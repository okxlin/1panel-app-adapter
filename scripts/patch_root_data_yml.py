#!/usr/bin/env python3
import re
import sys
from pathlib import Path

import yaml


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


REQ_DESC_LOCALES = ["en", "zh", "zh-Hant", "ja", "ko", "ru", "ms", "pt-br"]


def stripq(s: str) -> str:
    return s.strip().strip('"').strip("'")


def find_top(lines, key, fallback=""):
    rx = re.compile(rf"^{re.escape(key)}:\s*(.*)$")
    for line in lines:
        m = rx.match(line)
        if m:
            return stripq(m.group(1))
    return fallback


def find_ap_scalar(lines, key, fallback=""):
    rx = re.compile(rf"^\s{{2}}{re.escape(key)}:\s*(.*)$")
    for line in lines:
        m = rx.match(line)
        if m:
            return stripq(m.group(1))
    return fallback


def normalize_arches(raw: str):
    values = []
    for part in re.split(r"[\s,]+", raw.strip()):
        item = part.strip()
        if item and item not in values:
            values.append(item)
    return values or ["amd64"]


def parse_ap_tags(lines):
    tags = []
    capture = False
    for line in lines:
        if re.match(r"^\s{2}tags:\s*$", line):
            capture = True
            continue
        if capture:
            if re.match(r"^\s{4}-\s+", line):
                tags.append(stripq(re.sub(r"^\s{4}-\s+", "", line)))
                continue
            break
    return tags


def parse_ap_arches(lines):
    values = []
    capture = False
    for line in lines:
        if re.match(r"^\s{2}architectures:\s*$", line):
            capture = True
            continue
        if capture:
            if re.match(r"^\s{4}-\s+", line):
                values.append(stripq(re.sub(r"^\s{4}-\s+", "", line)))
                continue
            break
    return values


def parse_description_map(lines):
    values = {}
    capture = False
    for line in lines:
        if re.match(r"^\s{2}description:\s*$", line):
            capture = True
            continue
        if capture:
            m = re.match(r"^\s{4}([A-Za-z0-9-]+):\s*(.*)$", line)
            if m:
                raw_value = m.group(2).rstrip("\n")
                values[m.group(1)] = stripq(raw_value)
                continue
            break
    return values


def patch(path: Path, app_key_hint: str = "", architectures: str = ""):
    original = path.read_text(encoding="utf-8", errors="ignore")
    lines = original.splitlines()
    loaded = yaml.safe_load(original) if original.strip() else {}
    if not isinstance(loaded, dict):
        loaded = {}
    ap = loaded.get("additionalProperties") if isinstance(loaded.get("additionalProperties"), dict) else {}

    app_key = ap.get("key") or find_ap_scalar(lines, "key", app_key_hint or path.parent.name)
    name = loaded.get("name") or find_top(lines, "name", app_key)
    title = loaded.get("title") or find_top(lines, "title", name)
    description = loaded.get("description") or find_top(lines, "description", title)
    tags = ap.get("tags") if isinstance(ap.get("tags"), list) else (loaded.get("tags") if isinstance(loaded.get("tags"), list) else parse_ap_tags(lines) or ["Tool"])
    if not tags:
        tags = ["Tool"]
    app_type = ap.get("type") or find_ap_scalar(lines, "type", "tool")
    website = ap.get("website") if isinstance(ap.get("website"), str) else find_ap_scalar(lines, "website", "")
    document = ap.get("document") if isinstance(ap.get("document"), str) else find_ap_scalar(lines, "document", "")
    github = ap.get("github") if isinstance(ap.get("github"), str) else find_ap_scalar(lines, "github", "")
    short_desc_zh = ap.get("shortDescZh") or find_ap_scalar(lines, "shortDescZh", title)
    short_desc_en = ap.get("shortDescEn") or find_ap_scalar(lines, "shortDescEn", title)
    if ap.get("crossVersionUpdate") is not None:
        value = ap.get("crossVersionUpdate")
        if isinstance(value, str):
            cross_version = value.strip().lower() == "true"
        else:
            cross_version = value
    else:
        cross_version = (find_ap_scalar(lines, "crossVersionUpdate", "true") or "true").lower() == "true"

    if ap.get("limit") is not None:
        value = ap.get("limit")
        if isinstance(value, str):
            try:
                limit = int(value)
            except ValueError:
                limit = 0
        else:
            limit = value
    else:
        raw_limit = find_ap_scalar(lines, "limit", "0") or "0"
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 0
    arches = normalize_arches(architectures) if architectures else (ap.get("architectures") if isinstance(ap.get("architectures"), list) else parse_ap_arches(lines) or ["amd64"])
    description_map = ap.get("description") if isinstance(ap.get("description"), dict) else parse_description_map(lines)
    for locale in REQ_DESC_LOCALES:
        if locale not in description_map or description_map[locale] == "":
            if locale == "en":
                description_map[locale] = short_desc_en or title
            elif locale == "zh":
                description_map[locale] = short_desc_zh or title
            else:
                description_map[locale] = title

    payload = {
        "name": name,
        "tags": tags,
        "title": title,
        "description": description,
        "additionalProperties": {
            "key": app_key,
            "name": name,
            "tags": tags,
            "type": app_type,
            "website": website,
            "document": document,
            "github": github,
            "shortDescZh": short_desc_zh,
            "shortDescEn": short_desc_en,
            "crossVersionUpdate": cross_version,
            "limit": limit,
            "architectures": arches,
            "description": {locale: description_map[locale] for locale in REQ_DESC_LOCALES},
        },
    }

    new_text = yaml.dump(payload, Dumper=NoAliasDumper, allow_unicode=True, sort_keys=False)
    if new_text != original:
        path.write_text(new_text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: patch_root_data_yml.py <root-data-yml> [app_key] [architectures]", file=sys.stderr)
        sys.exit(2)
    patch(
        Path(sys.argv[1]),
        sys.argv[2] if len(sys.argv) > 2 else "",
        sys.argv[3] if len(sys.argv) > 3 else "",
    )
