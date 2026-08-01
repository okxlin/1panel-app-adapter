#!/usr/bin/env python3
"""Shared helpers for 1Panel lifecycle script generation."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml

ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_LINUX_ID = 4_294_967_294


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
    fields = (version_data.get("additionalProperties") or {}).get("formFields") or []
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


def parse_directory_permissions(
    specs: Iterable[str], path_fields: Iterable[dict[str, str]]
) -> dict[str, dict[str, str]]:
    valid_keys = {field["envKey"] for field in path_fields}
    permissions: dict[str, dict[str, str]] = {}
    for spec in specs:
        env_key, separator, value = spec.partition("=")
        parts = value.split(":") if separator else []
        if not ENV_KEY_PATTERN.fullmatch(env_key) or len(parts) != 3:
            raise ValueError(
                "directory owner must use ENV_KEY=UID:GID:MODE, for example "
                "APP_DATA_DIR=472:0:0750"
            )
        if env_key not in valid_keys:
            raise ValueError(
                f"directory owner references unknown path field: {env_key}"
            )
        if env_key in permissions:
            raise ValueError(f"duplicate directory owner for path field: {env_key}")

        uid, gid, mode = parts
        if not re.fullmatch(r"0|[1-9][0-9]*", uid) or int(uid) > MAX_LINUX_ID:
            raise ValueError(f"directory owner UID must be a valid Linux ID: {uid!r}")
        if not re.fullmatch(r"0|[1-9][0-9]*", gid) or int(gid) > MAX_LINUX_ID:
            raise ValueError(f"directory owner GID must be a valid Linux ID: {gid!r}")
        if not re.fullmatch(r"0?[0-7]{3}", mode):
            raise ValueError(
                f"directory mode must be three or four octal digits: {mode!r}"
            )
        normalized_mode = f"{int(mode, 8):04o}"
        if int(normalized_mode, 8) & 0o700 != 0o700:
            raise ValueError(
                f"directory mode must grant its source-backed owner read/write/execute: {mode!r}"
            )
        permissions[env_key] = {
            "uid": uid,
            "gid": gid,
            "mode": normalized_mode,
        }
    return permissions


def _shell_double_quote(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def render_init_script_content(
    version_data: dict[str, Any],
    directory_permissions: dict[str, dict[str, str]] | None = None,
) -> str:
    path_fields = collect_runtime_path_fields(version_data)
    directory_permissions = directory_permissions or {}
    unknown_permissions = set(directory_permissions) - {
        field["envKey"] for field in path_fields
    }
    if unknown_permissions:
        raise ValueError(
            "directory permissions reference unknown path fields: "
            + ", ".join(sorted(unknown_permissions))
        )
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "export PATH",
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
            '    \\"*\\") value="${value#\\"}"; value="${value%\\"}" ;;',
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
            "  printf '%s\\n' \"${value:-$default_value}\"",
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
            "resolve_direct_child() {",
            '  local key="$1"',
            '  local raw="$2"',
            "  local clean path",
            '  clean="${raw#./}"',
            '  if [[ -z "$clean" || "$clean" == */* ]]; then',
            '    echo "unsafe ${key} path: lifecycle directories must be direct children of the version root" >&2',
            "    return 1",
            "  fi",
            '  path="$(resolve_app_path "$key" "$raw")"',
            '  [[ "$path" == "$ROOT_DIR/$clean" ]] || { echo "unsafe ${key} path" >&2; return 1; }',
            "  printf '%s\\n' \"$path\"",
            "}",
            "",
            "verify_trusted_root_chain() {",
            "  local current owner mode",
            '  [[ "$(id -u)" == "0" ]] || { echo "directory ownership initialization must run as root" >&2; return 1; }',
            '  command -v stat >/dev/null 2>&1 || { echo "stat is required" >&2; return 1; }',
            '  current="$ROOT_DIR"',
            '  while [[ "$current" != "/" ]]; do',
            '    [[ -d "$current" && ! -L "$current" ]] || { echo "unsafe version root chain: $current" >&2; return 1; }',
            '    IFS=\':\' read -r owner mode < <(stat -c \'%u:%a\' -- "$current")',
            '    [[ "$owner" == "0" ]] || { echo "unsafe version root chain owner: $current" >&2; return 1; }',
            '    [[ "$mode" =~ ^[0-7]{3,4}$ ]] || { echo "unsafe version root chain mode: $current" >&2; return 1; }',
            '    (( (8#$mode & 0022) == 0 )) || { echo "unsafe version root chain permissions: $current" >&2; return 1; }',
            '    current="$(dirname -- "$current")"',
            "  done",
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
    if directory_permissions:
        lines.extend(
            [
                "ensure_owned_dir() {",
                '  local key="$1"',
                '  local default_value="$2"',
                '  local uid="$3"',
                '  local gid="$4"',
                '  local mode="$5"',
                "  local raw path actual expected_mode",
                '  raw="$(configured_value "$key" "$default_value")"',
                '  path="$(resolve_direct_child "$key" "$raw")"',
                "  verify_trusted_root_chain",
                '  if [[ -e "$path" || -L "$path" ]]; then',
                '    [[ -d "$path" && ! -L "$path" ]] || { echo "unsafe ${key} path" >&2; return 1; }',
                "  else",
                '    mkdir -- "$path"',
                "  fi",
                '  chmod "$mode" -- "$path"',
                '  [[ -d "$path" && ! -L "$path" ]] || { echo "unsafe ${key} path" >&2; return 1; }',
                '  chown --no-dereference "$uid:$gid" -- "$path"',
                '  expected_mode="${mode#0}"',
                '  actual="$(stat -c \'%u:%g:%a\' -- "$path")"',
                '  [[ "$actual" == "$uid:$gid:$expected_mode" ]] || { echo "${key} ownership/mode mismatch: expected ${uid}:${gid}:${expected_mode}, got ${actual}" >&2; return 1; }',
                "}",
                "",
            ]
        )
    for field in path_fields:
        env_key = _shell_double_quote(field["envKey"])
        default = _shell_double_quote(field["default"])
        permission = directory_permissions.get(field["envKey"])
        if permission:
            lines.append(
                f'ensure_owned_dir "{env_key}" "{default}" '
                f'"{permission["uid"]}" "{permission["gid"]}" "{permission["mode"]}"'
            )
        else:
            lines.append(f'ensure_dir "{env_key}" "{default}"')
    return "\n".join(lines) + "\n"


def load_version_data(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path} must be a regular non-symlink file")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML object")
    return data


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _open_directory_chain(path: Path) -> int:
    absolute = _absolute_lexical_path(path)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("directory-fd confinement requires Linux O_DIRECTORY/O_NOFOLLOW")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _load_version_data_at(version_fd: int) -> dict[str, Any]:
    data_fd = os.open("data.yml", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=version_fd)
    try:
        if not stat.S_ISREG(os.fstat(data_fd).st_mode):
            raise ValueError("data.yml must be a regular non-symlink file")
        with os.fdopen(data_fd, "r", encoding="utf-8") as fh:
            data_fd = -1
            data = yaml.safe_load(fh) or {}
    finally:
        if data_fd >= 0:
            os.close(data_fd)
    if not isinstance(data, dict):
        raise ValueError("data.yml did not contain a YAML object")
    return data


def _open_scripts_directory(version_fd: int) -> int:
    try:
        os.mkdir("scripts", mode=0o755, dir_fd=version_fd)
    except FileExistsError:
        pass
    try:
        return os.open(
            "scripts",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=version_fd,
        )
    except OSError as exc:
        raise ValueError("scripts directory must be a real directory") from exc


def _existing_regular_file(directory_fd: int, name: str) -> bool:
    try:
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{name} must be a regular non-symlink file")
    return True


def _write_temporary_file(directory_fd: int, name: str, content: str) -> str:
    temporary_name = f".{name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    temporary_fd = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        with os.fdopen(temporary_fd, "w", encoding="utf-8", newline="\n") as fh:
            temporary_fd = -1
            fh.write(content)
            fh.flush()
            os.fchmod(fh.fileno(), 0o755)
            os.fsync(fh.fileno())
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
    return temporary_name


def _atomic_replace_file(directory_fd: int, name: str, content: str) -> None:
    temporary_name = _write_temporary_file(directory_fd, name, content)
    try:
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except Exception:
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        raise


def _atomic_create_file(directory_fd: int, name: str, content: str) -> None:
    temporary_name = _write_temporary_file(directory_fd, name, content)
    try:
        try:
            os.link(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.fsync(directory_fd)
        except FileExistsError:
            _existing_regular_file(directory_fd, name)
    finally:
        os.unlink(temporary_name, dir_fd=directory_fd)


def _validate_scripts_anchor(version_fd: int, scripts_fd: int) -> None:
    anchored = os.fstat(scripts_fd)
    current = os.stat("scripts", dir_fd=version_fd, follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (
        anchored.st_dev,
        anchored.st_ino,
    ):
        raise ValueError("scripts directory changed during finalization")


UPGRADE_SCRIPT = "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n"
UNINSTALL_SCRIPT = "#!/bin/bash\ndocker-compose down --volumes\n"


def write_init_script(
    version_data_path: Path, out_path: Path, directory_owner_specs: Iterable[str] = ()
) -> None:
    version_dir = _absolute_lexical_path(version_data_path).parent
    expected_out = version_dir / "scripts" / "init.sh"
    if _absolute_lexical_path(out_path) != expected_out:
        raise ValueError("init output must be <version-dir>/scripts/init.sh")

    version_fd = _open_directory_chain(version_dir)
    try:
        version_data = _load_version_data_at(version_fd)
        path_fields = collect_runtime_path_fields(version_data)
        permissions = parse_directory_permissions(directory_owner_specs, path_fields)
        content = render_init_script_content(
            version_data, directory_permissions=permissions
        )
        scripts_fd = _open_scripts_directory(version_fd)
        try:
            if _existing_regular_file(scripts_fd, "init.sh"):
                raise ValueError("init.sh already exists")
            _atomic_replace_file(scripts_fd, "init.sh", content)
            _validate_scripts_anchor(version_fd, scripts_fd)
        finally:
            os.close(scripts_fd)
    finally:
        os.close(version_fd)


def finalize_lifecycle_scripts(
    version_data_path: Path,
    out_path: Path,
    directory_owner_specs: Iterable[str] = (),
    replace_init: bool = False,
) -> None:
    owner_specs = tuple(directory_owner_specs)
    version_dir = _absolute_lexical_path(version_data_path).parent
    expected_out = version_dir / "scripts" / "init.sh"
    if _absolute_lexical_path(out_path) != expected_out:
        raise ValueError("init output must be <version-dir>/scripts/init.sh")

    version_fd = _open_directory_chain(version_dir)
    try:
        version_data = _load_version_data_at(version_fd)
        path_fields = collect_runtime_path_fields(version_data)
        permissions = parse_directory_permissions(owner_specs, path_fields)
        content = render_init_script_content(
            version_data, directory_permissions=permissions
        )
        scripts_fd = _open_scripts_directory(version_fd)
        try:
            init_exists = _existing_regular_file(scripts_fd, "init.sh")
            if owner_specs and init_exists and not replace_init:
                raise ValueError(
                    "init.sh already exists; review it, then add --replace-init to "
                    "regenerate it with the explicit owner plan"
                )
            if not init_exists or replace_init:
                _atomic_replace_file(scripts_fd, "init.sh", content)
            if not _existing_regular_file(scripts_fd, "upgrade.sh"):
                _atomic_create_file(scripts_fd, "upgrade.sh", UPGRADE_SCRIPT)
            if not _existing_regular_file(scripts_fd, "uninstall.sh"):
                _atomic_create_file(scripts_fd, "uninstall.sh", UNINSTALL_SCRIPT)
            for name in ("init.sh", "upgrade.sh", "uninstall.sh"):
                _existing_regular_file(scripts_fd, name)
            _validate_scripts_anchor(version_fd, scripts_fd)
        finally:
            os.close(scripts_fd)
    finally:
        os.close(version_fd)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a confined 1Panel lifecycle init script."
    )
    parser.add_argument("version_data")
    parser.add_argument("out_init")
    parser.add_argument(
        "--dir-owner",
        action="append",
        default=[],
        metavar="ENV_KEY=UID:GID:MODE",
        help="apply source-backed ownership and mode to one exact confined directory",
    )
    parser.add_argument(
        "--finalize-lifecycle",
        action="store_true",
        help="atomically add all missing lifecycle scripts",
    )
    parser.add_argument(
        "--replace-init",
        action="store_true",
        help="replace an existing init.sh while finalizing lifecycle scripts",
    )
    args = parser.parse_args(argv[1:])
    try:
        if args.replace_init and not args.finalize_lifecycle:
            parser.error("--replace-init requires --finalize-lifecycle")
        if args.finalize_lifecycle:
            finalize_lifecycle_scripts(
                Path(args.version_data),
                Path(args.out_init),
                directory_owner_specs=args.dir_owner,
                replace_init=args.replace_init,
            )
        else:
            write_init_script(
                Path(args.version_data),
                Path(args.out_init),
                directory_owner_specs=args.dir_owner,
            )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
