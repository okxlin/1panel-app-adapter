#!/usr/bin/env python3
"""Shared helpers for 1Panel lifecycle script generation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


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


def _looks_like_file(env_key: str, default: str) -> bool:
    env_upper = str(env_key or "").upper()
    if "FILE" in env_upper:
        return True
    basename = Path(default).name
    if not basename or default.endswith("/"):
        return False
    return "." in basename


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
        seen.add(env_key)
        path_fields.append(
            {
                "envKey": env_key,
                "default": default_str,
                "kind": "file" if _looks_like_file(env_key, default_str) else "dir",
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
        'ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"',
        'ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"',
    ]
    if not path_fields:
        lines.extend(["", 'mkdir -p "$ROOT_DIR/data"'])
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
            '  local raw="$1"',
            '  if [[ "$raw" = /* ]]; then',
            "    printf '%s\\n' \"$raw\"",
            "  else",
            "    printf '%s\\n' \"$ROOT_DIR/${raw#./}\"",
            "  fi",
            "}",
            "",
            "ensure_dir() {",
            "  local path",
            '  path="$(resolve_app_path "$(configured_value "$1" "$2")")"',
            '  mkdir -p "$path"',
            "}",
            "",
            "ensure_file_parent() {",
            "  local path",
            "  local parent",
            '  path="$(resolve_app_path "$(configured_value "$1" "$2")")"',
            '  parent="$(dirname "$path")"',
            '  mkdir -p "$parent"',
            "}",
            "",
        ]
    )
    for field in path_fields:
        env_key = _shell_double_quote(field["envKey"])
        default = _shell_double_quote(field["default"])
        if field["kind"] == "file":
            lines.append(f'ensure_file_parent "{env_key}" "{default}"')
        else:
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
