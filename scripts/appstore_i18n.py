#!/usr/bin/env python3
"""1Panel application locale keys and focused translation checks.

Contract: 1Panel-dev/1Panel a02c25ebcc82e467a5e507cb340f5dc4c2eb2ce5,
agent/app/dto/app.go and frontend/src/utils/app-store.ts.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any

import yaml

LOCALES = ("en", "zh", "zh-hant", "ja", "ko", "ru", "ms", "pt-br", "tr", "es-es", "fa", "lo")
LEGACY_LOCALES = LOCALES[:8]
PLACEHOLDER = re.compile(
    r"[（(]\s*(?:placeholder|translation required|佔位|占位|プレースホルダー|플레이스홀더|заполнитель|ruang letak|preenchimento)\s*[）)]"
    r"|^\s*(?:placeholder|translation required)\s*$", re.I,
)
MALAY_HARBOUR = re.compile(r"\bpelabuhan\b", re.I)


def normalize_locales(value: Any) -> dict[str, Any]:
    """Accept historical case aliases, retain unknown locales, reject conflicts."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, text in value.items():
        lowered = str(key).lower()
        canonical = "zh-hant" if lowered == "tw" else lowered if lowered in LOCALES else key
        if canonical in result and result[canonical] != text:
            raise ValueError(f"conflicting locale aliases for {canonical}")
        result[canonical] = text
    return result


def fill_locales(zh: Any, en: Any = None, existing: Any = None) -> dict[str, Any]:
    """Fill the scaffold shape; English fallbacks still fail strict delivery checks."""
    result = normalize_locales(existing)
    zh = str(zh or en or "")
    en = str(en or zh or "")
    for locale in LOCALES:
        result.setdefault(locale, zh if locale in {"zh", "zh-hant"} else en)
    return result


def iter_fields(fields: Any):
    if isinstance(fields, dict):
        fields = [fields]
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        yield field
        yield from iter_fields(field.get("child"))


def _summary_placeholders(root: dict) -> set[str]:
    properties = root.get("additionalProperties") or {}
    names = {str(name).strip().casefold() for name in
             (root.get("name"), properties.get("name"), properties.get("key")) if name}
    # A title can be useful prose, but copying it to both language summaries is a scaffold placeholder.
    title = root.get("title")
    if isinstance(title, str) and title.strip() and all(
        isinstance(properties.get(key), str) and properties[key].strip().casefold() == title.strip().casefold()
        for key in ("shortDescZh", "shortDescEn")
    ):
        names.add(title.strip().casefold())
    return names


def _descriptive_text(value: Any, placeholders: set[str]) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and value.strip().casefold() not in placeholders and not PLACEHOLDER.search(value))


def normalize_short_descriptions(root: dict) -> None:
    """Repair missing/name-only summaries from supplied translations, preserving prose."""
    properties = root.setdefault("additionalProperties", {})
    descriptions = normalize_locales(properties.get("description"))
    placeholders = _summary_placeholders(root)
    for key, locale in (("shortDescZh", "zh"), ("shortDescEn", "en")):
        candidate = descriptions.get(locale)
        if not _descriptive_text(properties.get(key), placeholders) and _descriptive_text(candidate, placeholders):
            properties[key] = candidate
    if not _descriptive_text(root.get("description"), placeholders):
        for key in ("shortDescZh", "shortDescEn"):
            if _descriptive_text(properties.get(key), placeholders):
                root["description"] = properties[key]
                break


def short_description_findings(root: dict) -> list[str]:
    properties = root.get("additionalProperties") or {}
    placeholders = _summary_placeholders(root)
    values = [("root description", root.get("description"))]
    values.extend((f"additionalProperties.{key}", properties.get(key)) for key in ("shortDescZh", "shortDescEn"))
    return [f"{label} must describe the application, not just repeat its name or a placeholder"
            for label, value in values if not _descriptive_text(value, placeholders)]


def is_network_port(field: dict) -> bool:
    return str(field.get("envKey", "")).startswith("PANEL_APP_PORT") or field.get("rule") == "paramPort"


def normalize_port_label(field: dict) -> None:
    labels = field.get("label")
    if is_network_port(field) and isinstance(labels, dict) and isinstance(labels.get("ms"), str):
        labels["ms"] = MALAY_HARBOUR.sub("Port", labels["ms"])


def normalize_metadata(root_path: Path, version_path: Path) -> None:
    for path, is_root in ((root_path, True), (version_path, False)):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        properties = data.get("additionalProperties") or {}
        if is_root:
            properties["description"] = fill_locales(properties.get("shortDescZh"), properties.get("shortDescEn"), properties.get("description"))
        else:
            for field in iter_fields(properties.get("formFields")):
                if any(field.get(key) for key in ("label", "labelZh", "labelEn")):
                    field["label"] = fill_locales(field.get("labelZh"), field.get("labelEn"), field.get("label"))
                    normalize_port_label(field)
                if isinstance(field.get("description"), dict):
                    field["description"] = normalize_locales(field["description"])
        data["additionalProperties"] = properties
        if is_root:
            normalize_short_descriptions(data)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def translation_findings(value: Any, label: str, *, allow_english: set[str] | None = None,
                         allow_english_by_locale: dict[str, set[str]] | None = None) -> list[str]:
    try:
        values = normalize_locales(value)
    except ValueError as exc:
        return [f"{label}: {exc}"]
    findings = []
    english = str(values.get("en", "")).strip().casefold()
    for locale in LOCALES:
        text = values.get(locale)
        if not isinstance(text, str) or not text.strip():
            findings.append(f"{label} missing locale {locale}")
            continue
        if PLACEHOLDER.search(text):
            findings.append(f"{label}.{locale} contains a translation placeholder")
        elif (locale != "en" and text.strip().casefold() == english
              and english not in (allow_english or set())
              and english not in (allow_english_by_locale or {}).get(locale, set())):
            findings.append(f"{label}.{locale} equals English text exactly")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("version", type=Path)
    parser.add_argument("--mode", choices=("off", "warn", "strict"), default="warn")
    parser.add_argument("--scope", choices=("description", "labels", "all"), default="all")
    parser.add_argument("--allow-english-labels", default="")
    parser.add_argument("--normalize", action="store_true", help="Normalize generated locale keys and fill missing scaffold entries")
    parser.add_argument("--require-baseline", action="store_true", help="Require the historical root locale structure even when translation checks are off")
    args = parser.parse_args()
    if args.normalize:
        normalize_metadata(args.root, args.version)
        return 0
    if args.mode == "off" and not args.require_baseline:
        return 0
    try:
        root = yaml.safe_load(args.root.read_text(encoding="utf-8"))
        version = yaml.safe_load(args.version.read_text(encoding="utf-8"))
        if not isinstance(root, dict) or not isinstance(version, dict):
            raise ValueError("metadata must be YAML mappings")
        baseline = []
        if args.require_baseline:
            description = normalize_locales((root.get("additionalProperties") or {}).get("description"))
            baseline = [f"root additionalProperties.description missing locale {locale}"
                        for locale in LEGACY_LOCALES if locale not in description]
        findings = []
        if args.mode != "off" and args.scope in {"description", "all"}:
            findings.extend(translation_findings(
                (root.get("additionalProperties") or {}).get("description"),
                "additionalProperties.description",
            ))
        if args.mode != "off" and args.scope in {"labels", "all"}:
            allow = {word.strip().casefold() for word in args.allow_english_labels.split(",") if word.strip()}
            fields = (version.get("additionalProperties") or {}).get("formFields")
            for field in iter_fields(fields):
                # Unlabelled service children inherit their parent's visible label.
                if field.get("type") == "service" and not any(field.get(key) for key in ("label", "labelEn", "labelZh")):
                    continue
                label = f"formFields[{field.get('envKey', '?')}].label"
                port_field = is_network_port(field)
                findings.extend(translation_findings(
                    field.get("label"), label, allow_english=allow,
                    allow_english_by_locale={"ms": {"port"}} if port_field else None,
                ))
                if port_field:
                    try:
                        malay = normalize_locales(field.get("label")).get("ms")
                    except ValueError:
                        malay = None  # Alias conflicts are already reported by translation_findings.
                    if isinstance(malay, str) and MALAY_HARBOUR.search(malay):
                        findings.append(f"{label}.ms: network port must use Port, not Pelabuhan (harbour)")
                if field.get("description") is not None:
                    findings.extend(translation_findings(field["description"], f"formFields[{field.get('envKey', '?')}].description"))
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(f"[A][FAIL] cannot validate i18n: {exc}")
        return 1
    level = "[A][FAIL]" if args.mode == "strict" else "[B][WARN]"
    for finding in baseline:
        print(f"[A][FAIL] {finding}")
    for finding in findings:
        print(f"{level} {finding}")
    return int(bool(baseline) or (bool(findings) and args.mode == "strict"))


if __name__ == "__main__":
    raise SystemExit(main())
