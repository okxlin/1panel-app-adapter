#!/usr/bin/env python3
"""
Baota Docker Store app import library for 1Panel.

Provides: BaotaPrecheck, BaotaParser, BaotaToAppSpecMapper,
          ComposeTransformer, ImportRunner, error codes.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

# ── PyYAML (required dependency) ──────────────────────────────────────
try:
    import yaml
except ImportError:
    sys.stderr.write(
        "Error: PyYAML is required. Install with: pip install pyyaml\n"
    )
    raise SystemExit(1)

from runtime_script_utils import render_init_script_content

# ── Error Codes ───────────────────────────────────────────────────────
E_BAOTA_REQUIRED_FILES = "E_BAOTA_REQUIRED_FILES"
E_BAOTA_APP_KEY_INVALID = "E_BAOTA_APP_KEY_INVALID"
E_BAOTA_APP_JSON_MISSING = "E_BAOTA_APP_JSON_MISSING"
E_BAOTA_APP_JSON_INVALID = "E_BAOTA_APP_JSON_INVALID"
E_BAOTA_COMPOSE_INVALID = "E_BAOTA_COMPOSE_INVALID"
E_BAOTA_COMPOSE_MISSING = "E_BAOTA_COMPOSE_MISSING"
E_BAOTA_ENV_MISSING = "E_BAOTA_ENV_MISSING"
E_BAOTA_ICON_MISSING = "E_BAOTA_ICON_MISSING"
E_BAOTA_OUTPUT_PATH_INVALID = "E_BAOTA_OUTPUT_PATH_INVALID"
E_BAOTA_VERSION_INVALID = "E_BAOTA_VERSION_INVALID"
E_BAOTA_VERSION_DIR_MISSING = "E_BAOTA_VERSION_DIR_MISSING"
E_BAOTA_VERSION_MISSING = "E_BAOTA_VERSION_MISSING"
E_BAOTA_DISABLED = "E_BAOTA_DISABLED"
E_BAOTA_EVIDENCE_INVALID = "E_BAOTA_EVIDENCE_INVALID"
E_1PANEL_VALIDATION_MODE_REQUIRED = "E_1PANEL_VALIDATION_MODE_REQUIRED"

APP_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# ── Standard Baota platform fields / env keys ─────────────────────────
STANDARD_FIELD_ATTRS = {"domain", "allow_access", "cpus", "memory_limit"}
STANDARD_ENV_KEYS = {"app_path", "host_ip", "cpus", "memory_limit"}
I18N_LANGS = ["en", "zh", "zh-Hant", "ja", "ko", "ru", "ms", "pt-br"]

# ── App type mapping ──────────────────────────────────────────────────
BAOTA_TYPE_TO_1PANEL: Dict[str, str] = {
    "BuildWebsite": "Website",
    "Database": "Database",
    "Storage": "Storage",
    "Tools": "Tool",
    "Middleware": "Middleware",
    "AI": "AI",
    "Media": "Media",
    "Email": "Email",
    "DevOps": "DevOps",
    "Security": "Security",
}
_FALLBACK_TYPE = "Tool"

# ── Field type mapping ────────────────────────────────────────────────
BAOTA_FIELD_TYPE_TO_FORM: Dict[str, str] = {
    "number": "number",
    "string": "text",
    "textarea": "text",
    "checkbox": "select",
    "select": "select",
    "path": "text",
    "port": "number",
    "password": "password",
}

# ── Helpers ───────────────────────────────────────────────────────────


def _is_https_url(url: Any) -> bool:
    return isinstance(url, str) and bool(re.match(r"^https://[^\s]+$", url.strip()))


def _is_safe_app_key(value: Any) -> bool:
    return isinstance(value, str) and bool(APP_KEY_RE.fullmatch(value))


def _is_safe_version(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value not in {".", ".."}
        and bool(VERSION_RE.fullmatch(value))
    )


def _resolve_child(root: pathlib.Path, *components: str) -> pathlib.Path:
    root_resolved = root.resolve()
    candidate = root_resolved.joinpath(*components).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes root directory: {candidate}") from exc
    return candidate


class BaotaEvidenceError(ValueError):
    """Existing conversion evidence is malformed and cannot be merged safely."""


def _load_existing_evidence(path: pathlib.Path) -> Dict[str, Any]:
    if path.is_symlink():
        raise BaotaEvidenceError(f"Existing source evidence must not be a symlink: {path}")
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BaotaEvidenceError(f"Invalid existing source evidence at {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise BaotaEvidenceError(f"Invalid existing source evidence at {path}: expected a JSON object")
    return loaded


def _version_sort_key(version: str) -> Tuple[int, str]:
    return (0 if version == "latest" else 1, version)


def _stable_versions(versions: List[str]) -> List[str]:
    return sorted(
        {version for version in versions if _is_safe_version(version)},
        key=_version_sort_key,
    )


def _generated_output_targets(
    app_dir: pathlib.Path,
    version_dir: pathlib.Path,
) -> List[pathlib.Path]:
    scripts_dir = version_dir / "scripts"
    return [
        app_dir,
        version_dir,
        version_dir / "data",
        scripts_dir,
        app_dir / "data.yml",
        app_dir / "README.md",
        app_dir / "logo.png",
        app_dir / "source-evidence.json",
        version_dir / "data.yml",
        version_dir / "docker-compose.yml",
        version_dir / ".env.sample",
        scripts_dir / "init.sh",
        scripts_dir / "upgrade.sh",
        scripts_dir / "uninstall.sh",
    ]


def _assert_safe_output_targets(
    output_root: pathlib.Path,
    targets: List[pathlib.Path],
) -> None:
    root = output_root.resolve()
    for target in targets:
        absolute = target.absolute()
        try:
            relative = absolute.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Output target escapes root directory: {target}") from exc

        current = root
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise ValueError(f"Output target must not traverse a symlink: {current}")

        try:
            target.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Output target escapes root directory: {target}") from exc


def _load_compose_document(compose_path: pathlib.Path) -> Dict[str, Any]:
    try:
        with open(compose_path, "r", encoding="utf-8") as fh:
            compose = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Cannot parse Compose YAML: {exc}") from exc

    if not isinstance(compose, dict):
        raise ValueError("Compose document must be a mapping")
    services = compose.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("Compose services must be a non-empty mapping")
    invalid_services = [name for name, service in services.items() if not isinstance(service, dict)]
    if invalid_services:
        raise ValueError(f"Compose services must be mappings: {', '.join(map(str, invalid_services))}")
    return compose


def run_strict_store_validation(
    app_dir: str,
    version: Optional[str] = None,
    emit_output: bool = False,
) -> Dict[str, Any]:
    validate_script = pathlib.Path(__file__).resolve().parent / "validate-v2.sh"
    if not validate_script.is_file():
        return {
            "mode": "strict-store",
            "validator": str(validate_script),
            "valid": False,
            "failed": True,
            "errors": [f"validate-v2.sh not found: {validate_script}"],
            "stdout": "",
            "stderr": "",
            "returncode": 127,
        }

    command = ["bash", str(validate_script), "--dir", app_dir]
    if version:
        command.extend(["--version", version])
    command.append("--strict-store")
    proc = subprocess.run(command, text=True, capture_output=True)
    if emit_output and proc.stdout:
        print(proc.stdout, end="")
    if emit_output and proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    errors = [line for line in (proc.stdout + proc.stderr).splitlines() if "[FAIL]" in line]
    if proc.returncode != 0 and not errors:
        errors.append(f"strict-store validation failed with exit code {proc.returncode}")
    return {
        "mode": "strict-store",
        "validator": str(validate_script),
        "valid": proc.returncode == 0,
        "failed": proc.returncode != 0,
        "errors": errors,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }


def evaluate_baota_delivery_readiness(
    appspec: Dict[str, Any],
    compose_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    import_source = appspec.get("importSource", {})
    if not isinstance(import_source, dict) or import_source.get("type") != "baota":
        return {"applicable": False, "ready": True, "status": "not_applicable", "blockers": []}

    blockers: List[Dict[str, str]] = []
    if appspec.get("evidenceStatus") != "official_complete":
        blockers.append({
            "code": "unverified-source",
            "message": "Baota metadata does not prove official upstream deployment evidence.",
        })
    if appspec.get("architectureEvidence") != "registry_manifest_verified":
        blockers.append({
            "code": "unverified-architectures",
            "message": "Packaged architectures have not been verified from registry manifests.",
        })

    manual_reasons = appspec.get("manualReviewReasons", []) or []
    if compose_data and isinstance(compose_data, dict):
        transform = compose_data.get("_transform", {})
        if isinstance(transform, dict):
            manual_reasons = [*manual_reasons, *(transform.get("manualReviewReasons", []) or [])]
    seen_codes = {blocker["code"] for blocker in blockers}
    for reason in manual_reasons:
        code = reason.get("code", "compose-manual-review")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        blockers.append({
            "code": code,
            "message": reason.get("message", "Compose semantics require manual review."),
        })
    return {
        "applicable": True,
        "ready": not blockers,
        "status": "ready" if not blockers else "manual_review_required",
        "blockers": blockers,
    }


def _merge_baota_source_evidence(
    existing: Dict[str, Any],
    current: Dict[str, Any],
    version: str,
) -> Dict[str, Any]:
    merged = copy.deepcopy(current)
    current_import = merged.get("importSource", {})
    if not isinstance(current_import, dict) or current_import.get("type") != "baota":
        return merged

    existing_import = existing.get("importSource", {}) if isinstance(existing, dict) else {}
    same_app = (
        isinstance(existing_import, dict)
        and existing_import.get("type") == "baota"
        and existing_import.get("appName") == current_import.get("appName")
    )
    existing_source = (
        existing_import.get("sourcePath"),
        existing.get("repository"),
        existing_import.get("declaredHome"),
        existing_import.get("declaredHelp"),
    )
    current_source = (
        current_import.get("sourcePath"),
        current.get("repository"),
        current_import.get("declaredHome"),
        current_import.get("declaredHelp"),
    )
    same_source = same_app and any(current_source) and existing_source == current_source
    versions: List[str] = []
    if same_source:
        prior_versions = existing_import.get("versions", [])
        if isinstance(prior_versions, list):
            versions.extend(item for item in prior_versions if _is_safe_version(item))
        prior_selected = existing_import.get("version")
        if _is_safe_version(prior_selected):
            versions.append(prior_selected)
    versions.append(version)
    current_import["versions"] = _stable_versions(versions)
    merged["importSource"] = current_import

    version_evidence: Dict[str, Any] = {}
    if same_app and isinstance(existing.get("versionEvidence"), dict):
        version_evidence.update({
            key: copy.deepcopy(value)
            for key, value in existing["versionEvidence"].items()
            if _is_safe_version(key) and isinstance(value, dict)
        })
    version_import = copy.deepcopy(current_import)
    version_import.pop("versions", None)
    version_import["version"] = version
    version_evidence[version] = {
        "repository": merged.get("repository", ""),
        "dockerDocs": merged.get("dockerDocs", ""),
        "composeFile": merged.get("composeFile", ""),
        "evidenceStatus": merged.get("evidenceStatus", "third_party_only"),
        "architectures": merged.get("architectures", ["amd64"]),
        "architectureEvidence": merged.get("architectureEvidence", "unverified_default"),
        "importSource": version_import,
    }
    merged["versionEvidence"] = {
        key: version_evidence[key]
        for key in sorted(version_evidence, key=_version_sort_key)
    }
    return merged


def _normalize_git_remote_url(remote_url: str) -> str:
    remote = remote_url.strip()
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote[len("git@github.com:") :]
    if remote.endswith(".git"):
        remote = remote[:-4]
    return remote.rstrip("/")


def _read_git_branch(git_dir: pathlib.Path) -> str:
    head = git_dir / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return "main"
    if text.startswith("ref:"):
        return pathlib.PurePosixPath(text.split(" ", 1)[1].strip()).name or "main"
    return text[:12] if text else "main"


def _read_git_origin(git_dir: pathlib.Path) -> str:
    config = git_dir / "config"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    in_origin = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_origin = stripped in {'[remote "origin"]', "[remote 'origin']"}
            continue
        if in_origin and stripped.startswith("url"):
            _key, _sep, value = stripped.partition("=")
            return value.strip()
    return ""


def _source_file_url_from_git(file_path: pathlib.Path) -> str:
    """Return a GitHub blob URL for a local file when it lives under a git origin."""
    file_path = file_path.resolve()
    for parent in [file_path.parent, *file_path.parents]:
        git_dir = parent / ".git"
        if not git_dir.is_dir():
            continue
        try:
            rel = file_path.relative_to(parent).as_posix()
        except ValueError:
            return ""
        remote = _normalize_git_remote_url(_read_git_origin(git_dir))
        if not remote.startswith("https://github.com/"):
            return ""
        branch = _read_git_branch(git_dir)
        return f"{remote}/blob/{branch}/{rel}"
    return ""


def _source_repo_url_from_git(file_path: pathlib.Path) -> str:
    file_path = file_path.resolve()
    for parent in [file_path.parent, *file_path.parents]:
        git_dir = parent / ".git"
        if not git_dir.is_dir():
            continue
        remote = _normalize_git_remote_url(_read_git_origin(git_dir))
        return remote if remote.startswith("https://") else ""
    return ""


def _default_if_none(value: Any, fallback: Any) -> Any:
    """Return fallback if value is None, else value."""
    return fallback if value is None else value


def _str_default(value: Any) -> str:
    """Convert a field default value to string for AppSpec."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _i18n_map(zh_text: Any, en_text: Any = None) -> Dict[str, str]:
    zh = str(zh_text or en_text or "")
    en = str(en_text or zh_text or "")
    return {lang: (zh if lang in {"zh", "zh-Hant"} else en) for lang in I18N_LANGS}


def _sanitize_env_suffix(value: Any) -> str:
    suffix = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "data").upper()).strip("_")
    return suffix or "DATA"


def _strip_internal_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_internal_metadata(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, list):
        return [_strip_internal_metadata(item) for item in value]
    return value


def _normalize_form_field(field: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(field)
    label_zh = normalized.get("labelZh") or normalized.get("envKey") or "配置"
    label_en = normalized.get("labelEn") or str(label_zh)
    if not isinstance(normalized.get("label"), dict):
        normalized["label"] = _i18n_map(label_zh, label_en)
    if str(normalized.get("envKey", "")).startswith("PANEL_APP_PORT_"):
        normalized["required"] = True
        normalized.setdefault("rule", "paramPort")
    return normalized


def _write_default_runtime_files(app_out: pathlib.Path, ver_out: pathlib.Path, version_data: Optional[Dict[str, Any]] = None) -> None:
    (ver_out / "data").mkdir(parents=True, exist_ok=True)
    scripts_dir = ver_out / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    scripts = {
        "init.sh": render_init_script_content(version_data or {}),
        "upgrade.sh": "#!/bin/bash\nset -e\n",
        "uninstall.sh": "#!/bin/bash\nset -e\ndocker-compose down --volumes\n",
    }
    for name, content in scripts.items():
        path = scripts_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


def _write_default_readme(app_out: pathlib.Path, appspec: Dict[str, Any], version: str) -> None:
    title = appspec.get("title") or appspec.get("appKey", "")
    desc = appspec.get("description") or appspec.get("shortDescZh") or ""
    lines = [
        f"# {title}",
        "",
        "## 产品介绍",
        "",
        str(desc),
        "",
        "## 主要功能",
        "",
        "- 具体功能以项目官方文档和当前镜像版本为准。",
        "",
        "## 访问说明",
        "",
        "- 安装后通过应用配置的端口访问服务。",
        "",
        "## Introduction",
        "",
        str(desc),
        "",
        "## Features",
        "",
        "- Refer to the official project documentation for features supported by the selected image version.",
        "",
        "## Information",
        "",
        f"- App Key: {appspec.get('appKey', '')}",
        "- Version: select the required version from the app store version list",
        f"- Type: {appspec.get('type', 'Tool')}",
        "- Source evidence: source-evidence.json",
        "",
    ]
    notes = appspec.get("migrationNotes") or []
    if notes:
        lines.extend(["## Migration Notes", ""])
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    (app_out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _detect_port_envkey(port_entry: Tuple[str, str, str, str], index: int, total: int) -> str:
    """Determine PANEL_APP_PORT_* envKey from a port mapping.

    port_entry: (host_ip_var, host_port_var, container_port)
    """
    _, _, container_port, _ = port_entry
    if index == 0 and total <= 2:
        return "PANEL_APP_PORT_HTTP"
    return f"PANEL_APP_PORT_{container_port}"


def _detect_port_name(port_entry: Tuple[str, str, str, str], index: int) -> str:
    """Human-readable name for a port."""
    _, _, container_port, _ = port_entry
    if index == 0:
        return "HTTP Port"
    return f"Port {container_port}"


def _is_password_key(key: str) -> bool:
    """Heuristic: does env key look like a password/secret?"""
    lower = key.lower()
    return any(kw in lower for kw in ["password", "passwd", "secret", "token", "apikey", "api_key"])


def _split_compose_volume(volume: str) -> Optional[Tuple[str, str, str]]:
    """Split a Linux compose volume string into source, target, and optional mode."""
    parts = str(volume).split(":")
    if len(parts) < 2:
        return None
    source = parts[0].strip()
    target = parts[1].strip()
    mode = ":".join(parts[2:]).strip() if len(parts) > 2 else ""
    if not source or not target:
        return None
    return source, target, mode


# ═══════════════════════════════════════════════════════════════════════
#  BaotaPrecheck
# ═══════════════════════════════════════════════════════════════════════

class BaotaPrecheck:
    """Validates a Baota app directory before import."""

    def validate(self, input_dir: str, include_disabled: bool = False) -> Dict[str, Any]:
        """Run all precheck validations. Returns a report dict."""
        input_path = pathlib.Path(input_dir)
        report: Dict[str, Any] = {
            "errors": [],
            "warnings": [],
            "disabledSourceApp": False,
            "files": {},
            "fields": {},
        }
        self._validate_required_files(input_path, report)
        if report["errors"]:
            return report
        self._validate_app_json_content(input_path, report)
        self._check_appstatus(input_path, report, include_disabled)
        return report

    # ── File existence ────────────────────────────────────────────────

    def _validate_required_files(self, input_path: pathlib.Path, report: Dict[str, Any]) -> None:
        files = {
            "appJson": input_path / "app.json",
            "icon": input_path / "icon.png",
        }
        for label, fp in files.items():
            is_symlink = fp.is_symlink()
            exists = fp.is_file() and not is_symlink
            report["files"][label] = {
                "path": str(fp),
                "present": exists,
                "symlink": is_symlink,
            }
            if not exists:
                code_map = {
                    "appJson": E_BAOTA_APP_JSON_MISSING,
                    "icon": E_BAOTA_ICON_MISSING,
                }
                report["errors"].append({
                    "code": code_map.get(label, E_BAOTA_REQUIRED_FILES),
                    "message": (
                        f"Required file must not be a symlink: {fp.name}"
                        if is_symlink
                        else f"Required file missing: {fp.name}"
                    ),
                    "path": str(fp),
                })

    # ── app.json content ──────────────────────────────────────────────

    def _validate_app_json_content(self, input_path: pathlib.Path, report: Dict[str, Any]) -> None:
        app_json_path = input_path / "app.json"
        try:
            with open(app_json_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            report["errors"].append({
                "code": E_BAOTA_APP_JSON_INVALID,
                "message": f"Cannot parse app.json: {exc}",
                "path": str(app_json_path),
            })
            return
        if not isinstance(data, dict):
            report["errors"].append({
                "code": E_BAOTA_APP_JSON_INVALID,
                "message": "app.json is not a JSON object",
                "path": str(app_json_path),
            })
            return

        # Top-level required keys
        required_keys = [
            "appid", "appname", "apptitle", "apptype", "appTypeCN",
            "appversion", "appdesc", "appstatus", "updateat", "depend",
            "field", "env", "volumes",
        ]
        missing = [k for k in required_keys if k not in data]
        if missing:
            report["errors"].append({
                "code": E_BAOTA_APP_JSON_INVALID,
                "message": f"Missing required keys in app.json: {', '.join(missing)}",
                "path": str(app_json_path),
            })
            return

        app_key = data.get("appname")
        if not _is_safe_app_key(app_key):
            report["errors"].append({
                "code": E_BAOTA_APP_KEY_INVALID,
                "message": "appname must match ^[a-z0-9][a-z0-9_-]{0,127}$",
                "path": str(app_json_path),
            })
            return

        # Version directories
        versions = _expand_versions(data.get("appversion", []))
        report["fields"]["versions"] = versions
        if not versions:
            report["errors"].append({
                "code": E_BAOTA_VERSION_MISSING,
                "message": "No versions defined in appversion[]",
            })
            return
        invalid_versions = [version for version in versions if not _is_safe_version(version)]
        if invalid_versions:
            report["errors"].append({
                "code": E_BAOTA_VERSION_INVALID,
                "message": f"Unsafe version directory names: {', '.join(invalid_versions)}",
            })
            return
        found_any = False
        for ver in versions:
            raw_version_dir = input_path / ver
            if raw_version_dir.is_symlink():
                report["errors"].append({
                    "code": E_BAOTA_VERSION_INVALID,
                    "message": f"Version directory must not be a symlink: {ver}",
                    "path": str(raw_version_dir),
                })
                continue
            try:
                version_dir = _resolve_child(input_path, ver)
            except ValueError as exc:
                report["errors"].append({
                    "code": E_BAOTA_VERSION_INVALID,
                    "message": str(exc),
                    "path": str(raw_version_dir),
                })
                continue
            if not version_dir.is_dir():
                report["warnings"].append({
                    "code": E_BAOTA_VERSION_DIR_MISSING,
                    "message": f"Version directory not found: {ver}",
                    "path": str(version_dir),
                })
                continue
            found_any = True
            compose_file = version_dir / "docker-compose.yml"
            compose_present = compose_file.is_file() and not compose_file.is_symlink()
            report["files"][f"compose_{ver}"] = {
                "path": str(compose_file),
                "present": compose_present,
                "symlink": compose_file.is_symlink(),
            }
            if not compose_present:
                report["errors"].append({
                    "code": E_BAOTA_COMPOSE_MISSING,
                    "message": f"docker-compose.yml missing for version {ver}",
                    "path": str(compose_file),
                })
                continue
            env_file = version_dir / ".env"
            env_present = env_file.is_file() and not env_file.is_symlink()
            report["files"][f"env_{ver}"] = {
                "path": str(env_file),
                "present": env_present,
                "symlink": env_file.is_symlink(),
            }
            if not env_present:
                report["errors"].append({
                    "code": E_BAOTA_ENV_MISSING,
                    "message": f".env missing or is a symlink for version {ver}",
                    "path": str(env_file),
                })
            try:
                _load_compose_document(compose_file)
            except (OSError, ValueError) as exc:
                report["errors"].append({
                    "code": E_BAOTA_COMPOSE_INVALID,
                    "message": str(exc),
                    "path": str(compose_file),
                })
        if not found_any:
            report["errors"].append({
                "code": E_BAOTA_VERSION_DIR_MISSING,
                "message": "No version directories exist for any declared version",
            })

    # ── appstatus ─────────────────────────────────────────────────────

    def _check_appstatus(self, input_path: pathlib.Path, report: Dict[str, Any], include_disabled: bool) -> None:
        app_json_path = input_path / "app.json"
        try:
            with open(app_json_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return
        if data.get("appstatus") == 0:
            report["disabledSourceApp"] = True
            if not include_disabled:
                report["errors"].append({
                    "code": E_BAOTA_DISABLED,
                    "message": "App is disabled (appstatus=0). Use --include-disabled to import anyway.",
                })

    # ── Precheck-only helpers (detached from import) ──────────────────

    @staticmethod
    def validate_standard_fields(fields: List[Dict]) -> List[str]:
        """Return list of standard platform field attrs found in field[]."""
        return [f["attr"] for f in fields if isinstance(f, dict) and f.get("attr") in STANDARD_FIELD_ATTRS]

    @staticmethod
    def validate_standard_env(env_list: List[Dict]) -> List[str]:
        """Return list of standard platform env keys found in env[]."""
        return [e["key"] for e in env_list if isinstance(e, dict) and e.get("key") in STANDARD_ENV_KEYS]

    @staticmethod
    def validate_field_env_relationship(fields: List[Dict], env_list: List[Dict]) -> List[Dict]:
        """Check field.attr matches env.key. Returns list of mismatches."""
        env_keys_lower = {e.get("key", "").lower() for e in env_list if isinstance(e, dict)}
        mismatches = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            attr = f.get("attr", "")
            if attr and attr.lower() not in env_keys_lower:
                mismatches.append({
                    "field_attr": attr,
                    "message": f"No matching env key found for field attr '{attr}'",
                })
        return mismatches


# ═══════════════════════════════════════════════════════════════════════
#  Version Helpers
# ═══════════════════════════════════════════════════════════════════════

def _expand_versions(appversion: List[Dict]) -> List[str]:
    """Expand appversion entries to concrete version directory names."""
    versions: List[str] = []
    for entry in appversion:
        if not isinstance(entry, dict):
            continue
        m_ver = entry.get("m_version")
        if m_ver is None:
            continue
        m_str = str(m_ver)
        s_vers = entry.get("s_version", [])
        if not s_vers or not isinstance(s_vers, list):
            versions.append(m_str)
        else:
            for s in s_vers:
                versions.append(f"{m_str}.{s}")
    return versions


def _select_version(versions: List[str], requested: Optional[str] = None) -> str:
    """Select best version from candidates, preferring 'latest'."""
    if not versions:
        raise ValueError("No version candidates available")
    if requested and requested in versions:
        return requested
    if requested:
        raise ValueError(
            f"Requested version '{requested}' not found. Available: {', '.join(versions)}"
        )
    if "latest" in versions:
        return "latest"
    return versions[0]


# ═══════════════════════════════════════════════════════════════════════
#  BaotaParser
# ═══════════════════════════════════════════════════════════════════════

class BaotaParser:
    """Parses Baota app directory contents."""

    def parse_app_json(self, input_dir: str) -> Dict[str, Any]:
        """Load and return parsed app.json as a dict."""
        fp = pathlib.Path(input_dir) / "app.json"
        with open(fp, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def list_versions(self, input_dir: str) -> List[str]:
        """Return expanded version candidate strings."""
        app_json = self.parse_app_json(input_dir)
        return _expand_versions(app_json.get("appversion", []))

    def select_version(self, versions: List[str], requested: Optional[str] = None) -> str:
        """Select best-matching version from candidates."""
        return _select_version(versions, requested)

    def parse_env_file(self, env_path: str) -> Dict[str, str]:
        """Parse KEY=VALUE .env file into a dict."""
        result: Dict[str, str] = {}
        fp = pathlib.Path(env_path)
        if not fp.is_file():
            return result
        with open(fp, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    result[key] = val
        return result

    def load_compose(self, compose_path: str) -> Dict[str, Any]:
        """Load docker-compose.yml via yaml.safe_load."""
        return _load_compose_document(pathlib.Path(compose_path))


# ═══════════════════════════════════════════════════════════════════════
#  ComposeTransformer
# ═══════════════════════════════════════════════════════════════════════

class ComposeTransformer:
    """Transforms Baota docker-compose.yml to 1Panel-compatible format."""

    def transform(self, input_dir: str, version: str) -> Dict[str, Any]:
        """Main entry: deep-copy compose and apply all transforms."""
        # Phase 1: Parse real Baota compose for variable discovery
        if not _is_safe_version(version):
            raise ValueError(f"Unsafe version directory name: {version}")
        compose_path = _resolve_child(pathlib.Path(input_dir), version, "docker-compose.yml")
        compose = self.load_compose(str(compose_path))

        # Phase 2: Deep copy for transformation
        result = copy.deepcopy(compose)
        manual_review_reasons = self._collect_manual_review_reasons(result)

        # Phase 3: Apply transformations sequentially
        port_map = self._replace_host_ip_ports(result)
        vol_info = self._replace_app_path_volumes(result)
        self._replace_baota_network(result)
        self._replace_created_by_label(result)
        self._inject_container_name(result)
        self._normalize_resource_limits(result)
        unresolved = self._collect_unresolved_variables(result)

        # Phase 4: Attach transformation metadata
        result.setdefault("_transform", {})
        result["_transform"]["portMap"] = port_map
        result["_transform"]["volumeInfo"] = vol_info
        result["_transform"]["unresolved"] = unresolved
        result["_transform"]["manualReviewRequired"] = bool(manual_review_reasons)
        result["_transform"]["manualReviewReasons"] = manual_review_reasons

        return result

    @staticmethod
    def load_compose(compose_path: str) -> Dict[str, Any]:
        """Load and validate a raw Compose document."""
        return _load_compose_document(pathlib.Path(compose_path))

    @staticmethod
    def _collect_manual_review_reasons(compose: Dict[str, Any]) -> List[Dict[str, str]]:
        reasons: List[Dict[str, str]] = []
        for service_name, service in compose.get("services", {}).items():
            for index, port in enumerate(service.get("ports", []) or []):
                if isinstance(port, dict):
                    reasons.append({
                        "code": "compose-long-port-syntax",
                        "path": f"services.{service_name}.ports[{index}]",
                        "message": "Long port syntax requires manual semantic review.",
                    })
            for index, volume in enumerate(service.get("volumes", []) or []):
                if isinstance(volume, dict):
                    reasons.append({
                        "code": "compose-long-volume-syntax",
                        "path": f"services.{service_name}.volumes[{index}]",
                        "message": "Long volume syntax requires manual semantic review.",
                    })
        return reasons

    # ── Port transformation ───────────────────────────────────────────

    def _replace_host_ip_ports(self, compose: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Replace ${HOST_IP}:${PORT}:containerPort → ${PANEL_APP_PORT_*}:containerPort."""
        port_entries: List[Tuple[str, str, str, str]] = []
        services = compose.get("services", {})

        # First pass: collect all port entries
        for _svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            for port_str in svc.get("ports", []) or []:
                entry = self._parse_port_entry(str(port_str))
                if entry:
                    port_entries.append(entry)

        if not port_entries:
            return []

        port_map = []
        for i, entry in enumerate(port_entries):
            host_ip_var, host_port_var, container_port, protocol = entry
            env_key = _detect_port_envkey(entry, i, len(port_entries))
            name = _detect_port_name(entry, i)
            new_port_str = f"${{{env_key}}}:{container_port}{protocol}"
            port_map.append({
                "envKey": env_key,
                "name": name,
                "containerPort": int(container_port),
                "originalVar": host_port_var,
                "hostBindChanged": True,
            })

            # Replace in all services
            for _svc_name, svc in services.items():
                if not isinstance(svc, dict):
                    continue
                ports = svc.get("ports", [])
                if not ports:
                    continue
                new_ports = []
                for ps in ports:
                    ps_str = str(ps)
                    e = self._parse_port_entry(ps_str)
                    if e and e == entry:
                        new_ports.append(new_port_str)
                    else:
                        new_ports.append(ps)
                svc["ports"] = new_ports

        return port_map

    @staticmethod
    def _parse_port_entry(port_str: str) -> Optional[Tuple[str, str, str, str]]:
        """Parse '${HOST_IP}:${PORT}:CP' or '${PORT}:CP' into (host_ip_var, host_port_var, container_port)."""
        port_str = port_str.strip()
        # Remove protocol suffix like /udp, /tcp
        proto = ""
        if "/" in port_str:
            parts = port_str.rsplit("/", 1)
            if parts[1].lower() in ("tcp", "udp"):
                port_str = parts[0]
                proto = "/" + parts[1]

        segments = port_str.split(":")
        if len(segments) == 3:
            host_ip_var = segments[0]
            host_port_var = segments[1]
            container_port = segments[2]
        elif len(segments) == 2:
            host_ip_var = ""
            host_port_var = segments[0]
            container_port = segments[1]
        else:
            return None

        # Validate: host_port_var should be ${...}
        if not host_port_var.startswith("${") or not host_port_var.endswith("}"):
            return None

        host_port_var_name = host_port_var[2:-1]
        return (host_ip_var, host_port_var_name, container_port.split("/")[0], proto)

    # ── Volume transformation ─────────────────────────────────────────

    def _replace_app_path_volumes(self, compose: Dict[str, Any]) -> List[Dict[str, Any]]:
        volume_info: List[Dict[str, Any]] = []
        services = compose.get("services", {})

        app_path_names = set()
        for _svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            for vol in svc.get("volumes", []) or []:
                split = _split_compose_volume(str(vol))
                if split:
                    source, _target, _mode = split
                    if not source.startswith("${APP_PATH}"):
                        continue
                    sub_path = source[len("${APP_PATH}") :].lstrip("/")
                    app_path_names.add((sub_path.split("/", 1)[0] or "data"))
        multiple_app_paths = len(app_path_names) > 1

        for _svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            volumes = svc.get("volumes", [])
            if not volumes:
                continue
            new_volumes = []
            for vol in volumes:
                vol_str = str(vol)
                split = _split_compose_volume(vol_str)
                if split:
                    source, target, mode = split
                    if not source.startswith("${APP_PATH}"):
                        new_volumes.append(vol)
                        continue
                    sub_path = source[len("${APP_PATH}") :].lstrip("/")
                    first_segment, _, rest = sub_path.partition("/")
                    first_segment = first_segment or "data"
                    env_key = f"APP_DATA_DIR_{_sanitize_env_suffix(first_segment)}" if multiple_app_paths else "APP_DATA_DIR"
                    new_host = f"${{{env_key}}}"
                    if rest:
                        new_host = f"{new_host}/{rest}"
                    mode_suffix = f":{mode}" if mode else ""
                    new_vol_str = f"{new_host}:{target}{mode_suffix}"
                    volume_info.append({
                        "original": vol_str,
                        "transformed": new_vol_str,
                        "envKey": env_key,
                        "hostPathChanged": True,
                        "containerPath": target,
                    })
                    new_volumes.append(new_vol_str)
                else:
                    new_volumes.append(vol)
            svc["volumes"] = new_volumes

        return volume_info

    # ── Network transformation ────────────────────────────────────────

    @staticmethod
    def _replace_baota_network(compose: Dict[str, Any]) -> None:
        """Replace baota_net → 1panel-network in services and top-level networks."""
        services = compose.get("services", {})
        for _svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            nets = svc.get("networks", [])
            if isinstance(nets, list):
                svc["networks"] = [
                    "1panel-network" if str(n) == "baota_net" else n
                    for n in nets
                ]
            elif isinstance(nets, dict) and "baota_net" in nets:
                rewritten = {}
                for name, config in nets.items():
                    target = "1panel-network" if str(name) == "baota_net" else name
                    rewritten[target] = config
                svc["networks"] = rewritten
        top_nets = compose.get("networks", {})
        if isinstance(top_nets, dict) and "baota_net" in top_nets:
            top_nets["1panel-network"] = top_nets.pop("baota_net")

    # ── Label transformation ──────────────────────────────────────────

    @staticmethod
    def _replace_created_by_label(compose: Dict[str, Any]) -> None:
        """Replace createdBy: bt_apps → createdBy: Apps."""
        services = compose.get("services", {})
        for _svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            labels = svc.get("labels", {})
            if isinstance(labels, dict) and labels.get("createdBy") == "bt_apps":
                labels["createdBy"] = "Apps"
            elif isinstance(labels, dict) and "createdBy" not in labels:
                labels["createdBy"] = "Apps"
            elif not labels:
                svc["labels"] = {"createdBy": "Apps"}

    # ── Container name injection ──────────────────────────────────────

    @staticmethod
    def _inject_container_name(compose: Dict[str, Any]) -> None:
        """Inject container_name: ${CONTAINER_NAME} for primary, ${CONTAINER_NAME}-<svc> for secondary."""
        services = compose.get("services", {})
        if not services:
            return
        svc_names = list(services.keys())
        for i, name in enumerate(svc_names):
            svc = services[name]
            if not isinstance(svc, dict):
                continue
            if i == 0:
                svc["container_name"] = "${CONTAINER_NAME}"
            else:
                svc["container_name"] = f"${{CONTAINER_NAME}}-{name}"

    # ── Resource limits removal ───────────────────────────────────────

    @staticmethod
    def _normalize_resource_limits(compose: Dict[str, Any]) -> None:
        """Remove deploy.resources.limits referencing ${CPUS} or ${MEMORY_LIMIT}."""
        services = compose.get("services", {})
        for _svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            deploy = svc.get("deploy", {})
            if not isinstance(deploy, dict):
                continue
            resources = deploy.get("resources", {})
            if not isinstance(resources, dict):
                continue
            limits = resources.get("limits", {})
            if not isinstance(limits, dict):
                continue
            # Check if limits reference CPUS/MEMORY_LIMIT
            remove_limits = False
            limit_values = {str(v) for v in limits.values()}
            for ref in ("${CPUS}", "${MEMORY_LIMIT}"):
                if ref in limit_values or any(ref in str(v) for v in limits.values()):
                    remove_limits = True
                    break
            if remove_limits:
                resources.pop("limits", None)
            # Clean up empty deploy block
            if not resources:
                svc.pop("deploy", None)

    # ── Unresolved variable collection ────────────────────────────────

    @staticmethod
    def _collect_unresolved_variables(compose: Dict[str, Any]) -> List[str]:
        """Find all ${VAR} references still in the compose after transforms."""
        compose_str = yaml.dump(compose, default_flow_style=False)
        found = set()
        for match in re.finditer(r"\$\{(\w+)\}", compose_str):
            var_name = match.group(1)
            # Skip known platform-injected vars
            if var_name in ("CONTAINER_NAME",):
                continue
            if var_name.startswith("PANEL_APP_PORT_"):
                continue
            found.add(var_name)
        return sorted(found)


# ═══════════════════════════════════════════════════════════════════════
#  BaotaToAppSpecMapper
# ═══════════════════════════════════════════════════════════════════════

class BaotaToAppSpecMapper:
    """Maps Baota app.json + compose data to a 1Panel AppSpec dict."""

    def build_appspec(
        self,
        app_json: Dict[str, Any],
        version: str,
        compose_data: Dict[str, Any],
        input_dir: str = "",
    ) -> Dict[str, Any]:
        """Build the complete AppSpec JSON."""
        appspec: Dict[str, Any] = {}
        appspec["version"] = version
        self.map_metadata(app_json, appspec)
        self.map_app_type(app_json, appspec)
        self.map_source_evidence(app_json, appspec, input_dir, version)
        self.map_fields(app_json, appspec, compose_data)
        self.map_ports(app_json, compose_data, appspec)
        self.map_volumes(app_json, appspec)
        self.map_compose_override(appspec, compose_data)
        return appspec

    # ── Metadata ──────────────────────────────────────────────────────

    @staticmethod
    def map_metadata(app_json: Dict[str, Any], appspec: Dict[str, Any]) -> None:
        appspec["appKey"] = app_json.get("appname", "")
        appspec["title"] = app_json.get("apptitle", "")
        appspec["description"] = app_json.get("appdesc", "")
        appspec["shortDescZh"] = app_json.get("appdesc", "")
        appspec["home"] = app_json.get("home", "")
        appspec["help"] = app_json.get("help", "")
        appspec["updateat"] = app_json.get("updateat")

    # ── Type ──────────────────────────────────────────────────────────

    @staticmethod
    def map_app_type(app_json: Dict[str, Any], appspec: Dict[str, Any]) -> None:
        baota_type = app_json.get("apptype", "")
        panel_type = BAOTA_TYPE_TO_1PANEL.get(baota_type, _FALLBACK_TYPE)
        if baota_type and baota_type not in BAOTA_TYPE_TO_1PANEL:
            appspec["_typeWarning"] = f"Unknown Baota type '{baota_type}', mapped to '{panel_type}'"
        appspec["type"] = panel_type
        appspec["tag"] = panel_type

    # ── Source evidence ───────────────────────────────────────────────

    @staticmethod
    def map_source_evidence(
        app_json: Dict[str, Any],
        appspec: Dict[str, Any],
        input_dir: str = "",
        version: str = "",
    ) -> None:
        home = app_json.get("home", "")
        help_url = app_json.get("help", "")

        import_source = {
            "type": "baota",
            "appName": app_json.get("appname", ""),
            "version": version,
            "sourcePath": input_dir,
            "declaredHome": home if _is_https_url(home) else "",
            "declaredHelp": help_url if _is_https_url(help_url) else "",
        }
        compose_path = pathlib.Path(input_dir) / version / "docker-compose.yml" if input_dir and version else None
        compose_file_url = _source_file_url_from_git(compose_path) if compose_path and compose_path.is_file() else ""
        source_repo_url = _source_repo_url_from_git(compose_path) if compose_path and compose_path.is_file() else ""
        appspec["importSource"] = import_source
        appspec["evidenceStatus"] = "third_party_only"
        appspec["repository"] = home if _is_https_url(home) else source_repo_url
        appspec["dockerDocs"] = help_url if _is_https_url(help_url) else ""
        appspec["composeFile"] = compose_file_url
        appspec["architectures"] = ["amd64"]
        appspec["architectureEvidence"] = "unverified_default"

    # ── Fields → formFields ───────────────────────────────────────────

    @staticmethod
    def map_fields(
        app_json: Dict[str, Any],
        appspec: Dict[str, Any],
        compose_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Map Baota field[] + env[] to 1Panel formFields."""
        form_fields: List[Dict[str, Any]] = []
        migration_notes: List[str] = []

        fields = app_json.get("field", []) or []
        env_list = app_json.get("env", []) or []
        volumes = app_json.get("volumes", {}) or {}
        transform = compose_data.get("_transform", {}) if isinstance(compose_data, dict) else {}
        port_map = transform.get("portMap", []) if isinstance(transform, dict) else []
        transformed_port_vars = {str(pm.get("originalVar", "")).upper() for pm in port_map if isinstance(pm, dict)}
        field_by_env_key = {
            f.get("attr", "").upper(): f
            for f in fields
            if isinstance(f, dict)
        }

        # Build env key lookup for type inference
        env_type_map: Dict[str, str] = {}
        for e in env_list:
            if isinstance(e, dict):
                env_type_map[e.get("key", "")] = e.get("type", "string")

        # Process field[] entries
        for f in fields:
            if not isinstance(f, dict):
                continue
            attr = f.get("attr", "")
            if attr in STANDARD_FIELD_ATTRS:
                migration_notes.append(f"Skipped platform field: {attr}")
                continue
            if attr.upper() in transformed_port_vars:
                continue

            env_key = attr.upper()
            field_type = f.get("type", "string")
            form_type = BAOTA_FIELD_TYPE_TO_FORM.get(field_type, "text")
            default = f.get("default", "")

            ff: Dict[str, Any] = {
                "envKey": env_key,
                "labelZh": f.get("name", attr),
                "labelEn": attr.replace("_", " ").title(),
                "type": form_type,
                "required": field_type == "port",
                "default": _str_default(default),
                "edit": True,
            }

            if form_type == "number" and field_type == "port":
                ff["rule"] = "paramPort"
            elif form_type == "select":
                ff["values"] = [
                    {"label": "true", "value": "true"},
                    {"label": "false", "value": "false"},
                ]

            if _is_password_key(env_key):
                ff["type"] = "password"
                ff["default"] = ""  # Mask password defaults

            form_fields.append(_normalize_form_field(ff))

        # Process env[] entries not covered by field[]
        field_env_keys = {
            f.get("attr", "").upper()
            for f in fields
            if isinstance(f, dict) and f.get("attr", "") not in STANDARD_FIELD_ATTRS
        }
        for e in env_list:
            if not isinstance(e, dict):
                continue
            key = e.get("key", "")
            if key in STANDARD_ENV_KEYS:
                migration_notes.append(f"Skipped platform env: {key}")
                continue
            if key.upper() in transformed_port_vars:
                continue
            if key.upper() in field_env_keys:
                continue  # Already covered by field[]

            env_type = e.get("type", "string")
            form_type = "number" if env_type == "port" else "text"

            ff = {
                "envKey": key.upper(),
                "labelZh": e.get("desc", key),
                "labelEn": key.replace("_", " ").title(),
                "type": form_type,
                "required": env_type == "port",
                "default": _str_default(e.get("default")),
                "edit": True,
            }
            if env_type == "port":
                ff["rule"] = "paramPort"
            form_fields.append(_normalize_form_field(ff))

        for pm in port_map:
            if not isinstance(pm, dict) or not pm.get("envKey"):
                continue
            original_var = str(pm.get("originalVar", "")).upper()
            source_field = field_by_env_key.get(original_var, {})
            ff = {
                "envKey": pm.get("envKey"),
                "labelZh": source_field.get("name") or pm.get("name") or pm.get("envKey"),
                "labelEn": pm.get("name") or str(pm.get("envKey", "")).replace("_", " ").title(),
                "type": "number",
                "required": True,
                "default": _str_default(source_field.get("default", "")),
                "edit": True,
                "rule": "paramPort",
            }
            form_fields.append(_normalize_form_field(ff))

        # Process volumes → data dir fields
        vol_names = list(volumes.keys()) if isinstance(volumes, dict) else []
        for vname in vol_names:
            vinfo = volumes[vname] if isinstance(volumes, dict) else {}
            vtype = vinfo.get("type", "path") if isinstance(vinfo, dict) else "path"
            if vtype == "file":
                migration_notes.append(f"File volume '{vname}' requires manual review")
                continue
            env_key = f"APP_DATA_DIR_{_sanitize_env_suffix(vname)}" if len(vol_names) > 1 else "APP_DATA_DIR"
            ff = {
                "envKey": env_key,
                "labelZh": vinfo.get("desc", vname) if isinstance(vinfo, dict) else vname,
                "labelEn": f"{vname.title()} Directory",
                "type": "text",
                "required": False,
                "default": f"./data/{vname}",
                "edit": True,
            }
            form_fields.append(_normalize_form_field(ff))

        appspec["formFields"] = form_fields
        if migration_notes:
            appspec["migrationNotes"] = migration_notes

    # ── Ports ─────────────────────────────────────────────────────────

    @staticmethod
    def map_ports(
        app_json: Dict[str, Any],
        compose_data: Dict[str, Any],
        appspec: Dict[str, Any],
    ) -> None:
        """Extract port mappings from compose _transform metadata or app_json."""
        port_list: List[Dict[str, Any]] = []
        transform = compose_data.get("_transform", {}) if isinstance(compose_data, dict) else {}
        port_map = transform.get("portMap", [])
        if port_map:
            for pm in port_map:
                port_list.append({
                    "envKey": pm.get("envKey", ""),
                    "hostDefault": "",
                    "containerPort": pm.get("containerPort", ""),
                    "protocol": "tcp",
                    "primary": port_list == [],
                })
        else:
            # Fallback: extract from env[] with type=port
            env_list = app_json.get("env", []) or []
            for e in env_list:
                if not isinstance(e, dict):
                    continue
                if e.get("type") == "port":
                    env_key = e.get("key", "").upper()
                    if env_key:
                        port_list.append({
                            "envKey": f"PANEL_APP_PORT_{env_key}",
                            "containerPort": "",
                            "protocol": "tcp",
                        })
        appspec["ports"] = port_list

    # ── Volumes ───────────────────────────────────────────────────────

    @staticmethod
    def map_volumes(app_json: Dict[str, Any], appspec: Dict[str, Any]) -> None:
        """Extract volume info from Baota volumes object."""
        volumes = app_json.get("volumes", {}) or {}
        vol_list: List[Dict[str, Any]] = []
        if isinstance(volumes, dict):
            for vname, vinfo in volumes.items():
                if isinstance(vinfo, dict):
                    vol_list.append({
                        "name": vname,
                        "type": vinfo.get("type", "path"),
                        "desc": vinfo.get("desc", ""),
                    })
        appspec["_volumes"] = vol_list

    # ── Compose override ──────────────────────────────────────────────

    @staticmethod
    def map_compose_override(appspec: Dict[str, Any], compose_data: Dict[str, Any]) -> None:
        """Set composeOverride to use the transformed compose."""
        appspec["composeOverride"] = {
            "enabled": True,
            "compose": _strip_internal_metadata(compose_data),
        }
        transform = compose_data.get("_transform", {}) if isinstance(compose_data, dict) else {}
        appspec["manualReviewReasons"] = list(transform.get("manualReviewReasons", []) or [])


# ═══════════════════════════════════════════════════════════════════════
#  ImportRunner
# ═══════════════════════════════════════════════════════════════════════

class ImportRunner:
    """Orchestrates the full Baota → 1Panel import pipeline."""

    def __init__(self):
        self.precheck = BaotaPrecheck()
        self.parser = BaotaParser()
        self.mapper = BaotaToAppSpecMapper()
        self.transformer = ComposeTransformer()

    # ── Single import ─────────────────────────────────────────────────

    def import_one(
        self,
        input_dir: str,
        out_dir: str,
        version: Optional[str] = None,
        include_disabled: bool = False,
        validate: bool = False,
        strict_store_validate: bool = False,
        require_validate: bool = False,
    ) -> Dict[str, Any]:
        """Import a single Baota app directory to 1Panel format."""
        result: Dict[str, Any] = {
            "app": "",
            "version": version or "latest",
            "success": False,
            "stage": "precheck",
            "candidateStatus": "blocked",
            "outputPath": "",
            "declaredVersions": [],
            "importableVersions": [],
            "availableVersions": [],
            "selectedVersion": None,
            "packagedVersions": [],
            "errors": [],
            "warnings": [],
        }

        if require_validate and not (validate or strict_store_validate):
            message = "--require-validate requires --validate or --strict-store-validate"
            result["errorCode"] = E_1PANEL_VALIDATION_MODE_REQUIRED
            result["errors"] = [{"code": E_1PANEL_VALIDATION_MODE_REQUIRED, "message": message}]
            return result

        # 1. Precheck
        precheck_report = self.precheck.validate(input_dir, include_disabled)
        result["precheck"] = precheck_report
        result["warnings"] = list(precheck_report.get("warnings", []))
        result["app"] = pathlib.Path(input_dir).name
        if precheck_report.get("errors"):
            # Filter: only disabled is non-fatal if skipped
            hard_errors = [
                e for e in precheck_report["errors"]
                if e.get("code") != E_BAOTA_DISABLED
            ]
            if hard_errors:
                result["errors"] = hard_errors
                result["errorCode"] = hard_errors[0]["code"]
                return result
            # Only disabled-app error → skip gracefully
            result["success"] = True
            result["skipped"] = True
            result["candidateStatus"] = "skipped"
            result["reason"] = "App is disabled"
            return result

        # 2. Parse
        try:
            app_json = self.parser.parse_app_json(input_dir)
        except Exception as exc:
            result["errors"].append({"code": E_BAOTA_APP_JSON_INVALID, "message": str(exc)})
            return result

        app_name = app_json.get("appname", pathlib.Path(input_dir).name)
        result["app"] = app_name

        versions = _stable_versions(self.parser.list_versions(input_dir))
        result["declaredVersions"] = versions
        result["availableVersions"] = versions
        input_path = pathlib.Path(input_dir)
        result["importableVersions"] = [
            item
            for item in versions
            if (_resolve_child(input_path, item) / "docker-compose.yml").is_file()
        ]
        try:
            selected_version = self.parser.select_version(versions, version)
        except ValueError as exc:
            result["errors"].append({"code": E_BAOTA_VERSION_DIR_MISSING, "message": str(exc)})
            return result
        result["version"] = selected_version
        result["selectedVersion"] = selected_version

        # 3. Transform compose
        try:
            compose_data = self.transformer.transform(input_dir, selected_version)
        except Exception as exc:
            result["errors"].append({"code": E_BAOTA_COMPOSE_MISSING, "message": str(exc)})
            return result

        # 4. Build AppSpec
        appspec = self.mapper.build_appspec(app_json, selected_version, compose_data, input_dir)
        result["appspec"] = appspec

        # 5. Write output
        try:
            output_path = self._write_output(appspec, compose_data, input_dir, out_dir, selected_version)
        except BaotaEvidenceError as exc:
            result["errors"].append({"code": E_BAOTA_EVIDENCE_INVALID, "message": str(exc)})
            result["errorCode"] = E_BAOTA_EVIDENCE_INVALID
            return result
        except (OSError, ValueError) as exc:
            result["errors"].append({"code": E_BAOTA_OUTPUT_PATH_INVALID, "message": str(exc)})
            result["errorCode"] = E_BAOTA_OUTPUT_PATH_INVALID
            return result
        result["outputPath"] = output_path
        result["packagedVersions"] = self._list_packaged_versions(output_path, versions)
        result["success"] = True
        result["stage"] = "converted_candidate"

        delivery = evaluate_baota_delivery_readiness(appspec, compose_data)
        result["delivery"] = delivery
        result["deliveryReady"] = delivery["ready"]
        result["candidateStatus"] = "delivery_ready" if delivery["ready"] else "manual_review_required"

        if strict_store_validate:
            result["stage"] = "strict_store_validate"
            validation = run_strict_store_validation(output_path, selected_version)
            result["validation"] = validation
            if validation.get("failed"):
                result["errors"].append({
                    "code": "E_1PANEL_STRICT_VALIDATE_FAILED",
                    "message": "strict-store validation failed",
                })
            if not delivery["ready"]:
                result["errors"].extend({
                    "code": "E_BAOTA_DELIVERY_BLOCKED",
                    "message": blocker["message"],
                } for blocker in delivery["blockers"])
            if validation.get("failed") or not delivery["ready"]:
                result["success"] = False
        elif validate:
            result["stage"] = "basic_validate"
            validation = self._validate_output(output_path)
            validation["mode"] = "basic"
            result["validation"] = validation
            if require_validate and validation.get("failed"):
                result["success"] = False
                result["errors"] = [{"code": "E_1PANEL_VALIDATE_FAILED", "message": err} for err in validation.get("errors", [])]
            else:
                result["stage"] = "converted_candidate"

        return result

    # ── Batch import ──────────────────────────────────────────────────

    def import_batch(
        self,
        input_dir: str,
        out_dir: str,
        version: Optional[str] = None,
        include_disabled: bool = False,
        validate: bool = False,
        strict_store_validate: bool = False,
        require_validate: bool = False,
    ) -> Dict[str, Any]:
        """Batch import all subdirectories with app.json."""
        input_path = pathlib.Path(input_dir)
        candidates = sorted(
            p for p in input_path.iterdir()
            if p.is_dir() and (p / "app.json").is_file()
        )
        results: List[Dict[str, Any]] = []
        success_count = 0
        failed_count = 0

        for cand in candidates:
            item = self.import_one(
                str(cand), out_dir, version,
                include_disabled, validate, strict_store_validate, require_validate,
            )
            results.append(item)
            if item.get("success") and not item.get("skipped"):
                success_count += 1
            elif not item.get("success"):
                failed_count += 1

        return {
            "results": results,
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(candidates),
        }

    # ── Output writing ────────────────────────────────────────────────

    def _write_output(
        self,
        appspec: Dict[str, Any],
        compose_data: Dict[str, Any],
        input_dir: str,
        out_dir: str,
        version: str,
    ) -> str:
        """Write 1Panel v2 app directory structure."""
        app_key = appspec.get("appKey", "unknown")
        if not _is_safe_app_key(app_key):
            raise ValueError(f"Unsafe app key: {app_key}")
        if not _is_safe_version(version):
            raise ValueError(f"Unsafe version directory name: {version}")
        output_root = pathlib.Path(out_dir).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        raw_app_out = output_root / app_key
        raw_ver_out = raw_app_out / version
        _assert_safe_output_targets(
            output_root,
            _generated_output_targets(raw_app_out, raw_ver_out),
        )
        app_out = _resolve_child(output_root, app_key)
        ver_out = _resolve_child(app_out, version)
        evidence_path = app_out / "source-evidence.json"
        existing_evidence = _load_existing_evidence(evidence_path)
        ver_out.mkdir(parents=True, exist_ok=True)
        (ver_out / "data").mkdir(parents=True, exist_ok=True)

        # Root data.yml
        root_data = self._build_root_data_yml(appspec)
        with open(app_out / "data.yml", "w", encoding="utf-8") as fh:
            yaml.dump(root_data, fh, default_flow_style=False, allow_unicode=True)

        # Version data.yml
        ver_data = self._build_version_data_yml(appspec)
        with open(ver_out / "data.yml", "w", encoding="utf-8") as fh:
            yaml.dump(ver_data, fh, default_flow_style=False, allow_unicode=True)
        _write_default_runtime_files(app_out, ver_out, ver_data)

        # Transformed docker-compose.yml (strip _transform metadata)
        clean_compose = {k: v for k, v in compose_data.items() if not k.startswith("_")}
        with open(ver_out / "docker-compose.yml", "w", encoding="utf-8") as fh:
            yaml.dump(clean_compose, fh, default_flow_style=False, allow_unicode=True)

        # .env.sample
        self._write_env_sample(ver_out, clean_compose, appspec)

        _write_default_readme(app_out, appspec, version)

        # source-evidence.json
        evidence = self._build_source_evidence(appspec)
        evidence = _merge_baota_source_evidence(existing_evidence, evidence, version)
        with open(evidence_path, "w", encoding="utf-8") as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=2)

        # Copy icon → logo.png
        src_icon = pathlib.Path(input_dir) / "icon.png"
        if src_icon.is_file():
            import shutil
            shutil.copy2(str(src_icon), str(app_out / "logo.png"))

        return str(app_out)

    @staticmethod
    def _validate_output(app_dir: str) -> Dict[str, Any]:
        app_path = pathlib.Path(app_dir)
        errors: List[str] = []
        required_root = ["data.yml", "README.md", "logo.png", "source-evidence.json"]
        for name in required_root:
            fp = app_path / name
            if not fp.is_file():
                errors.append(f"Missing: {name}")
        logo = app_path / "logo.png"
        if logo.is_file() and logo.stat().st_size == 0:
            errors.append("Invalid: logo.png is empty")
        try:
            root_data = yaml.safe_load((app_path / "data.yml").read_text(encoding="utf-8")) or {}
            desc = root_data.get("additionalProperties", {}).get("description")
            if not isinstance(desc, dict) or not all(lang in desc for lang in I18N_LANGS):
                errors.append("Invalid: root additionalProperties.description i18n")
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"Invalid: root data.yml: {exc}")
        for version_dir in sorted(p for p in app_path.iterdir() if p.is_dir()):
            required_version = [
                "data.yml",
                "docker-compose.yml",
                ".env.sample",
                "data",
                "scripts/init.sh",
                "scripts/upgrade.sh",
                "scripts/uninstall.sh",
            ]
            for rel in required_version:
                fp = version_dir / rel
                if rel == "data":
                    if not fp.is_dir():
                        errors.append(f"Missing: {version_dir.name}/{rel}")
                elif not fp.is_file():
                    errors.append(f"Missing: {version_dir.name}/{rel}")
            try:
                ver_data = yaml.safe_load((version_dir / "data.yml").read_text(encoding="utf-8")) or {}
                fields = ver_data.get("additionalProperties", {}).get("formFields", []) or []
                field_keys = {field.get("envKey") for field in fields if isinstance(field, dict)}
                for field in fields:
                    if not isinstance(field, dict) or not isinstance(field.get("label"), dict):
                        errors.append(f"Invalid: {version_dir.name}/data.yml formField label")
            except (OSError, yaml.YAMLError) as exc:
                errors.append(f"Invalid: {version_dir.name}/data.yml: {exc}")
                field_keys = set()
            try:
                compose_text = (version_dir / "docker-compose.yml").read_text(encoding="utf-8")
                env_text = (version_dir / ".env.sample").read_text(encoding="utf-8")
                compose_vars = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", compose_text))
                env_keys = {line.split("=", 1)[0] for line in env_text.splitlines() if "=" in line}
                for env_key in sorted(compose_vars - env_keys):
                    errors.append(f"Missing env.sample variable: {env_key}")
                for env_key in sorted(compose_vars - field_keys - {"CONTAINER_NAME"}):
                    errors.append(f"Missing formField variable: {env_key}")
            except OSError as exc:
                errors.append(f"Invalid: compose/env validation failed: {exc}")
        return {"valid": not errors, "errors": errors, "failed": bool(errors)}

    @staticmethod
    def _list_packaged_versions(app_dir: str, declared_versions: List[str]) -> List[str]:
        app_path = pathlib.Path(app_dir)
        app_root = app_path.resolve()

        def is_packaged(path: pathlib.Path) -> bool:
            if path.is_symlink():
                return False
            try:
                path.resolve().relative_to(app_root)
            except ValueError:
                return False
            return path.is_dir() and (path / "docker-compose.yml").is_file()

        declared = [
            version
            for version in _stable_versions(declared_versions)
            if is_packaged(app_path / version)
        ]
        extras = sorted(
            (
                path.name
                for path in app_path.iterdir()
                if is_packaged(path)
                and _is_safe_version(path.name)
                and path.name not in declared
            ),
            key=_version_sort_key,
        )
        return [*declared, *extras]

    # ── data.yml builders ─────────────────────────────────────────────

    @staticmethod
    def _build_root_data_yml(appspec: Dict[str, Any]) -> Dict[str, Any]:
        tag = appspec.get("tag", "Tool")
        return {
            "name": appspec.get("appKey", ""),
            "tags": [tag],
            "title": appspec.get("title", ""),
            "description": appspec.get("shortDescZh", ""),
            "additionalProperties": {
                "key": appspec.get("appKey", ""),
                "name": appspec.get("title", ""),
                "tags": [tag],
                "type": appspec.get("type", "Tool"),
                "website": appspec.get("home", ""),
                "document": appspec.get("help", ""),
                "github": appspec.get("repository", ""),
                "shortDescZh": appspec.get("shortDescZh", ""),
                "shortDescEn": appspec.get("description", ""),
                "description": _i18n_map(appspec.get("shortDescZh", ""), appspec.get("description", "")),
                "crossVersionUpdate": False,
                "limit": 0,
                "architectures": appspec.get("architectures", ["amd64"]),
            },
        }

    @staticmethod
    def _build_version_data_yml(appspec: Dict[str, Any]) -> Dict[str, Any]:
        form_fields = [_normalize_form_field(field) for field in appspec.get("formFields", [])]
        return {
            "additionalProperties": {
                "formFields": form_fields,
            },
        }

    @staticmethod
    def _build_source_evidence(appspec: Dict[str, Any]) -> Dict[str, Any]:
        evidence: Dict[str, Any] = {
            "repository": appspec.get("repository", ""),
            "dockerDocs": appspec.get("dockerDocs", ""),
            "composeFile": appspec.get("composeFile", ""),
            "evidenceStatus": appspec.get("evidenceStatus", "third_party_only"),
            "architectures": appspec.get("architectures", ["amd64"]),
            "architectureEvidence": appspec.get("architectureEvidence", "unverified_default"),
            "importSource": appspec.get("importSource", {}),
        }
        notes = appspec.get("migrationNotes", [])
        if notes:
            evidence["migrationNotes"] = notes
        return evidence

    # ── .env.sample ───────────────────────────────────────────────────

    @staticmethod
    def _write_env_sample(ver_out: pathlib.Path, compose_data: Dict[str, Any], appspec: Optional[Dict[str, Any]] = None) -> None:
        """Generate .env.sample with all variables referenced in compose."""
        compose_str = yaml.dump(compose_data, default_flow_style=False)
        var_names = set()
        for match in re.finditer(r"\$\{(\w+)\}", compose_str):
            var_names.add(match.group(1))

        defaults: Dict[str, Any] = {}
        if isinstance(appspec, dict):
            for field in appspec.get("formFields", []) or []:
                if not isinstance(field, dict):
                    continue
                env_key = field.get("envKey")
                if env_key:
                    defaults[str(env_key)] = field.get("default", "")

        lines = []
        for vn in sorted(var_names):
            if vn == "CONTAINER_NAME":
                lines.append(f"{vn}=")
            elif vn in defaults:
                lines.append(f"{vn}={_str_default(defaults[vn])}")
            elif vn == "APP_DATA_DIR":
                lines.append(f"{vn}=./data")
            elif vn.startswith("APP_DATA_DIR_"):
                suffix = vn[len("APP_DATA_DIR_"):].lower()
                lines.append(f"{vn}=./data/{suffix}")
            elif vn.startswith("PANEL_APP_PORT_"):
                lines.append(f"{vn}=")
            else:
                lines.append(f"{vn}=")

        if not lines:
            lines.append("# No variables detected")
        lines.append("")

        with open(ver_out / ".env.sample", "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))


# ── Module entry (for simple tests) ───────────────────────────────────

if __name__ == "__main__":
    print("baota_import_lib.py loaded successfully.")
    print(f"  Classes: BaotaPrecheck, BaotaParser, BaotaToAppSpecMapper, ComposeTransformer, ImportRunner")
    print(f"  Error codes: {E_BAOTA_REQUIRED_FILES}, {E_BAOTA_APP_JSON_MISSING}, ...")
