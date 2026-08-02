#!/usr/bin/env python3
"""Conservative static checks for deterministic adaptation safety failures."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

SHELL_ASSIGNMENT = re.compile(
    r"^\s*(?:(?:export|local|readonly)\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$"
)
SHELL_VARIABLE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|([A-Za-z_][A-Za-z0-9_]*))"
)
COMMAND_POSITION = r"(?:^|(?:&&|\|\||;|\|)\s*|\bthen\s+|\bdo\s+|\$\(\s*)"
MUTATING_COMMAND_NAMES = {
    "mkdir",
    "touch",
    "install",
    "chmod",
    "chown",
    "cp",
    "mv",
    "rm",
    "rmdir",
    "truncate",
    "ln",
    "tee",
    "rsync",
    "sed",
    "tar",
}
MUTATING_COMMAND = re.compile(
    COMMAND_POSITION
    + r"(?:(?:if|while|until)\s+)?(?:sudo\s+|command\s+)?"
    + r"(?P<command>mkdir|touch|install|chmod|chown|cp|mv|rm|rmdir|truncate|ln|tee|rsync|sed|tar)\b"
)
COMMAND_INVOCATION = re.compile(
    COMMAND_POSITION
    + r"(?:(?:if|while|until)\s+)?(?:sudo\s+|command\s+)?"
    + r"(?P<command>\.|[A-Za-z_][A-Za-z0-9_.-]*)"
)
READ_ONLY_TAINT_COMMANDS = {
    "awk",
    "basename",
    "cut",
    "dirname",
    "echo",
    "false",
    "find",
    "grep",
    "head",
    "printf",
    "readlink",
    "realpath",
    "sed",
    "sort",
    "stat",
    "tail",
    "test",
    "tr",
    "true",
    "wc",
}
REDIRECTION = re.compile(r"(?<![<>])(?:[0-9]*)>>?(?![>&])")
CONNECTION_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
RANDOM_GENERATOR = re.compile(r"(?:openssl\s+rand|/dev/urandom|\bpwgen\b|\buuidgen\b)")
PATH_ENV_SEGMENT = re.compile(r"(?:^|_)(?:DIR|PATH|FILE)(?:_|$)", re.I)
SAFE_ENCODER_SUBSTITUTION = re.compile(
    r"\$\(\s*(?:url[_-]?encode|percent[_-]?encode)\s+"
    r"(?P<argument>\"[^\"]*\"|'[^']*'|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)\s*\)",
    re.I,
)
SAFE_RESOLVER_SUBSTITUTION = re.compile(
    r"\$\(\s*resolve_app_path\s+(?P<arguments>[^;&|]+)\s*\)"
)


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def _iter_form_fields(fields: Iterable[Any]):
    for field in fields:
        if not isinstance(field, dict):
            continue
        yield field
        child = field.get("child")
        if isinstance(child, dict):
            yield child
        elif isinstance(child, list):
            yield from _iter_form_fields(child)


def _shell_variables(text: str) -> set[str]:
    return {left or right for left, right in SHELL_VARIABLE.findall(text)}


def _references_name(text: str, name: str) -> bool:
    return (
        name in _shell_variables(text)
        or re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text)
        is not None
    )


def _is_path_form_field(field: dict[str, Any]) -> bool:
    env_key = str(field.get("envKey") or "")
    default = field.get("default")
    return bool(PATH_ENV_SEGMENT.search(env_key)) or (
        isinstance(default, str)
        and (default.startswith(("./", "../", "/")) or default.endswith("/"))
    )


def _short_volume_source(value: str) -> str | None:
    depth = 0
    cursor = 0
    while cursor < len(value):
        if value.startswith("${", cursor):
            depth += 1
            cursor += 2
            continue
        if value[cursor] == "}" and depth:
            depth -= 1
        elif value[cursor] == ":" and depth == 0:
            return value[:cursor]
        cursor += 1
    return None


def _compose_volume_sources(payload: Any):
    if not isinstance(payload, dict):
        return
    services = payload.get("services")
    if not isinstance(services, dict):
        return
    for service in services.values():
        if not isinstance(service, dict):
            continue
        volumes = service.get("volumes")
        if not isinstance(volumes, list):
            continue
        for volume in volumes:
            if isinstance(volume, str):
                source = _short_volume_source(volume)
            elif isinstance(volume, dict):
                source = volume.get("source")
            else:
                source = None
            if isinstance(source, str) and source:
                yield source


def _compose_bound_form_keys(compose_payload: Any, form_keys: set[str]) -> set[str]:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from compose_env_vars import extract_compose_variable_names

    bound: set[str] = set()
    for source in _compose_volume_sources(compose_payload):
        bound.update(extract_compose_variable_names(source) & form_keys)
    return bound


def _compose_variable_names(compose_text: str) -> set[str]:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from compose_env_vars import extract_compose_variable_names

    return extract_compose_variable_names(compose_text)


def _extract_shell_functions(text: str, name: str) -> list[str]:
    return re.findall(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n",
        text,
    )


def _reference_resolver_function() -> str:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from runtime_script_utils import render_init_script_content

    reference_script = render_init_script_content(
        {
            "additionalProperties": {
                "formFields": [{"envKey": "APP_DATA_DIR", "default": "./data"}]
            }
        }
    )
    functions = _extract_shell_functions(reference_script, "resolve_app_path")
    if len(functions) != 1:
        raise RuntimeError("generated resolver reference is ambiguous")
    return functions[0]


def _has_exact_generated_confinement(text: str) -> bool:
    functions = _extract_shell_functions(text, "resolve_app_path")
    return len(functions) == 1 and functions[0] == _reference_resolver_function()


def _safe_encoder_source(expression: str, candidates: set[str]) -> str | None:
    value = expression.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    match = SAFE_ENCODER_SUBSTITUTION.fullmatch(value)
    if match is None:
        return None
    variables = _shell_variables(match.group("argument"))
    if len(variables) != 1:
        return None
    source = next(iter(variables))
    return source if source in candidates else None


def _is_sole_resolver_value(expression: str, candidates: set[str]) -> bool:
    value = expression.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    match = SAFE_RESOLVER_SUBSTITUTION.fullmatch(value)
    return match is not None and bool(
        _shell_variables(match.group("arguments")) & candidates
    )


def _remove_safe_encoder_substitutions(text: str, candidates: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variables = _shell_variables(match.group("argument"))
        return (
            ""
            if len(variables) == 1 and next(iter(variables)) in candidates
            else match.group(0)
        )

    return SAFE_ENCODER_SUBSTITUTION.sub(replace, text)


def _segment_after_command(line: str, start: int) -> str:
    remainder = line[start:]
    return re.split(r"(?:&&|\|\||;|\|)", remainder, maxsplit=1)[0]


def _logical_shell_lines(text: str):
    buffer = ""
    start_line = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not buffer:
            start_line = line_number
        stripped = raw_line.rstrip()
        slash_count = len(stripped) - len(stripped.rstrip("\\"))
        if slash_count % 2 == 1:
            buffer += stripped[:-1] + " "
            continue
        yield start_line, buffer + raw_line
        buffer = ""
    if buffer:
        yield start_line, buffer


def _executable_shell_text(text: str) -> str:
    return "\n".join(
        line
        for _, line in _logical_shell_lines(text)
        if line.strip() and not line.lstrip().startswith("#")
    )


def _opaque_tainted_variables(
    line: str,
    candidates: set[str],
    *,
    confined_resolver: bool,
    allow_encoders: bool = False,
) -> set[str]:
    unsafe: set[str] = set()
    assignment = SHELL_ASSIGNMENT.match(line)
    for match in COMMAND_INVOCATION.finditer(line):
        if assignment is not None and match.start() == 0:
            continue
        command = match.group("command")
        segment = _segment_after_command(line, match.end())
        used = _shell_variables(segment) & candidates
        if not used:
            continue
        if command in MUTATING_COMMAND_NAMES:
            continue
        if command == "resolve_app_path" and confined_resolver:
            continue
        if allow_encoders and re.fullmatch(
            r"(?:url[_-]?encode|percent[_-]?encode)", command, re.I
        ):
            continue
        if command in READ_ONLY_TAINT_COMMANDS:
            continue
        unsafe.update(used)
    return unsafe


def _mutating_path_variables(line: str, tainted_paths: set[str]) -> set[str]:
    unsafe: set[str] = set()
    for match in MUTATING_COMMAND.finditer(line):
        segment = _segment_after_command(line, match.end())
        command = match.group("command")
        if command == "sed" and re.search(r"(?:^|\s)-[^\s]*i", segment) is None:
            continue
        if (
            command == "tar"
            and re.search(r"(?:^|\s)(?:-[^\s]*x|--extract)(?:\s|$)", segment) is None
        ):
            continue
        unsafe.update(_shell_variables(segment) & tainted_paths)

    for match in REDIRECTION.finditer(line):
        target_segment = _segment_after_command(line, match.end())
        unsafe.update(_shell_variables(target_segment) & tainted_paths)
    return unsafe


def analyze_shell(
    path: Path, path_keys: set[str], random_keys: set[str]
) -> list[Finding]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    confined_resolver = _has_exact_generated_confinement(text)
    tainted_paths = set(path_keys)
    tainted_random = set(random_keys)
    encoded_random: set[str] = set()
    findings: list[Finding] = []

    for line_number, raw_line in _logical_shell_lines(text):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        assignment = SHELL_ASSIGNMENT.match(raw_line)
        if assignment:
            target, expression = assignment.groups()
            expression_vars = _shell_variables(expression)
            path_source = bool(expression_vars & tainted_paths) or any(
                _references_name(expression, key) for key in path_keys
            )
            if path_source:
                if confined_resolver and _is_sole_resolver_value(
                    expression, tainted_paths
                ):
                    tainted_paths.discard(target)
                else:
                    tainted_paths.add(target)

            random_source = bool(expression_vars & tainted_random) or any(
                _references_name(expression, key) for key in random_keys
            )
            if RANDOM_GENERATOR.search(expression):
                random_source = True
            if random_source:
                tainted_random.add(target)
                if _safe_encoder_source(expression, tainted_random) is not None:
                    encoded_random.add(target)
                else:
                    encoded_random.discard(target)

        unsafe_paths = sorted(_mutating_path_variables(line, tainted_paths))
        if (
            re.search(COMMAND_POSITION + r"(?:sudo\s+|command\s+)?find\b", line)
            and "-delete" in line
        ):
            unsafe_paths.extend(sorted(_shell_variables(line) & tainted_paths))
        if unsafe_paths:
            findings.append(
                Finding(
                    "A",
                    f"{path.name}:{line_number}: unconfined form path reaches mutating command via {', '.join(sorted(set(unsafe_paths)))}",
                )
            )

        opaque_paths = sorted(
            _opaque_tainted_variables(
                line,
                tainted_paths,
                confined_resolver=confined_resolver,
            )
        )
        if opaque_paths:
            findings.append(
                Finding(
                    "A",
                    f"{path.name}:{line_number}: unconfined form path reaches an opaque shell command via {', '.join(opaque_paths)}",
                )
            )

        if CONNECTION_URL.search(line):
            checked_line = _remove_safe_encoder_substitutions(line, tainted_random)
            used = _shell_variables(checked_line)
            unsafe_random = sorted((used & tainted_random) - encoded_random)
            if unsafe_random:
                findings.append(
                    Finding(
                        "B",
                        f"{path.name}:{line_number}: random credential is interpolated raw into a connection URL via {', '.join(unsafe_random)}; URL-encode it or prove and validate a source-backed URL-safe alphabet",
                    )
                )

        opaque_random = sorted(
            _opaque_tainted_variables(
                line,
                tainted_random,
                confined_resolver=confined_resolver,
                allow_encoders=True,
            )
        )
        if opaque_random:
            findings.append(
                Finding(
                    "B",
                    f"{path.name}:{line_number}: random credential reaches an opaque shell command via {', '.join(opaque_random)}; inspect the complete value flow before constructing a connection URL",
                )
            )

    return findings


def analyze(
    version_data_path: Path, compose_path: Path, scripts_dir: Path
) -> list[Finding]:
    version_data = yaml.safe_load(version_data_path.read_text(encoding="utf-8")) or {}
    fields = list(
        _iter_form_fields(
            ((version_data.get("additionalProperties") or {}).get("formFields") or [])
        )
    )
    form_keys = {str(field.get("envKey")) for field in fields if field.get("envKey")}
    path_keys = {
        str(field.get("envKey"))
        for field in fields
        if field.get("envKey") and _is_path_form_field(field)
    }
    random_keys = {
        str(field.get("envKey"))
        for field in fields
        if str(field.get("random", "")).lower() == "true" and field.get("envKey")
    }

    findings: list[Finding] = []
    compose_text = compose_path.read_text(encoding="utf-8", errors="ignore")
    compose_payload = yaml.safe_load(compose_text) or {}
    compose_keys = _compose_variable_names(compose_text)
    editable_keys = {
        str(field.get("envKey"))
        for field in fields
        if field.get("envKey") and field.get("edit") is True
    }
    if scripts_dir.is_dir():
        init_path = scripts_dir / "init.sh"
        upgrade_path = scripts_dir / "upgrade.sh"
        init_text = (
            init_path.read_text(encoding="utf-8", errors="ignore")
            if init_path.is_file()
            else ""
        )
        upgrade_text = (
            upgrade_path.read_text(encoding="utf-8", errors="ignore")
            if upgrade_path.is_file()
            else ""
        )
        init_text = _executable_shell_text(init_text)
        upgrade_text = _executable_shell_text(upgrade_text)
        for env_key in sorted(editable_keys - compose_keys):
            if _references_name(init_text, env_key) and not _references_name(
                upgrade_text, env_key
            ):
                findings.append(
                    Finding(
                        "A",
                        f"editable field {env_key} has no post-install consumer; set edit:false or add a reviewed upgrade reconciliation/migration",
                    )
                )
    path_keys.update(_compose_bound_form_keys(compose_payload, form_keys))
    for line_number, raw_line in enumerate(compose_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or not CONNECTION_URL.search(line):
            continue
        used = _shell_variables(line)
        unsafe_random = sorted(used & random_keys)
        if unsafe_random:
            findings.append(
                Finding(
                    "B",
                    f"{compose_path.name}:{line_number}: random credential is interpolated raw into a connection URL via {', '.join(unsafe_random)}; URL-encode it or prove and validate a source-backed URL-safe alphabet",
                )
            )

    if scripts_dir.is_dir():
        for script_path in sorted(scripts_dir.glob("*.sh")):
            findings.extend(analyze_shell(script_path, path_keys, random_keys))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check deterministic lifecycle and credential hazards"
    )
    parser.add_argument("--version-data", required=True)
    parser.add_argument("--compose", required=True)
    parser.add_argument("--scripts-dir", required=True)
    args = parser.parse_args()

    findings = analyze(
        Path(args.version_data), Path(args.compose), Path(args.scripts_dir)
    )
    for finding in findings:
        label = "FAIL" if finding.level == "A" else "WARN"
        print(f"[{finding.level}][{label}] {finding.message}")
    return 1 if any(finding.level == "A" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
