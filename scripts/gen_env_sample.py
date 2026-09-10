#!/usr/bin/env python3
"""Write literal Docker Compose environment samples from panel form defaults.

Syntax: https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#env-file-syntax
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any

import yaml

from appstore_i18n import iter_fields
from compose_env_vars import extract_compose_variable_names

ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CONTAINER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
DOUBLE_ESCAPES = {
    "\\": "\\", "a": "\a", "b": "\b", "f": "\f", "n": "\n",
    "r": "\r", "t": "\t", "v": "\v", "$": "$$",
}
ENCODE_ESCAPES = {
    "\\": "\\\\", '"': '\\"', "$": "$$", "\a": "\\a", "\b": "\\b",
    "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\v": "\\v",
}


def normalize_env_default(value: Any) -> str:
    """Use panel-compatible scalar spelling without Python bool/null literals."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, (str, int, float)):
        raise ValueError("environment defaults must be scalar strings, numbers, booleans, or null")
    text = str(value)
    if "\0" in text:
        raise ValueError("environment defaults cannot contain NUL")
    return text


def format_env_value(value: Any) -> str:
    """Quote complex literals; escaped dollars never read the caller's environment."""
    text = normalize_env_default(value)
    if not re.search(r"""[\s'"\\$#]""", text):
        return text
    return '"' + "".join(ENCODE_ESCAPES.get(char, char) for char in text) + '"'


def _literal_dollars(value: str, *, allow_interpolation: bool = False) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group() == "$$":
            return "$"
        if allow_interpolation:
            return match.group()
        raise ValueError("env sample contains interpolation; a literal value is required")
    return re.sub(r"\$\$|\$(?=[A-Za-z_{])", replace, value)


def _read_quoted_value(text: str, start: int, *, allow_interpolation: bool = False) -> tuple[str, int]:
    quote = text[start]
    chars = []
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == quote:
            value = "".join(chars)
            if quote == '"':
                value = re.sub(r"\\([abfnrtv\\$])", lambda match: DOUBLE_ESCAPES[match.group(1)], value)
                value = _literal_dollars(value, allow_interpolation=allow_interpolation)
            return value, cursor + 1
        if char == "\\" and cursor + 1 < len(text):
            following = text[cursor + 1]
            if following == quote:
                chars.append(quote)
            else:
                chars.extend((char, following))
            cursor += 2
        else:
            chars.append(char)
            cursor += 1
    raise ValueError("env sample contains an unterminated quoted value")


def read_env_sample(path: Path, *, allow_interpolation: bool = False) -> dict[str, str]:
    """Read literal assignments, including quoted multiline values; never expand vars.

    This intentionally supports a literal subset, not shell evaluation or inherited
    environment values. Unescaped variable interpolation is rejected by default;
    allow_interpolation preserves unresolved expressions without evaluating them.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    values: dict[str, str] = {}
    cursor = 0
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        if text[cursor] == "#":
            end = text.find("\n", cursor)
            cursor = len(text) if end < 0 else end + 1
            continue
        match = re.match(r"(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*[=:][ \t]*", text[cursor:])
        if match is None:
            raise ValueError("env sample requires literal KEY=value assignments")
        key = match.group(1)
        cursor += match.end()
        if cursor < len(text) and text[cursor] in {'"', "'"}:
            value, cursor = _read_quoted_value(text, cursor, allow_interpolation=allow_interpolation)
            end = text.find("\n", cursor)
            end = len(text) if end < 0 else end
            suffix = text[cursor:end].strip()
            if suffix and not suffix.startswith("#"):
                raise ValueError("env sample has trailing text after a quoted value")
        else:
            end = text.find("\n", cursor)
            end = len(text) if end < 0 else end
            value = _literal_dollars(
                text[cursor:end].split(" #", 1)[0].rstrip(),
                allow_interpolation=allow_interpolation,
            )
        values[key] = value
        cursor = end + 1
    return values


def write_env_sample(
    version_data_path: Path,
    output_path: Path,
    compose_path: Path | None = None,
    container_name: str | None = None,
) -> dict[str, str]:
    """Write selected scalar form defaults and return their literal values.

    With Compose supplied, emit only referenced form keys. An apps selector is
    included only when Compose references it; without Compose, omit selectors.
    Undeclared keys stay unset so Compose's own default operators retain meaning.
    """
    output_path = Path(output_path)
    app_key = output_path.parent.parent.name
    if container_name is None:
        container_name = f"{app_key}-compose-check" if CONTAINER_NAME.fullmatch(app_key) else "adapter-compose-check"
    if CONTAINER_NAME.fullmatch(container_name) is None:
        raise ValueError("container-name must be a valid non-empty Docker container name")
    data = yaml.safe_load(Path(version_data_path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("additionalProperties", {}), dict):
        raise ValueError("version metadata and additionalProperties must be YAML mappings")
    properties = data.get("additionalProperties") or {}
    referenced = None
    if compose_path is not None:
        referenced = extract_compose_variable_names(Path(compose_path).read_text(encoding="utf-8"))
    values = {"CONTAINER_NAME": container_name}
    for field in iter_fields(properties.get("formFields")):
        key = field.get("envKey")
        if not key or key == "CONTAINER_NAME":
            continue
        if not isinstance(key, str) or ENV_NAME.fullmatch(key) is None:
            raise ValueError("form envKey must be a valid environment variable name")
        if referenced is not None and key not in referenced:
            continue
        if str(field.get("type", "")).lower() == "apps" and (referenced is None or key not in referenced):
            continue
        values[key] = normalize_env_default(field.get("default"))
    output = "".join(f"{key}={format_env_value(value)}\n" for key, value in values.items())
    output_path.write_text(output, encoding="utf-8")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version_data", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("compose", nargs="?", type=Path)
    parser.add_argument("container_name", nargs="?")
    args = parser.parse_args()
    if args.container_name is not None and CONTAINER_NAME.fullmatch(args.container_name) is None:
        parser.error("container-name must be a valid non-empty Docker container name")
    try:
        write_env_sample(args.version_data, args.output, args.compose, args.container_name)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
