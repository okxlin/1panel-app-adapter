#!/usr/bin/env python3
"""Validate required and optional source-evidence.json fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

HTTPS_URL = re.compile(r"https://[^\s]+")
COMMIT_ID = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-fA-F]{64}")
PINNED_IMAGE_REFERENCE = re.compile(
    r"[^\s]+@(?P<digest>sha256:[0-9a-fA-F]{64})"
)
SERVICE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
VERSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+&-]{0,127}")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
UNBRACED_ENV = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
OCI_PLATFORM = re.compile(
    r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*" r"(?:/[a-z0-9][a-z0-9._-]*)?"
)
LOGO_SOURCE = re.compile(r"(?:https://[^\s]+|bundled:[^\s]+)")
ASSET_SOURCE = re.compile(r"(?:https://[^\s]+|bundled:[^\s]+|unverified:[^\s]+)")
SHA256 = re.compile(r"[0-9a-fA-F]{64}")
REDISTRIBUTION_STATUSES = {"verified", "unresolved"}
PLACEHOLDER_LICENSES = {
    "n/a",
    "na",
    "none",
    "placeholder",
    "tbd",
    "todo",
    "unknown",
    "unspecified",
    "unverified",
}


def _optional_object(payload: dict[str, Any], key: str, errors: list[str]):
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        errors.append(f"{key} must be a non-empty object when present")
        return None
    return value


def _validate_image_fields(
    value: dict[str, Any],
    field: str,
    errors: list[str],
    *,
    require_digest: bool = False,
) -> None:
    digest = value.get("digest")
    platforms = value.get("platforms")
    if digest is not None and (
        not isinstance(digest, str)
        or IMAGE_DIGEST.fullmatch(digest.strip()) is None
    ):
        errors.append(f"{field}.digest must be a sha256 digest with 64 hex characters")
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
            f"{field}.platforms must be a non-empty list of OCI platform strings"
        )
    if require_digest and digest is None:
        errors.append(f"{field}.digest is required")
    elif digest is None and platforms is None:
        errors.append(f"{field} must include digest or platforms")


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if ENV_NAME.fullmatch(key) is None:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _split_parameter_expression(expression: str) -> tuple[str, str | None, str]:
    match = ENV_NAME.match(expression)
    if match is None:
        raise ValueError(f"unsupported Compose image interpolation: ${{{expression}}}")
    name = match.group(0)
    remainder = expression[match.end():]
    if not remainder:
        return name, None, ""
    for operator in (":-", ":?", ":+", "-", "?", "+"):
        if remainder.startswith(operator):
            return name, operator, remainder[len(operator):]
    raise ValueError(f"unsupported Compose image interpolation: ${{{expression}}}")


def _resolve_compose_image(reference: str, env: dict[str, str]) -> str:
    def find_parameter_end(text: str, start: int) -> int:
        depth = 1
        cursor = start
        while cursor < len(text):
            if text.startswith("$$", cursor):
                cursor += 2
                continue
            if text.startswith("${", cursor):
                depth += 1
                cursor += 2
                continue
            if text[cursor] == "}":
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        raise ValueError("unterminated Compose image interpolation")

    def resolve_braced(text: str) -> str:
        output: list[str] = []
        cursor = 0
        while cursor < len(text):
            if text.startswith("$$", cursor):
                output.append("$")
                cursor += 2
                continue
            if not text.startswith("${", cursor):
                output.append(text[cursor])
                cursor += 1
                continue
            end = find_parameter_end(text, cursor + 2)
            expression = text[cursor + 2:end]
            name, operator, operand = _split_parameter_expression(expression)
            is_set = name in env
            value = env.get(name, "")
            is_nonempty = is_set and value != ""
            if operator is None:
                if not is_set:
                    raise ValueError(f"Compose image variable is unset: {name}")
                replacement = value
            elif operator == ":-":
                replacement = value if is_nonempty else resolve_braced(operand)
            elif operator == "-":
                replacement = value if is_set else resolve_braced(operand)
            elif operator in {":?", "?"}:
                valid = is_nonempty if operator == ":?" else is_set
                if not valid:
                    raise ValueError(f"Compose image variable is required: {name}")
                replacement = value
            elif operator == ":+":
                replacement = resolve_braced(operand) if is_nonempty else ""
            else:
                replacement = resolve_braced(operand) if is_set else ""
            output.append(replacement)
            cursor = end + 1
        return "".join(output)

    resolved = resolve_braced(reference)

    def replace_unbraced(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ValueError(f"Compose image variable is unset: {name}")
        return env[name]

    resolved = UNBRACED_ENV.sub(replace_unbraced, resolved)
    if not resolved or resolved != resolved.strip() or re.search(r"\s", resolved):
        raise ValueError("resolved Compose image reference must be one non-empty token")
    return resolved


def load_compose_images(compose_path: Path, env_path: Path) -> dict[str, str]:
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("services"), dict):
        raise ValueError("Compose must contain a services object")
    env = _read_env_file(env_path)
    images: dict[str, str] = {}
    for service, config in payload["services"].items():
        if not isinstance(config, dict) or "image" not in config:
            continue
        reference = config.get("image")
        if not isinstance(reference, str):
            raise ValueError(f"Compose service image must be a string: {service}")
        images[str(service)] = _resolve_compose_image(reference, env)
    return images


def _is_safe_package_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if "\\" in value or "\x00" in value or re.match(r"^[A-Za-z]:", value):
        return False
    path = Path(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in value.split("/"))


def _is_placeholder_license(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() in PLACEHOLDER_LICENSES


def _validate_path_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    paths: list[str] = []
    for index, item in enumerate(value):
        if not _is_safe_package_path(item):
            errors.append(f"{field}[{index}] must be a safe package-relative path")
        else:
            paths.append(item)
    return paths


def _artifact_file(root: Path, relative_path: str) -> tuple[Path | None, str | None]:
    root = root.resolve()
    current = root
    for component in relative_path.split("/"):
        current = current / component
        if current.is_symlink():
            return None, f"must not traverse a symlink: {relative_path}"
    try:
        current.resolve().relative_to(root)
    except ValueError:
        return None, f"escapes artifact root: {relative_path}"
    if not current.is_file():
        return None, f"is missing from artifact: {relative_path}"
    return current, None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_redistribution_delivery(
    payload: Any,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Return report-ready redistribution evidence bound to delivered files."""
    evidence = payload.get("redistributionEvidence") if isinstance(payload, dict) else None
    review: dict[str, Any] = {
        "redistributionStatus": "missing",
        "requiredFiles": [],
        "deliveredFiles": [],
        "materials": [],
        "assets": [],
        "issues": [],
    }
    if not isinstance(evidence, dict):
        return review

    review["redistributionStatus"] = evidence.get("status", "missing")
    root = Path(artifact_root).resolve() if artifact_root is not None else None
    required_files: list[str] = []
    raw_required = evidence.get("requiredFiles", [])
    if isinstance(raw_required, list):
        required_files.extend(item for item in raw_required if _is_safe_package_path(item))

    raw_assets = evidence.get("assets", [])
    assets = raw_assets if isinstance(raw_assets, list) else []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_required = asset.get("requiredFiles", [])
        if isinstance(asset_required, list):
            required_files.extend(item for item in asset_required if _is_safe_package_path(item))

    review["requiredFiles"] = list(dict.fromkeys(required_files))
    if root is not None:
        for relative_path in review["requiredFiles"]:
            material, error = _artifact_file(root, relative_path)
            if material is not None:
                review["deliveredFiles"].append(relative_path)
            else:
                review["issues"].append({
                    "code": "missing-redistribution-material",
                    "message": error,
                })

    raw_materials = evidence.get("materials", [])
    materials = raw_materials if isinstance(raw_materials, list) else []
    material_paths: set[str] = set()
    for index, material in enumerate(materials):
        if not isinstance(material, dict):
            continue
        item = {
            key: material[key]
            for key in ("path", "sha256", "purpose")
            if key in material
        }
        item["delivered"] = False
        item["hashMatches"] = False
        path_value = material.get("path")
        if _is_safe_package_path(path_value):
            material_paths.add(path_value)
        if root is not None and _is_safe_package_path(path_value):
            material_path, error = _artifact_file(root, path_value)
            if material_path is None:
                review["issues"].append({
                    "code": "invalid-redistribution-material",
                    "message": error,
                })
            else:
                item["delivered"] = True
                expected_hash = material.get("sha256")
                actual_hash = _sha256_file(material_path)
                item["actualSha256"] = actual_hash
                if material_path.stat().st_size == 0:
                    review["issues"].append({
                        "code": "invalid-redistribution-material",
                        "message": f"required redistribution material is empty: {path_value}",
                    })
                item["hashMatches"] = (
                    isinstance(expected_hash, str)
                    and expected_hash.lower() == actual_hash
                )
                if not item["hashMatches"]:
                    review["issues"].append({
                        "code": "invalid-redistribution-material",
                        "message": f"redistributionEvidence.materials[{index}].sha256 does not match delivered {path_value}",
                    })
        review["materials"].append(item)

    for relative_path in review["requiredFiles"]:
        if relative_path not in material_paths:
            review["issues"].append({
                "code": "invalid-redistribution-material",
                "message": f"required redistribution material lacks hash evidence: {relative_path}",
            })

    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            continue
        item = {
            key: asset[key]
            for key in ("path", "source", "license", "sha256", "requiredFiles")
            if key in asset
        }
        item["delivered"] = False
        item["hashMatches"] = False
        path_value = asset.get("path")
        if root is not None and _is_safe_package_path(path_value):
            asset_path, error = _artifact_file(root, path_value)
            if asset_path is None:
                review["issues"].append({
                    "code": "invalid-redistribution-asset",
                    "message": error,
                })
            else:
                item["delivered"] = True
                expected_hash = asset.get("sha256")
                actual_hash = _sha256_file(asset_path)
                item["actualSha256"] = actual_hash
                if asset_path.stat().st_size == 0:
                    review["issues"].append({
                        "code": "invalid-redistribution-asset",
                        "message": f"redistribution asset is empty: {path_value}",
                    })
                item["hashMatches"] = (
                    isinstance(expected_hash, str)
                    and expected_hash.lower() == actual_hash
                )
                if not item["hashMatches"]:
                    review["issues"].append({
                        "code": "invalid-redistribution-asset",
                        "message": f"redistributionEvidence.assets[{index}].sha256 does not match delivered {path_value}",
                    })
        review["assets"].append(item)

    if root is not None:
        delivered_logo = root / "logo.png"
        tracked_assets = {
            asset.get("path")
            for asset in assets
            if isinstance(asset, dict)
        }
        if (delivered_logo.exists() or delivered_logo.is_symlink()) and "logo.png" not in tracked_assets:
            review["issues"].append({
                "code": "untracked-redistribution-asset",
                "message": "delivered logo.png is missing from redistributionEvidence.assets",
            })

    return review


def validate_source_evidence(
    payload: Any,
    *,
    require_urls: bool = True,
    artifact_root: Path | None = None,
    require_delivery: bool = False,
    compose_images: dict[str, str] | None = None,
    compose_version: str | None = None,
) -> list[str]:
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
        _validate_image_fields(image_evidence, "imageEvidence", errors)

    image_entries = payload.get("images")
    images_by_version_service: dict[tuple[str, str], dict[str, Any]] = {}
    if image_entries is not None:
        if not isinstance(image_entries, list) or not image_entries:
            errors.append("images must be a non-empty list when present")
            image_entries = []
        for index, image in enumerate(image_entries):
            field = f"images[{index}]"
            if not isinstance(image, dict):
                errors.append(f"{field} must be an object")
                continue
            version = image.get("version")
            service = image.get("service")
            reference = image.get("reference")
            valid_version = (
                isinstance(version, str)
                and VERSION_NAME.fullmatch(version.strip()) is not None
                and version == version.strip()
            )
            if not valid_version:
                errors.append(f"{field}.version must be a valid version directory name")
            if (
                not isinstance(service, str)
                or SERVICE_NAME.fullmatch(service.strip()) is None
                or service != service.strip()
            ):
                errors.append(f"{field}.service must be a valid Compose service name")
            elif valid_version:
                key = (version, service)
                if key in images_by_version_service:
                    errors.append(
                        "images version/service pairs must be unique: "
                        f"{version}/{service}"
                    )
                else:
                    images_by_version_service[key] = image
            if (
                not isinstance(reference, str)
                or not reference
                or reference != reference.strip()
                or re.search(r"\s", reference)
            ):
                errors.append(f"{field}.reference must be one non-empty image reference")
            _validate_image_fields(image, field, errors, require_digest=True)

    if require_delivery and compose_images is not None:
        if image_entries is None and len(compose_images) == 1 and image_evidence is not None:
            service, reference = next(iter(compose_images.items()))
            pinned = PINNED_IMAGE_REFERENCE.fullmatch(reference)
            digest = image_evidence.get("digest")
            if not isinstance(digest, str) or IMAGE_DIGEST.fullmatch(digest.strip()) is None:
                errors.append("imageEvidence.digest is required for delivery")
            elif pinned is not None and digest.lower() != pinned.group("digest").lower():
                errors.append(
                    f"imageEvidence.digest must match Compose service image: {service}"
                )
        else:
            selected_images: dict[str, dict[str, Any]] = {}
            if compose_version is None:
                errors.append("Compose version is required to select images evidence")
            else:
                selected_images = {
                    service: image
                    for (version, service), image in images_by_version_service.items()
                    if version == compose_version
                }
            for service, reference in compose_images.items():
                image = selected_images.get(service)
                if image is None:
                    errors.append(f"Compose service image lacks evidence: {service}")
                    continue
                evidence_reference = image.get("reference")
                if evidence_reference != reference:
                    errors.append(
                        f"images evidence reference must match Compose service image: {service}"
                    )
                pinned = PINNED_IMAGE_REFERENCE.fullmatch(reference)
                digest = image.get("digest")
                if (
                    pinned is not None
                    and isinstance(digest, str)
                    and digest.lower() != pinned.group("digest").lower()
                ):
                    errors.append(
                        f"images evidence digest must match Compose service image: {service}"
                    )
            for service in sorted(selected_images.keys() - compose_images.keys()):
                errors.append(f"images evidence service is absent from Compose: {service}")

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
        if require_delivery and _is_placeholder_license(spdx):
            errors.append("licenseEvidence.spdx must identify a verified license for delivery")
    elif require_delivery:
        errors.append("missing key: licenseEvidence")

    logo_evidence = _optional_object(payload, "logoEvidence", errors)
    if logo_evidence is not None:
        source = logo_evidence.get("source")
        logo_license = logo_evidence.get("license")
        sha256 = logo_evidence.get("sha256")
        if not isinstance(source, str) or LOGO_SOURCE.fullmatch(source.strip()) is None:
            errors.append(
                "logoEvidence.source must be an https URL or bundled:<package-relative-path>"
            )
        elif source != source.strip():
            errors.append("logoEvidence.source must not contain surrounding whitespace")
        elif source.startswith("bundled:") and not _is_safe_package_path(
            source.removeprefix("bundled:")
        ):
            errors.append("logoEvidence.source must use a safe bundled package-relative path")
        if logo_license is not None and (
            not isinstance(logo_license, str) or not logo_license.strip()
        ):
            errors.append("logoEvidence.license must be a non-empty string")
        if sha256 is not None and (
            not isinstance(sha256, str)
            or SHA256.fullmatch(sha256.strip()) is None
        ):
            errors.append("logoEvidence.sha256 must contain 64 hex characters")
        if require_delivery and sha256 is None:
            errors.append("logoEvidence.sha256 is required for delivery")
        if require_delivery and _is_placeholder_license(logo_license):
            errors.append("logoEvidence.license must identify a verified license for delivery")

    redistribution = _optional_object(payload, "redistributionEvidence", errors)
    if redistribution is None:
        if require_delivery:
            errors.append("missing key: redistributionEvidence")
        return errors

    status = redistribution.get("status")
    if status not in REDISTRIBUTION_STATUSES:
        errors.append("redistributionEvidence.status must be verified or unresolved")
    elif require_delivery and status != "verified":
        errors.append("redistributionEvidence.status must be verified for delivery")

    _validate_path_list(
        redistribution.get("requiredFiles", []),
        "redistributionEvidence.requiredFiles",
        errors,
    )
    assets = redistribution.get("assets")
    if not isinstance(assets, list):
        errors.append("redistributionEvidence.assets must be a list")
        assets = []
    elif status == "verified" and not assets:
        errors.append("redistributionEvidence.assets must not be empty when status is verified")

    materials = redistribution.get("materials", [])
    if not isinstance(materials, list):
        errors.append("redistributionEvidence.materials must be a list")
        materials = []
    material_paths: list[str] = []
    for index, material in enumerate(materials):
        field = f"redistributionEvidence.materials[{index}]"
        if not isinstance(material, dict):
            errors.append(f"{field} must be an object")
            continue
        path_value = material.get("path")
        if not _is_safe_package_path(path_value):
            errors.append(f"{field}.path must be a safe package-relative path")
        else:
            material_paths.append(path_value)
        sha256 = material.get("sha256")
        if not isinstance(sha256, str) or SHA256.fullmatch(sha256.strip()) is None:
            errors.append(f"{field}.sha256 must contain 64 hex characters")
        purpose = material.get("purpose")
        if purpose is not None and (
            not isinstance(purpose, str) or not purpose.strip()
        ):
            errors.append(f"{field}.purpose must be a non-empty string when present")
    if len(material_paths) != len(set(material_paths)):
        errors.append("redistributionEvidence.materials paths must be unique")

    asset_paths: list[str] = []
    logo_assets: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        field = f"redistributionEvidence.assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{field} must be an object")
            continue
        path_value = asset.get("path")
        if not _is_safe_package_path(path_value):
            errors.append(f"{field}.path must be a safe package-relative path")
        else:
            asset_paths.append(path_value)
            if path_value == "logo.png":
                logo_assets.append(asset)
        source = asset.get("source")
        if not isinstance(source, str) or ASSET_SOURCE.fullmatch(source.strip()) is None:
            errors.append(f"{field}.source must be an https, bundled, or unverified source")
        elif source != source.strip():
            errors.append(f"{field}.source must not contain surrounding whitespace")
        elif source.startswith("bundled:") and not _is_safe_package_path(
            source.removeprefix("bundled:")
        ):
            errors.append(f"{field}.source must use a safe bundled package-relative path")
        elif status == "verified" and source.startswith("unverified:"):
            errors.append(f"{field}.source must be verified when status is verified")
        license_value = asset.get("license")
        if status == "verified" and (
            not isinstance(license_value, str) or not license_value.strip()
        ):
            errors.append(f"{field}.license must be a non-empty string when status is verified")
        elif status == "verified" and _is_placeholder_license(license_value):
            errors.append(f"{field}.license must identify a verified license when status is verified")
        sha256 = asset.get("sha256")
        if not isinstance(sha256, str) or SHA256.fullmatch(sha256.strip()) is None:
            errors.append(f"{field}.sha256 must contain 64 hex characters")
        _validate_path_list(
            asset.get("requiredFiles", []),
            f"{field}.requiredFiles",
            errors,
        )
    if len(asset_paths) != len(set(asset_paths)):
        errors.append("redistributionEvidence.assets paths must be unique")

    if logo_evidence is not None and len(logo_assets) == 1:
        logo_asset = logo_assets[0]
        for key in ("source", "license", "sha256"):
            logo_value = logo_evidence.get(key)
            asset_value = logo_asset.get(key)
            if key == "sha256" and isinstance(logo_value, str) and isinstance(asset_value, str):
                matches = logo_value.lower() == asset_value.lower()
            else:
                matches = logo_value == asset_value
            if logo_value is not None and not matches:
                errors.append(
                    f"logoEvidence.{key} must match redistributionEvidence asset for logo.png"
                )

    if logo_evidence is not None and artifact_root is not None:
        logo_path, logo_error = _artifact_file(Path(artifact_root), "logo.png")
        if logo_path is None:
            errors.append(f"logoEvidence cannot be bound to delivered logo.png: {logo_error}")
        else:
            logo_sha256 = logo_evidence.get("sha256")
            if isinstance(logo_sha256, str) and SHA256.fullmatch(logo_sha256.strip()):
                if logo_sha256.lower() != _sha256_file(logo_path):
                    errors.append("logoEvidence.sha256 does not match delivered logo.png")

    required_paths: list[str] = []
    raw_required = redistribution.get("requiredFiles", [])
    if isinstance(raw_required, list):
        required_paths.extend(item for item in raw_required if _is_safe_package_path(item))
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_required = asset.get("requiredFiles", [])
        if isinstance(asset_required, list):
            required_paths.extend(item for item in asset_required if _is_safe_package_path(item))
    if status == "verified" and (require_delivery or artifact_root is not None):
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                continue
            source = asset.get("source")
            if isinstance(source, str) and source.startswith("bundled:"):
                bundled_path = source.removeprefix("bundled:")
                if bundled_path not in required_paths:
                    errors.append(
                        f"redistributionEvidence.assets[{index}].source bundled source "
                        "must be a hash-bound required file"
                    )
    if status == "verified":
        for required_path in dict.fromkeys(required_paths):
            if required_path not in material_paths:
                errors.append(
                    "redistributionEvidence.materials must hash required file: "
                    f"{required_path}"
                )

    if artifact_root is not None and not errors:
        review = inspect_redistribution_delivery(payload, artifact_root=artifact_root)
        errors.extend(issue["message"] for issue in review["issues"])

    return errors


def load_source_evidence(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate source-evidence.json")
    parser.add_argument("evidence_file")
    parser.add_argument("--artifact-root")
    parser.add_argument("--compose")
    parser.add_argument("--env-file")
    parser.add_argument("--version-name")
    parser.add_argument("--require-delivery", action="store_true")
    args = parser.parse_args()
    try:
        payload = load_source_evidence(Path(args.evidence_file))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[A][FAIL] source-evidence.json invalid JSON: {exc}")
        return 1

    compose_images = None
    if args.compose or args.env_file:
        if not args.compose or not args.env_file:
            print("[A][FAIL] source-evidence.json --compose and --env-file must be used together")
            return 1
        try:
            compose_images = load_compose_images(
                Path(args.compose),
                Path(args.env_file),
            )
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"[A][FAIL] source-evidence.json cannot inspect Compose images: {exc}")
            return 1

    errors = validate_source_evidence(
        payload,
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        require_delivery=args.require_delivery,
        compose_images=compose_images,
        compose_version=args.version_name,
    )
    for error in errors:
        print(f"[A][FAIL] source-evidence.json {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
