#!/usr/bin/env python3
"""Submission profiles and run-only evidence locations for app packages."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shlex

import yaml

from appstore_i18n import iter_fields
from runtime_script_utils import collect_runtime_path_fields

PROFILES = ("third-party", "official")
VERSION_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
FALLBACK_LOGO_SOURCE = "https://github.com/okxlin/1panel-app-adapter/blob/1af3a585d413bbafccd1231512ad6f07839fe8b1/assets/default-logo.svg"
SELECTED_VERSION = re.compile(r"(?im)^\s*(?:[-*#]+\s*)?(?:\*\*)?(?:version|app(?:lication)? version|image version|版本|当前版本|应用版本|镜像版本)(?:\*\*)?\s*[:：]\s*(?:\*\*|`)?v?\d+(?:\.\d+)+")


def readme_version_findings(app_dir: Path) -> list[str]:
    findings = []
    for name in ("README.md", "README_en.md"):
        path = app_dir / name
        if path.is_file() and SELECTED_VERSION.search(path.read_text(encoding="utf-8")):
            findings.append(f"{name} contains a fixed selected-version line; keep version selection in package metadata")
    return findings


def noop_lifecycle_findings(version_dir: Path) -> list[str]:
    """Flag comments, simple no-op statements, and literal echo-only hooks."""
    scripts = version_dir / "scripts"
    if scripts.is_symlink():
        return []  # The validator reports unsafe paths separately; do not follow them.
    findings = []
    for name in ("init.sh", "upgrade.sh", "uninstall.sh"):
        path = scripts / name
        if path.is_symlink() or not path.is_file():
            continue
        commands = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                literal_line = not re.search(r"[$`\\<>|&()]", line)
                lexer = shlex.shlex(line, posix=True, punctuation_chars=";")
                lexer.whitespace_split = True
                command = []
                for token in lexer:
                    if token == ";":
                        commands.append((command, literal_line))
                        command = []
                    else:
                        command.append(token)
                commands.append((command, literal_line))
        except ValueError:
            continue  # Unknown shell syntax is outside this deliberately narrow lint.
        for command, literal_line in commands:
            if not command or tuple(command) in {(':',), ('true',), ('exit',), ('exit', '0')}:
                continue
            if command[0] == "set" and re.fullmatch(r"-[efu]+|-[efu]*o pipefail", " ".join(command[1:])):
                continue
            if command[0] == "echo" and literal_line:
                continue
            break
        else:
            findings.append(f"scripts/{name} contains no lifecycle operation; omit unused hooks")
    return findings


def check_profile(value: str) -> str:
    if value not in PROFILES:
        raise ValueError(f"unknown submission profile: {value}")
    return value


def _app_path(app_dir: Path) -> Path:
    app_dir = app_dir.absolute()
    if not app_dir.name or app_dir.name in {".", ".."}:
        raise ValueError("app directory must be a named child of the output root")
    if app_dir.is_symlink():
        raise ValueError(f"app directory must not be a symlink: {app_dir}")
    return app_dir.parent.resolve() / app_dir.name


def _check_file_path(path: Path, root: Path) -> Path:
    current = root
    for part in path.relative_to(root).parts:
        if part == "..":
            raise ValueError(f"path escapes output root: {path}")
        current = current / part
        if current.is_symlink():
            raise ValueError(f"path must not traverse a symlink: {current}")
    if path.exists() and not path.is_file():
        raise ValueError(f"expected a regular file: {path}")
    return path


def evidence_path(app_dir: Path) -> Path:
    app_dir = _app_path(app_dir)
    return _check_file_path(app_dir.parent / ".evidence" / app_dir.name / "source-evidence.json", app_dir.parent)


def find_evidence(app_dir: Path) -> Path:
    app_dir = _app_path(app_dir)
    external = evidence_path(app_dir)
    legacy = _check_file_path(app_dir / "source-evidence.json", app_dir.parent)
    if external.is_file() and legacy.is_file() and external.read_bytes() != legacy.read_bytes():
        raise ValueError("conflicting external and in-package source evidence; select --source-evidence explicitly")
    return external if external.exists() else legacy if legacy.exists() else external


def ensure_evidence_parent(app_dir: Path) -> Path:
    target = evidence_path(app_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def check_output_profile(app_dir: Path, profile: str, version: str | None = None, allow_existing: bool = False) -> None:
    """Reject mode switches and accidental replacement before any output write."""
    check_profile(profile)
    app_dir = _app_path(app_dir)
    existing = find_evidence(app_dir)
    if existing.is_file():
        payload = json.loads(existing.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("existing source evidence must contain an object")
        previous = payload.get("submissionProfile")
        if previous is not None and previous != profile:
            raise ValueError(f"submission profile conflicts with existing {previous!r} output; use a new output directory")
    if app_dir.is_dir() and profile == "official":
        for child in app_dir.iterdir():
            if child.is_dir() and (child / ".env.sample").exists():
                raise ValueError("official profile conflicts with existing in-package .env.sample; use a new output directory")
    if version is not None:
        sample_path(app_dir, version, profile)
        version_dir = app_dir / version
        if not allow_existing and version_dir.exists() and (not version_dir.is_dir() or any(version_dir.iterdir())):
            raise ValueError(f"target version already exists: {version_dir}; use a new output directory or version")


def profile_data(data: dict, profile: str) -> dict:
    check_profile(profile)
    result = copy.deepcopy(data)
    if profile == "official":
        directories = {item["envKey"] for item in collect_runtime_path_fields(result)}
        for field in iter_fields((result.get("additionalProperties") or {}).get("formFields")):
            if field.get("envKey") in directories:
                field["disabled"] = True
                field["edit"] = False
    return result


def sample_path(app_dir: Path, version: str, profile: str) -> Path:
    check_profile(profile)
    if not isinstance(version, str) or not VERSION_COMPONENT.fullmatch(version):
        raise ValueError(f"unsafe version directory name: {version!r}")
    app_dir = _app_path(app_dir)
    if profile == "official":
        path = evidence_path(app_dir).parent / version / ".env.sample"
    else:
        path = app_dir / version / ".env.sample"
    return _check_file_path(path, app_dir.parent)


def bundled_logo_evidence(app_dir: Path, evidence: dict) -> dict:
    """Deliver the MIT notice in the README; MIT does not require the source SVG."""
    notice = (Path(__file__).resolve().parents[1] / "assets/default-logo.LICENSE.txt").read_text(encoding="utf-8").strip()
    readme = app_dir / "README.md"
    content = readme.read_text(encoding="utf-8")
    if notice not in content:
        content = content.rstrip() + "\n\n<details>\n<summary>默认图标许可 / Fallback icon license (MIT)</summary>\n\n" + notice + "\n\n</details>\n"
        readme.write_text(content, encoding="utf-8")
    result = copy.deepcopy(evidence)
    logo_hash = hashlib.sha256((app_dir / "logo.png").read_bytes()).hexdigest()
    result["logoEvidence"] = {"source": FALLBACK_LOGO_SOURCE, "license": "MIT", "sha256": logo_hash}
    redistribution = result.setdefault("redistributionEvidence", {"status": "verified"})
    required = redistribution.setdefault("requiredFiles", [])
    if "README.md" not in required:
        required.append("README.md")
    materials = redistribution.setdefault("materials", [])
    materials[:] = [item for item in materials if item.get("path") != "README.md"]
    materials.append({"path": "README.md", "sha256": hashlib.sha256(readme.read_bytes()).hexdigest(), "purpose": "MIT notice for the bundled fallback icon"})
    assets = redistribution.setdefault("assets", [])
    assets[:] = [item for item in assets if item.get("path") != "logo.png"]
    assets.append({"path": "logo.png", **result["logoEvidence"], "requiredFiles": ["README.md"]})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_dir", type=Path)
    parser.add_argument("--find-evidence", action="store_true")
    parser.add_argument("--evidence-path", action="store_true")
    parser.add_argument("--prepare-evidence", action="store_true")
    parser.add_argument("--check-output", action="store_true")
    parser.add_argument("--allow-existing", action="store_true")
    parser.add_argument("--submission-profile", choices=PROFILES, default="third-party")
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.check_output:
        check_output_profile(args.app_dir, args.submission_profile, args.version, args.allow_existing)
    elif args.find_evidence:
        print(find_evidence(args.app_dir))
    elif args.prepare_evidence:
        print(ensure_evidence_parent(args.app_dir))
    elif args.evidence_path:
        print(evidence_path(args.app_dir))
    elif args.version:
        app_dir = _app_path(args.app_dir)
        target = sample_path(app_dir, args.version, args.submission_profile)
        path = _check_file_path(app_dir / args.version / "data.yml", app_dir.parent)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        transformed = profile_data(data, args.submission_profile)
        ensure_evidence_parent(app_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        if transformed != data:
            path.write_text(yaml.safe_dump(transformed, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(target)
    else:
        parser.error("select an evidence operation or --version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
