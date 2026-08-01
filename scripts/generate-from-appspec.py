#!/usr/bin/env python3
"""
Generate 1Panel v2 app directory from an AppSpec JSON file.

Extended to support Baota import fields:
  - ports[]          → generated port formFields
  - formFields[]     → used directly in version data.yml
  - importSource     → included in source-evidence.json
  - composeOverride  → use provided compose instead of generating one

Backward-compatible: old AppSpec format (without these fields) still works.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── PyYAML ────────────────────────────────────────────────────────────
try:
    import yaml
except ImportError:
    sys.stderr.write("Error: PyYAML is required. Install with: pip install pyyaml\n")
    raise SystemExit(1)

from baota_import_lib import (
    _assert_safe_output_targets,
    _generated_output_targets,
    _i18n_map,
    _is_safe_app_key,
    _is_safe_version,
    _load_existing_evidence,
    _merge_baota_source_evidence,
    _normalize_form_field,
    _sanitize_env_suffix,
    _resolve_child,
    _strip_internal_metadata,
    _write_default_readme,
    evaluate_baota_delivery_readiness,
    run_strict_store_validation,
)
from runtime_script_utils import UNINSTALL_SCRIPT, collect_runtime_path_fields, write_init_script
from source_evidence import load_source_evidence, validate_source_evidence

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

I18N_LANGS = ["en", "zh", "zh-Hant", "ja", "ko", "ru", "ms", "pt-br"]
TYPE_ALIASES = {
    "ai": "AI",
    "bi": "BI",
    "crm": "CRM",
    "database": "Database",
    "devops": "DevOps",
    "email": "Email",
    "game": "Game",
    "media": "Media",
    "middleware": "Middleware",
    "runtime": "Runtime",
    "security": "Security",
    "server": "Server",
    "storage": "Storage",
    "tool": "Tool",
    "tools": "Tool",
    "website": "Website",
}


def _canonical_type(value: Any, fallback: str = "Tool") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return TYPE_ALIASES.get(text.lower(), text)


def _split_volume(value: str) -> Optional[Dict[str, str]]:
    parts = value.split(":")
    if len(parts) < 2:
        return None
    host = parts[0].strip()
    target = parts[1].strip()
    mode = ":".join(parts[2:]).strip() if len(parts) > 2 else ""
    if not host or not target:
        return None
    return {"source": host, "target": target, "mode": mode}


def _volume_name(source: str, target: str) -> str:
    for candidate in (source, target):
        cleaned = re.sub(r"^\$\{[^}]+\}/?", "", candidate.strip())
        cleaned = cleaned.strip().strip("/")
        if cleaned and cleaned not in {".", ".."}:
            name = pathlib.PurePosixPath(cleaned).name
            if name:
                return _sanitize_env_suffix(name).lower()
    return "data"


def _normalize_appspec(raw_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy and Baota AppSpec shapes into the direct generator shape."""
    spec = dict(raw_spec)

    source_evidence = spec.get("sourceEvidence")
    if isinstance(source_evidence, dict):
        spec.setdefault("repository", source_evidence.get("repository", ""))
        spec.setdefault("dockerDocs", source_evidence.get("dockerDocs", ""))
        spec.setdefault("composeFile", source_evidence.get("composeFile", ""))
        spec.setdefault("evidenceStatus", source_evidence.get("evidenceStatus", "official_partial"))
        spec.setdefault("architectures", source_evidence.get("architectures", ["amd64"]))
        spec.setdefault("architectureEvidence", source_evidence.get("architectureEvidence", "unverified_default"))
        for field in (
            "sourceRevision",
            "imageEvidence",
            "licenseEvidence",
            "logoEvidence",
            "redistributionEvidence",
        ):
            if field in source_evidence:
                spec.setdefault(field, source_evidence[field])

    evidence_errors = validate_source_evidence(spec, require_urls=False)
    if evidence_errors:
        raise ValueError("invalid source evidence: " + "; ".join(evidence_errors))

    spec["type"] = _canonical_type(spec.get("type", "Tool"))
    spec["tag"] = _canonical_type(spec.get("tag") or spec.get("type") or "Tool")
    if not spec.get("shortDescZh"):
        spec["shortDescZh"] = spec.get("description", "")

    if not spec.get("ports") and spec.get("port") and spec.get("targetPort"):
        spec["ports"] = [{
            "envKey": "PANEL_APP_PORT_HTTP",
            "name": "HTTP Port",
            "hostDefault": spec.get("port"),
            "containerPort": spec.get("targetPort"),
            "protocol": "tcp",
            "primary": True,
        }]

    if not spec.get("_volumes") and isinstance(spec.get("volumes"), list):
        volume_entries: List[Dict[str, Any]] = []
        raw_volumes = [item for item in spec.get("volumes", []) if isinstance(item, str)]
        multiple = len(raw_volumes) > 1
        for item in raw_volumes:
            parsed = _split_volume(item)
            if not parsed:
                continue
            name = _volume_name(parsed["source"], parsed["target"])
            env_key = f"APP_DATA_DIR_{_sanitize_env_suffix(name)}" if multiple else "APP_DATA_DIR"
            volume_entries.append({
                "name": name,
                "type": "path",
                "desc": f"{name.title()} Directory",
                "source": parsed["source"],
                "target": parsed["target"],
                "mode": parsed["mode"],
                "envKey": env_key,
            })
        if volume_entries:
            spec["_volumes"] = volume_entries

    return spec


# ═══════════════════════════════════════════════════════════════════════
#  AppSpec Generator
# ═══════════════════════════════════════════════════════════════════════

class AppSpecGenerator:
    """Generates a 1Panel v2 app directory from an AppSpec JSON dict."""

    def __init__(self, spec: Dict[str, Any], out_dir: str, validate: bool = False):
        self.spec = _normalize_appspec(spec)
        self.app_key = self.spec.get("appKey", "unknown")
        self.version = self.spec.get("version", "latest")
        if not _is_safe_app_key(self.app_key):
            raise ValueError(f"Unsafe app key: {self.app_key}")
        if not _is_safe_version(self.version):
            raise ValueError(f"Unsafe version directory name: {self.version}")
        self.out_dir = pathlib.Path(out_dir).resolve()
        raw_app_dir = self.out_dir / self.app_key
        raw_version_dir = raw_app_dir / self.version
        _assert_safe_output_targets(
            self.out_dir,
            _generated_output_targets(raw_app_dir, raw_version_dir),
        )
        self.app_dir = _resolve_child(self.out_dir, self.app_key)
        self.version_dir = _resolve_child(self.app_dir, self.version)
        self._existing_source_evidence = _load_existing_evidence(
            self.app_dir / "source-evidence.json"
        )

    def generate(self) -> str:
        """Generate the complete 1Panel v2 app directory. Returns output path."""
        collect_runtime_path_fields(self._build_version_data())
        self._ensure_dirs()
        self._write_root_data_yml()
        self._write_version_data_yml()
        self._write_compose()
        self._write_env_sample()
        self._write_logo()
        self._write_source_evidence()
        self._write_readme()
        self._write_runtime_files()
        return str(self.app_dir)

    def _ensure_dirs(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.version_dir.mkdir(parents=True, exist_ok=True)
        (self.version_dir / "data").mkdir(parents=True, exist_ok=True)

    # ── Root data.yml ─────────────────────────────────────────────────

    def _write_root_data_yml(self) -> None:
        tag = _canonical_type(self.spec.get("tag", "Tool"))
        root = {
            "name": self.app_key,
            "tags": [tag],
            "title": self.spec.get("title", self.app_key),
            "description": self.spec.get("shortDescZh", self.spec.get("description", "")),
            "additionalProperties": {
                "key": self.app_key,
                "name": self.spec.get("title", self.app_key),
                "tags": [tag],
                "type": _canonical_type(self.spec.get("type", "Tool")),
                "website": self.spec.get("home", ""),
                "document": self.spec.get("help", ""),
                "github": self.spec.get("repository", ""),
                "shortDescZh": self.spec.get("shortDescZh", ""),
                "shortDescEn": self.spec.get("description", ""),
                "description": _i18n_map(self.spec.get("shortDescZh", ""), self.spec.get("description", "")),
                "crossVersionUpdate": False,
                "limit": self.spec.get("limit", 0),
                "architectures": self.spec.get("architectures", ["amd64"]),
            },
        }
        self._write_yaml(self.app_dir / "data.yml", root)

    # ── Version data.yml ──────────────────────────────────────────────

    def _write_version_data_yml(self) -> None:
        self._write_yaml(self.version_dir / "data.yml", self._build_version_data())

    def _build_version_data(self) -> Dict[str, Any]:
        form_fields = self._build_form_fields()
        ver_data: Dict[str, Any] = {
            "additionalProperties": {},
        }
        if form_fields:
            ver_data["additionalProperties"]["formFields"] = form_fields
        return ver_data

    def _build_form_fields(self) -> List[Dict[str, Any]]:
        """Build formFields from spec formFields[] + ports[]."""
        ff: List[Dict[str, Any]] = []

        # 1. Use spec.formFields[] directly if present (Baota import)
        spec_ff = self.spec.get("formFields", [])
        if spec_ff:
            ff.extend(spec_ff)

        # 2. Generate port formFields from spec.ports[]
        ports = self.spec.get("ports", [])
        for port in ports:
            if not isinstance(port, dict):
                continue
            # Check if port envKey already exists in formFields
            env_key = port.get("envKey", "")
            if env_key and any(f.get("envKey") == env_key for f in ff):
                continue
            pm = self._port_to_formfield(port)
            if pm:
                ff.append(pm)

        # 3. Volume formFields (only if not already present from spec)
        volumes = self.spec.get("_volumes", [])
        for vol in volumes:
            if not isinstance(vol, dict):
                continue
            vff = self._volume_to_formfield(vol, len(volumes))
            if vff:
                env_key = vff.get("envKey", "")
                if env_key and any(f.get("envKey") == env_key for f in ff):
                    continue
                ff.append(vff)

        return [
            _normalize_form_field(field)
            for field in ff
            if field.get("envKey") != "CONTAINER_NAME"
        ]

    @staticmethod
    def _port_to_formfield(port: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        env_key = port.get("envKey", "")
        if not env_key:
            return None
        return {
            "envKey": env_key,
            "labelZh": port.get("name", "端口"),
            "labelEn": port.get("name", "Port"),
            "type": "number",
            "required": True,
            "default": port.get("hostDefault", port.get("containerPort", "")),
            "edit": True,
            "rule": "paramPort",
        }

    @staticmethod
    def _volume_to_formfield(vol: Dict[str, Any], total_volumes: int) -> Optional[Dict[str, Any]]:
        name = vol.get("name", "data")
        vtype = vol.get("type", "path")
        if vtype == "file":
            return None  # File volumes don't get formFields
        env_key = vol.get("envKey") or (f"APP_DATA_DIR_{_sanitize_env_suffix(name)}" if total_volumes > 1 else "APP_DATA_DIR")
        default = vol.get("source") if str(vol.get("source", "")).startswith(".") else f"./data/{name}"
        return {
            "envKey": env_key,
            "labelZh": vol.get("desc", name),
            "labelEn": f"{name.title()} Directory",
            "type": "text",
            "required": False,
            "default": default,
            "edit": True,
        }

    # ── docker-compose.yml ────────────────────────────────────────────

    def _write_compose(self) -> None:
        compose_override = self.spec.get("composeOverride", {})
        if isinstance(compose_override, dict) and compose_override.get("enabled"):
            compose_data = compose_override.get("compose", {})
            compose_data = self._normalize_compose_override(compose_data)
            self._write_yaml(self.version_dir / "docker-compose.yml", compose_data)
            return

        # Generate minimal compose
        compose = self._generate_basic_compose()
        self._write_yaml(self.version_dir / "docker-compose.yml", compose)

    def _generate_basic_compose(self) -> Dict[str, Any]:
        image = self.spec.get("image", f"{self.app_key}:latest")
        ports_list = []
        for port in self.spec.get("ports", []) or []:
            env_key = port.get("envKey", "")
            container_port = port.get("containerPort", "")
            if env_key and container_port:
                ports_list.append(f"${{{env_key}}}:{container_port}")

        service: Dict[str, Any] = {
            "image": image,
            "container_name": "${CONTAINER_NAME}",
            "restart": "always",
            "labels": {"createdBy": "Apps"},
            "networks": ["1panel-network"],
        }
        if ports_list:
            service["ports"] = ports_list

        volumes = self.spec.get("_volumes", [])
        if volumes:
            vol_list = []
            for v in volumes:
                if isinstance(v, dict) and v.get("type", "path") == "path":
                    vname = v.get("name", "data")
                    env_key = v.get("envKey") or (f"APP_DATA_DIR_{_sanitize_env_suffix(vname)}" if len(volumes) > 1 else "APP_DATA_DIR")
                    target = v.get("target") or f"/data/{vname}"
                    mode = f":{v.get('mode')}" if v.get("mode") else ""
                    vol_list.append(f"${{{env_key}}}:{target}{mode}")
            if vol_list:
                service["volumes"] = vol_list

        return {
            "services": {self.app_key: service},
            "networks": {
                "1panel-network": {"external": True},
            },
        }

    def _normalize_compose_override(self, compose_data: Dict[str, Any]) -> Dict[str, Any]:
        compose = _strip_internal_metadata(compose_data if isinstance(compose_data, dict) else {})
        compose.pop("version", None)
        services = compose.get("services")
        if isinstance(services, dict):
            first = True
            for service_name, service in services.items():
                if not isinstance(service, dict):
                    continue
                service.setdefault("container_name", "${CONTAINER_NAME}" if first else f"${{CONTAINER_NAME}}-{service_name}")
                labels = service.get("labels")
                if not isinstance(labels, dict):
                    labels = {}
                labels["createdBy"] = "Apps"
                service["labels"] = labels
                networks = service.get("networks")
                if networks is None:
                    service["networks"] = ["1panel-network"]
                first = False
        if not isinstance(compose.get("networks"), dict):
            compose["networks"] = {}
        compose["networks"].setdefault("1panel-network", {"external": True})
        return compose

    # ── .env.sample ───────────────────────────────────────────────────

    def _write_env_sample(self) -> None:
        compose_path = self.version_dir / "docker-compose.yml"
        compose_text = compose_path.read_text(encoding="utf-8") if compose_path.is_file() else ""
        compose_vars = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", compose_text))
        lines = [f"CONTAINER_NAME={self.app_key}-compose-check"]
        for f_item in self._build_form_fields():
            env_key = f_item.get("envKey", "")
            default = f_item.get("default", "")
            if env_key and env_key != "CONTAINER_NAME":
                lines.append(f"{env_key}={default}")
        for port in self.spec.get("ports", []) or []:
            env_key = port.get("envKey", "")
            default = port.get("hostDefault", "")
            if env_key and env_key not in {l.split("=")[0] for l in lines}:
                lines.append(f"{env_key}={default}")
        existing = {line.split("=")[0] for line in lines if "=" in line}
        for env_key in sorted(compose_vars - existing):
            lines.append(f"{env_key}=")
        lines.append("")
        with open(self.version_dir / ".env.sample", "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

    # ── source-evidence.json ──────────────────────────────────────────

    def _write_source_evidence(self) -> None:
        evidence: Dict[str, Any] = {
            "repository": self.spec.get("repository", ""),
            "dockerDocs": self.spec.get("dockerDocs", ""),
            "composeFile": self.spec.get("composeFile", "(generated)"),
            "evidenceStatus": self.spec.get("evidenceStatus", "third_party_only"),
            "architectures": self.spec.get("architectures", ["amd64"]),
            "architectureEvidence": self.spec.get("architectureEvidence", "unverified_default"),
        }

        for field in (
            "sourceRevision",
            "imageEvidence",
            "licenseEvidence",
            "logoEvidence",
            "redistributionEvidence",
        ):
            value = self.spec.get(field)
            if isinstance(value, dict) and value:
                evidence[field] = value

        import_source = self.spec.get("importSource")
        if import_source:
            evidence["importSource"] = import_source

        notes = self.spec.get("migrationNotes")
        if notes:
            evidence["migrationNotes"] = notes

        evidence_path = self.app_dir / "source-evidence.json"
        evidence = _merge_baota_source_evidence(
            self._existing_source_evidence, evidence, self.version
        )
        with open(evidence_path, "w", encoding="utf-8") as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=2)

    # ── README.md ─────────────────────────────────────────────────────

    def _write_readme(self) -> None:
        _write_default_readme(self.app_dir, self.spec, self.version)

    def _write_logo(self) -> None:
        explicit_logo = self.spec.get("logoPath") or self.spec.get("logo")
        explicit_logo_path = pathlib.Path(str(explicit_logo)) if explicit_logo else None
        source_path = self.spec.get("importSource", {}).get("sourcePath", "")
        source_icon = pathlib.Path(source_path) / "icon.png" if source_path else None
        default_logo = pathlib.Path(__file__).resolve().parent.parent / "assets" / "default-logo.png"
        default_license = default_logo.with_name("default-logo.LICENSE.txt")
        default_source = default_logo.with_name("default-logo.svg")
        target = self.app_dir / "logo.png"
        used_default = False
        if explicit_logo_path and explicit_logo_path.is_file():
            shutil.copy2(str(explicit_logo_path), str(target))
        elif source_icon and source_icon.is_file():
            shutil.copy2(str(source_icon), str(target))
        elif default_logo.is_file() and default_license.is_file() and default_source.is_file():
            shutil.copy2(str(default_logo), str(target))
            used_default = True
        elif not target.exists():
            target.write_bytes(b"")

        delivered_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if used_default:
            notice = self.app_dir / "ASSET-LICENSES" / "default-logo.txt"
            source = self.app_dir / "assets" / "default-logo.svg"
            _assert_safe_output_targets(
                self.out_dir, [notice.parent, notice, source.parent, source]
            )
            notice.parent.mkdir(parents=True, exist_ok=True)
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(default_license), str(notice))
            shutil.copy2(str(default_source), str(source))
            notice_hash = hashlib.sha256(notice.read_bytes()).hexdigest()
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            self.spec["logoEvidence"] = {
                "source": "bundled:assets/default-logo.svg",
                "license": "MIT",
                "sha256": delivered_hash,
            }
            existing_redistribution = self.spec.get("redistributionEvidence")
            if isinstance(existing_redistribution, dict):
                redistribution_status = existing_redistribution.get(
                    "status", "unresolved"
                )
                required_files = list(existing_redistribution.get("requiredFiles", []))
                materials = [
                    item
                    for item in existing_redistribution.get("materials", [])
                    if isinstance(item, dict)
                    and item.get("path")
                    not in {
                        "ASSET-LICENSES/default-logo.txt",
                        "assets/default-logo.svg",
                    }
                ]
                assets = [
                    item
                    for item in existing_redistribution.get("assets", [])
                    if isinstance(item, dict) and item.get("path") != "logo.png"
                ]
            else:
                redistribution_status = "verified"
                required_files = []
                materials = []
                assets = []
            if "ASSET-LICENSES/default-logo.txt" not in required_files:
                required_files.append("ASSET-LICENSES/default-logo.txt")
            if "assets/default-logo.svg" not in required_files:
                required_files.append("assets/default-logo.svg")
            materials.append({
                "path": "ASSET-LICENSES/default-logo.txt",
                "sha256": notice_hash,
                "purpose": "default logo license",
            })
            materials.append({
                "path": "assets/default-logo.svg",
                "sha256": source_hash,
                "purpose": "default logo source",
            })
            assets.append({
                "path": "logo.png",
                "source": "bundled:assets/default-logo.svg",
                "license": "MIT",
                "sha256": delivered_hash,
                "requiredFiles": [
                    "ASSET-LICENSES/default-logo.txt",
                    "assets/default-logo.svg",
                ],
            })
            self.spec["redistributionEvidence"] = {
                "status": redistribution_status,
                "requiredFiles": required_files,
                "materials": materials,
                "assets": assets,
            }
        elif not isinstance(self.spec.get("redistributionEvidence"), dict):
            logo_evidence = self.spec.get("logoEvidence", {})
            logo_evidence = logo_evidence if isinstance(logo_evidence, dict) else {}
            asset = {
                "path": "logo.png",
                "source": logo_evidence.get("source", "unverified:logo.png"),
                "sha256": delivered_hash,
                "requiredFiles": [],
            }
            if logo_evidence.get("license"):
                asset["license"] = logo_evidence["license"]
            self.spec["redistributionEvidence"] = {
                "status": "unresolved",
                "requiredFiles": [],
                "assets": [asset],
            }

    def _write_runtime_files(self) -> None:
        scripts_dir = self.version_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        scripts = {
            "upgrade.sh": "#!/bin/bash\nset -e\n",
            "uninstall.sh": UNINSTALL_SCRIPT,
        }
        write_init_script(self.version_dir / "data.yml", scripts_dir / "init.sh")
        for name, content in scripts.items():
            path = scripts_dir / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _write_yaml(path: pathlib.Path, data: Dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate 1Panel v2 app directory from AppSpec JSON / 从 AppSpec JSON 生成 1Panel v2 应用目录"
    )
    parser.add_argument("--spec", required=True, help="Path to AppSpec JSON file / AppSpec JSON 文件路径")
    parser.add_argument("--out-dir", default="./1panel-apps", help="Output directory / 输出目录")
    parser.add_argument("--validate", action="store_true", help="Run basic validation after generation / 生成后执行基础校验")
    parser.add_argument("--strict-store-validate", action="store_true", help="Run strict-store validation after generation / 生成后执行严格商店校验")
    parser.add_argument("--require-validate", action="store_true", help="Exit non-zero if validation fails / 校验失败时返回非零退出码")
    parser.add_argument("--report", help="Write run report JSON to this file path / 将运行报告写入 JSON 文件")
    return parser.parse_args()


def load_spec(spec_path: str) -> Dict[str, Any]:
    with open(spec_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_output(app_dir: str) -> Dict[str, Any]:
    """Basic validation: check required files exist."""
    app_path = pathlib.Path(app_dir)
    errors = []
    nested_app = app_path / app_path.name
    if (
        (nested_app / "data.yml").is_file()
        and (nested_app / "source-evidence.json").is_file()
        and any(path.is_dir() for path in nested_app.iterdir())
    ):
        errors.append(f"Invalid: duplicate nested app root: {nested_app}")
    checks = {
        "data.yml": app_path / "data.yml",
        "README.md": app_path / "README.md",
        "logo.png": app_path / "logo.png",
        "source-evidence.json": app_path / "source-evidence.json",
    }
    for label, fp in checks.items():
        if not fp.is_file():
            errors.append(f"Missing: {label}")
    logo = app_path / "logo.png"
    if logo.is_file() and logo.stat().st_size == 0:
        errors.append("Invalid: logo.png is empty")

    evidence_path = app_path / "source-evidence.json"
    if evidence_path.is_file():
        try:
            evidence = load_source_evidence(evidence_path)
            for error in validate_source_evidence(
                evidence,
                require_urls=False,
                artifact_root=app_path,
            ):
                errors.append(f"Invalid: source-evidence.json {error}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid: source-evidence.json invalid JSON: {exc}")

    # Check version dir
    subdirs = [
        d
        for d in app_path.iterdir()
        if d.is_dir() and (d / "data.yml").is_file()
    ]
    for sd in subdirs:
        ver_checks = {
            f"{sd.name}/data.yml": sd / "data.yml",
            f"{sd.name}/docker-compose.yml": sd / "docker-compose.yml",
            f"{sd.name}/.env.sample": sd / ".env.sample",
            f"{sd.name}/data": sd / "data",
            f"{sd.name}/scripts/init.sh": sd / "scripts" / "init.sh",
            f"{sd.name}/scripts/upgrade.sh": sd / "scripts" / "upgrade.sh",
            f"{sd.name}/scripts/uninstall.sh": sd / "scripts" / "uninstall.sh",
        }
        for label, fp in ver_checks.items():
            if label.endswith("/data"):
                if not fp.is_dir():
                    errors.append(f"Missing: {label}")
            elif not fp.is_file():
                errors.append(f"Missing: {label}")

        try:
            root_data = yaml.safe_load((app_path / "data.yml").read_text(encoding="utf-8")) or {}
            desc = root_data.get("additionalProperties", {}).get("description")
            if not isinstance(desc, dict) or not all(lang in desc for lang in I18N_LANGS):
                errors.append("Invalid: root additionalProperties.description i18n")
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"Invalid: root data.yml: {exc}")

        try:
            ver_data = yaml.safe_load((sd / "data.yml").read_text(encoding="utf-8")) or {}
            fields = ver_data.get("additionalProperties", {}).get("formFields", []) or []
            field_keys = {field.get("envKey") for field in fields if isinstance(field, dict)}
            for field in fields:
                if not isinstance(field.get("label"), dict):
                    errors.append(f"Invalid: {sd.name}/data.yml formField label for {field.get('envKey', '')}")
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"Invalid: {sd.name}/data.yml: {exc}")
            field_keys = set()

        try:
            compose_text = (sd / "docker-compose.yml").read_text(encoding="utf-8")
            env_text = (sd / ".env.sample").read_text(encoding="utf-8")
            env_keys = {line.split("=", 1)[0] for line in env_text.splitlines() if "=" in line}
            compose_vars = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", compose_text))
            for env_key in sorted(compose_vars - env_keys):
                errors.append(f"Missing env.sample variable: {env_key}")
            for env_key in sorted(compose_vars - field_keys - {"CONTAINER_NAME"}):
                errors.append(f"Missing formField variable: {env_key}")
        except OSError as exc:
            errors.append(f"Invalid: env closure check failed: {exc}")

    return {"valid": len(errors) == 0, "errors": errors, "failed": len(errors) > 0}


def write_report(path_value: str, report: Dict[str, Any]) -> None:
    path = pathlib.Path(path_value).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spec": str(pathlib.Path(args.spec).resolve()),
        "outputDir": str(pathlib.Path(args.out_dir)),
        "validateRequested": bool(args.validate or args.strict_store_validate),
        "strictStoreValidate": bool(args.strict_store_validate),
        "requireValidate": bool(args.require_validate),
        "status": "failed",
        "step": "init",
        "appDir": "",
        "validation": None,
        "strictValidation": None,
        "delivery": None,
        "error": "",
    }

    def finish(code: int) -> int:
        if args.report:
            write_report(args.report, report)
        return code

    if args.require_validate and not (args.validate or args.strict_store_validate):
        report["error"] = "--require-validate requires --validate or --strict-store-validate"
        print(f"Error: {report['error']}", file=sys.stderr)
        return finish(EXIT_FAILURE)

    # Load spec
    try:
        report["step"] = "load_spec"
        spec = load_spec(args.spec)
    except (json.JSONDecodeError, OSError) as exc:
        report["error"] = f"Cannot load spec: {exc}"
        print(f"Error: Cannot load spec: {exc}", file=sys.stderr)
        return finish(EXIT_FAILURE)

    # Generate
    try:
        report["step"] = "generate"
        generator = AppSpecGenerator(spec, args.out_dir, args.validate)
        output_path = generator.generate()
    except Exception as exc:
        report["error"] = f"Generation failed: {exc}"
        print(f"Error: Generation failed: {exc}", file=sys.stderr)
        return finish(EXIT_FAILURE)

    print(f"Generated: {output_path}")
    report["appDir"] = output_path
    report["delivery"] = evaluate_baota_delivery_readiness(
        generator.spec,
        app_dir=pathlib.Path(output_path),
        require_strict_validation=True,
    )

    # Validate
    if args.validate:
        report["step"] = "validate"
        validation = validate_output(output_path)
        report["validation"] = {
            "valid": validation.get("valid"),
            "failed": validation.get("failed"),
            "errors": validation.get("errors", []),
        }
        if validation["errors"]:
            print(f"Validation: {len(validation['errors'])} error(s)")
            for err in validation["errors"]:
                print(f"  - {err}")
        else:
            print("Validation: OK")
        if args.require_validate and validation["failed"]:
            report["error"] = "validation failed"
            return finish(EXIT_FAILURE)

    if args.strict_store_validate:
        report["step"] = "strict_store_validate"
        strict_validation = run_strict_store_validation(output_path, emit_output=True)
        report["strictValidation"] = {
            "mode": strict_validation.get("mode"),
            "validator": strict_validation.get("validator"),
            "valid": strict_validation.get("valid"),
            "failed": strict_validation.get("failed"),
            "errors": strict_validation.get("errors", []),
            "returncode": strict_validation.get("returncode"),
        }
        report["delivery"] = evaluate_baota_delivery_readiness(
            generator.spec,
            app_dir=pathlib.Path(output_path),
            strict_validation=strict_validation,
            require_strict_validation=True,
        )
        if strict_validation["failed"]:
            report["error"] = "strict-store validation failed"
            return finish(EXIT_FAILURE)
        if not report["delivery"]["ready"]:
            report["error"] = "delivery gates are not satisfied"
            print(f"Error: {report['error']}", file=sys.stderr)
            return finish(EXIT_FAILURE)

    report["status"] = "ok" if report["delivery"]["ready"] else "generated_candidate"
    report["step"] = "done"
    return finish(EXIT_SUCCESS)


if __name__ == "__main__":
    raise SystemExit(main())
