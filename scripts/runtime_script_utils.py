#!/usr/bin/env python3
"""Shared helpers for 1Panel lifecycle script generation."""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml


ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _iter_form_fields(fields: Iterable[Any]):
    for field in fields:
        if not isinstance(field, dict):
            continue
        yield field
        child = field.get("child")
        if isinstance(child, dict):
            yield child
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    yield item


def _is_path_default(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(("./", "../", "/"))


def _validate_package_local_default(env_key: str, value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value.startswith("./")
        or value in (".", "./")
        or path.is_absolute()
        or ".." in path.parts
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(
            f"{env_key} path default must be a package-local relative path beginning with ./"
        )


def _is_explicit_directory(env_key: str, default: str) -> bool:
    env_upper = str(env_key or "").upper()
    if "FILE" in env_upper:
        return False
    return bool(re.search(r"(^|_)DIR($|_)", env_upper)) or default.endswith("/")


def collect_runtime_path_fields(version_data: dict[str, Any]) -> list[dict[str, str]]:
    fields = ((version_data.get("additionalProperties") or {}).get("formFields") or [])
    path_fields: list[dict[str, str]] = []
    seen: set[str] = set()
    for field in _iter_form_fields(fields):
        env_key = str(field.get("envKey") or "").strip()
        default = field.get("default")
        if not env_key or env_key in seen or not _is_path_default(default):
            continue
        default_str = str(default)
        if not ENV_KEY_PATTERN.fullmatch(env_key):
            raise ValueError(f"{env_key!r} is not a valid environment variable name")
        _validate_package_local_default(env_key, default_str)
        if not _is_explicit_directory(env_key, default_str):
            raise ValueError(
                f"{env_key} is not an explicit directory field; define an application-specific "
                "exact file lifecycle or rename a proven directory field with a DIR segment"
            )
        seen.add(env_key)
        path_fields.append(
            {
                "envKey": env_key,
                "default": default_str,
            }
        )
    return path_fields


def _shell_double_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def render_init_script_content(version_data: dict[str, Any]) -> str:
    path_fields = collect_runtime_path_fields(version_data)
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        'ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"',
        'ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"',
    ]
    if not path_fields:
        lines.extend(
            [
                "",
                'DATA_DIR="$ROOT_DIR/data"',
                '[[ ! -L "$DATA_DIR" ]] || { echo "unsafe PACKAGE_DATA_DIR path" >&2; exit 1; }',
                'mkdir -p -- "$DATA_DIR"',
                '[[ ! -L "$DATA_DIR" ]] || { echo "unsafe PACKAGE_DATA_DIR path" >&2; exit 1; }',
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "",
            "read_env_value() {",
            '  local key="$1"',
            '  [[ -f "$ENV_FILE" ]] || return 0',
            "  local value",
            '  value="$(sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1)"',
            '  case "$value" in',
            '    \\"*\\") value="${value#\\\"}"; value="${value%\\\"}" ;;',
            "    \\'*\\') value=\"${value#\\'}\"; value=\"${value%\\'}\" ;;",
            "  esac",
            "  printf '%s\\n' \"$value\"",
            "}",
            "",
            "configured_value() {",
            '  local key="$1"',
            '  local default_value="$2"',
            "  local value",
            '  value="${!key:-}"',
            '  if [[ -z "$value" ]]; then',
            '    value="$(read_env_value "$key")"',
            "  fi",
            '  printf \'%s\\n\' "${value:-$default_value}"',
            "}",
            "",
            "resolve_app_path() {",
            '  local key="$1"',
            '  local raw="$2"',
            "  local clean candidate resolved current part",
            "  local -a parts=()",
            '  case "$raw" in',
            '    ""|/*|.|..|../*|*/../*|*/..) echo "unsafe ${key} path" >&2; return 1 ;;',
            "  esac",
            '  if [[ "$raw" =~ [[:cntrl:]] ]]; then',
            '    echo "unsafe ${key} path" >&2',
            "    return 1",
            "  fi",
            '  clean="${raw#./}"',
            '  [[ -n "$clean" ]] || { echo "unsafe ${key} path" >&2; return 1; }',
            '  command -v realpath >/dev/null 2>&1 || { echo "realpath is required" >&2; return 1; }',
            '  candidate="$ROOT_DIR/$clean"',
            '  resolved="$(realpath -m -- "$candidate")" || { echo "unsafe ${key} path" >&2; return 1; }',
            '  case "$resolved" in',
            '    "$ROOT_DIR"/*) ;;',
            '    *) echo "unsafe ${key} path" >&2; return 1 ;;',
            "  esac",
            '  current="$ROOT_DIR"',
            "  IFS='/' read -r -a parts <<< \"$clean\"",
            '  for part in "${parts[@]}"; do',
            '    [[ -z "$part" || "$part" == "." ]] && continue',
            '    current="$current/$part"',
            '    if [[ -L "$current" ]]; then',
            '      echo "unsafe ${key} path" >&2',
            "      return 1",
            "    fi",
            "  done",
            "  printf '%s\\n' \"$resolved\"",
            "}",
            "",
            "ensure_dir() {",
            '  local key="$1"',
            "  local raw",
            "  local path",
            '  raw="$(configured_value "$key" "$2")"',
            '  path="$(resolve_app_path "$key" "$raw")"',
            '  mkdir -p -- "$path"',
            '  [[ "$(resolve_app_path "$key" "$raw")" == "$path" ]] || { echo "unsafe ${key} path" >&2; return 1; }',
            "}",
            "",
        ]
    )
    for field in path_fields:
        env_key = _shell_double_quote(field["envKey"])
        default = _shell_double_quote(field["default"])
        lines.append(f'ensure_dir "{env_key}" "{default}"')
    return "\n".join(lines) + "\n"


def load_version_data(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML object")
    return data


def write_init_script(version_data_path: Path, out_path: Path) -> None:
    content = render_init_script_content(load_version_data(version_data_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    out_path.chmod(0o755)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: runtime_script_utils.py <version-data.yml> <out-init.sh>", file=sys.stderr)
        return 2
    write_init_script(Path(argv[1]), Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
