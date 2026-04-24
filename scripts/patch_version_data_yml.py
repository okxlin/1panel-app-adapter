#!/usr/bin/env python3
import sys
from pathlib import Path

import yaml


def patch(path: Path):
    original = path.read_text(encoding="utf-8", errors="ignore")
    loaded = yaml.safe_load(original) if original.strip() else {}
    if not isinstance(loaded, dict):
        loaded = {}

    top_formfields = loaded.pop("formFields", None)
    ap = loaded.get("additionalProperties")
    if not isinstance(ap, dict):
        ap = {}
        loaded["additionalProperties"] = ap

    formfields = ap.get("formFields")
    if formfields is None:
        formfields = top_formfields if isinstance(top_formfields, list) else []
    elif not isinstance(formfields, list):
        formfields = []
    ap["formFields"] = formfields

    if not formfields:
        formfields.append({
            "default": 8080,
            "type": "number",
            "edit": True,
            "envKey": "PANEL_APP_PORT_HTTP",
            "required": True,
            "rule": "paramPort",
        })

    for item in formfields:
        if not isinstance(item, dict):
            continue
        env = str(item.get("envKey", "")).strip()
        if env == "HOST_PORT":
            env = "PANEL_APP_PORT_HTTP"
            item["envKey"] = env

        if env and "type" not in item:
            item["type"] = "number" if env.startswith("PANEL_APP_PORT") else "text"
        if env and "required" not in item:
            item["required"] = True
        if env.startswith("PANEL_APP_PORT") and "rule" not in item:
            item["rule"] = "paramPort"
        if env and "edit" not in item and item.get("type") not in {"apps", "service"} and env not in {"PANEL_DB_HOST", "PANEL_REDIS_HOST"}:
            item["edit"] = True

    if not any(isinstance(item, dict) and str(item.get("envKey", "")).strip() == "TZ" for item in formfields):
        formfields.append({
            "default": "Asia/Shanghai",
            "edit": True,
            "envKey": "TZ",
            "labelEn": "Timezone",
            "labelZh": "时区",
            "label": {
                "en": "Timezone",
                "zh": "时区",
                "zh-Hant": "時區",
                "ja": "タイムゾーン",
                "ko": "시간대",
                "ru": "Часовой пояс",
                "ms": "Zon waktu",
                "pt-br": "Fuso horário",
            },
            "required": True,
            "type": "text",
        })

    new_text = yaml.safe_dump(loaded, allow_unicode=True, sort_keys=False)
    if new_text != original:
        path.write_text(new_text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: patch_version_data_yml.py <version-data-yml>", file=sys.stderr)
        sys.exit(2)
    patch(Path(sys.argv[1]))
