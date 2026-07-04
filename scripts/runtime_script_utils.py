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


def _var_expr(env_key: str, default: str) -> str:
    return f'${{{env_key}:-{_shell_double_quote(default)}}}'


def render_init_script_content(version_data: dict[str, Any]) -> str:
    path_fields = collect_runtime_path_fields(version_data)
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
    ]
    if not path_fields:
        lines.append("mkdir -p ./data")
        return "\n".join(lines) + "\n"

    file_fields = [field for field in path_fields if field["kind"] == "file"]
    if file_fields:
        lines.extend(
            [
                "",
                "ensure_parent_dir() {",
                '  local path="$1"',
                "  local parent",
                '  parent="$(dirname "$path")"',
                '  if [[ -n "$parent" && "$parent" != "." ]]; then',
                '    mkdir -p "$parent"',
                "  fi",
                "}",
            ]
        )

    lines.append("")
    for field in path_fields:
        expr = _var_expr(field["envKey"], field["default"])
        if field["kind"] == "file":
            lines.append(f'ensure_parent_dir "{expr}"')
        else:
            lines.append(f'mkdir -p "{expr}"')
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
