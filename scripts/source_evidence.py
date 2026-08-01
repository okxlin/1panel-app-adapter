#!/usr/bin/env python3
"""Validate required and optional source-evidence.json fields."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HTTPS_URL = re.compile(r"https://[^\s]+")
COMMIT_ID = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-fA-F]{64}")
OCI_PLATFORM = re.compile(
    r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*" r"(?:/[a-z0-9][a-z0-9._-]*)?"
)
LOGO_SOURCE = re.compile(r"(?:https://[^\s]+|bundled:[^\s]+)")


def _optional_object(payload: dict[str, Any], key: str, errors: list[str]):
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        errors.append(f"{key} must be a non-empty object when present")
        return None
    return value


def validate_source_evidence(payload: Any, *, require_urls: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["must contain a JSON object"]

    if require_urls:
        for key in ("repository", "dockerDocs", "composeFile"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"missing key: {key}")
            elif HTTPS_URL.fullmatch(value.strip()) is None:
                errors.append(f"key must be https URL: {key}")

    source_revision = _optional_object(payload, "sourceRevision", errors)
    if source_revision is not None:
        tag = source_revision.get("tag")
        commit = source_revision.get("commit")
        if tag is not None and (not isinstance(tag, str) or not tag.strip()):
            errors.append("sourceRevision.tag must be a non-empty string")
        if commit is not None and (
            not isinstance(commit, str) or COMMIT_ID.fullmatch(commit.strip()) is None
        ):
            errors.append(
                "sourceRevision.commit must be a full 40- or 64-hex commit identifier"
            )
        if tag is None and commit is None:
            errors.append("sourceRevision must include tag or commit")

    image_evidence = _optional_object(payload, "imageEvidence", errors)
    if image_evidence is not None:
        digest = image_evidence.get("digest")
        platforms = image_evidence.get("platforms")
        if digest is not None and (
            not isinstance(digest, str)
            or IMAGE_DIGEST.fullmatch(digest.strip()) is None
        ):
            errors.append(
                "imageEvidence.digest must be a sha256 digest with 64 hex characters"
            )
        if platforms is not None and (
            not isinstance(platforms, list)
            or not platforms
            or any(
                not isinstance(item, str)
                or OCI_PLATFORM.fullmatch(item.strip()) is None
                for item in platforms
            )
        ):
            errors.append(
                "imageEvidence.platforms must be a non-empty list of OCI platform strings"
            )
        if digest is None and platforms is None:
            errors.append("imageEvidence must include digest or platforms")

    license_evidence = _optional_object(payload, "licenseEvidence", errors)
    if license_evidence is not None:
        spdx = license_evidence.get("spdx")
        url = license_evidence.get("url")
        if spdx is not None and (not isinstance(spdx, str) or not spdx.strip()):
            errors.append("licenseEvidence.spdx must be a non-empty string")
        if url is not None and (
            not isinstance(url, str) or HTTPS_URL.fullmatch(url.strip()) is None
        ):
            errors.append("licenseEvidence.url must be an https URL")
        if spdx is None and url is None:
            errors.append("licenseEvidence must include spdx or url")

    logo_evidence = _optional_object(payload, "logoEvidence", errors)
    if logo_evidence is not None:
        source = logo_evidence.get("source")
        logo_license = logo_evidence.get("license")
        sha256 = logo_evidence.get("sha256")
        if not isinstance(source, str) or LOGO_SOURCE.fullmatch(source.strip()) is None:
            errors.append(
                "logoEvidence.source must be an https URL or bundled:<repo-relative-path>"
            )
        if logo_license is not None and (
            not isinstance(logo_license, str) or not logo_license.strip()
        ):
            errors.append("logoEvidence.license must be a non-empty string")
        if sha256 is not None and (
            not isinstance(sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", sha256.strip()) is None
        ):
            errors.append("logoEvidence.sha256 must contain 64 hex characters")

    return errors


def load_source_evidence(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate source-evidence.json")
    parser.add_argument("evidence_file")
    args = parser.parse_args()
    try:
        payload = load_source_evidence(Path(args.evidence_file))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[A][FAIL] source-evidence.json invalid JSON: {exc}")
        return 1

    errors = validate_source_evidence(payload)
    for error in errors:
        print(f"[A][FAIL] source-evidence.json {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
