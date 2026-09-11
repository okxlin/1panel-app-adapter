#!/usr/bin/env python3
import copy
import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from appstore_i18n import (LOCALES, fill_locales, normalize_locales, normalize_port_label,
                          normalize_short_descriptions, short_description_findings, translation_findings)
import test_validate_v2


DESCRIPTION = {
    "en": "Manage tasks with your team",
    "zh": "与团队一起管理任务",
    "zh-hant": "與團隊一起管理任務",
    "ja": "チームでタスクを管理",
    "ko": "팀과 함께 작업 관리",
    "ru": "Управляйте задачами вместе с командой",
    "ms": "Urus tugas bersama pasukan anda",
    "pt-br": "Gerencie tarefas com sua equipe",
    "tr": "Ekibinizle görevleri yönetin",
    "es-es": "Gestiona tareas con tu equipo",
    "fa": "وظایف را با تیم خود مدیریت کنید",
    "lo": "ຈັດການວຽກກັບທີມຂອງທ່ານ",
}

PORT_LABELS = {
    "en": "Port", "zh": "端口", "zh-hant": "連接埠", "ja": "ポート", "ko": "포트",
    "ru": "Порт", "ms": "Port", "pt-br": "Porta", "tr": "Bağlantı noktası",
    "es-es": "Puerto", "fa": "درگاه", "lo": "ພອດ",
}


class AppstoreI18nTests(unittest.TestCase):
    def test_runtime_keys_and_legacy_aliases(self):
        values = normalize_locales({"zh-Hant": "繁體", "pt-BR": "Tarefas", "es-ES": "Tareas", "de": "Aufgaben"})
        self.assertEqual(values, {"zh-hant": "繁體", "pt-br": "Tarefas", "es-es": "Tareas", "de": "Aufgaben"})
        with self.assertRaisesRegex(ValueError, "conflicting locale aliases"):
            normalize_locales({"zh-hant": "甲", "zh-Hant": "乙"})

    def test_fill_preserves_supplied_translations(self):
        values = fill_locales("任务", "Tasks", {"zh-Hant": "任務", "tr": "Görevler"})
        self.assertEqual(set(values), set(LOCALES))
        self.assertEqual(values["zh-hant"], "任務")
        self.assertEqual(values["tr"], "Görevler")
        self.assertTrue(translation_findings(values, "description"))

    def test_translations_and_technical_labels(self):
        self.assertEqual(translation_findings(DESCRIPTION, "description"), [])
        labels = dict.fromkeys(LOCALES, "API")
        self.assertEqual(translation_findings(labels, "label", allow_english={"api"}), [])
        for locale in ("tr", "es-es", "fa", "lo"):
            with self.subTest(locale=locale):
                incomplete = dict(DESCRIPTION)
                incomplete.pop(locale)
                self.assertIn(f"description missing locale {locale}", translation_findings(incomplete, "description"))

    def test_natural_language_is_not_a_placeholder_marker(self):
        values = dict(DESCRIPTION)
        values["pt-br"] = "Gerencie tarefas com preenchimento automático"
        self.assertEqual(translation_findings(values, "description"), [])
        values["pt-br"] += " (preenchimento)"
        self.assertIn("description.pt-br contains a translation placeholder", translation_findings(values, "description"))

    def test_network_port_malay_label_is_checked_in_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "root.yml"
            version = pathlib.Path(tmp) / "version.yml"
            root.write_text(yaml.safe_dump({"additionalProperties": {"description": DESCRIPTION}}), encoding="utf-8")
            field = {"envKey": "PANEL_APP_PORT_HTTP", "label": {**PORT_LABELS, "ms": "Pelabuhan"}}
            data = {"additionalProperties": {"formFields": [field]}}
            version.write_text(yaml.safe_dump(data), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts/appstore_i18n.py"), str(root), str(version),
                       "--mode", "strict", "--scope", "labels"]
            invalid = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout + invalid.stderr)
            self.assertIn("network port must use Port", invalid.stdout)
            normalized = subprocess.run(command + ["--normalize"], text=True, capture_output=True)
            self.assertEqual(normalized.returncode, 0, normalized.stdout + normalized.stderr)
            actual = yaml.safe_load(version.read_text(encoding="utf-8"))
            self.assertEqual(actual["additionalProperties"]["formFields"][0]["label"], PORT_LABELS)
            valid = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            field["label"] = {**PORT_LABELS, "ja": "Port"}
            version.write_text(yaml.safe_dump(data), encoding="utf-8")
            copied = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(copied.returncode, 0, copied.stdout + copied.stderr)
            self.assertIn("label.ja equals English text exactly", copied.stdout)
            self.assertNotIn("label.ms equals English text exactly", copied.stdout)
            field["label"] = {**PORT_LABELS, "en": "Choose the published port", "ms": "Choose the published port"}
            version.write_text(yaml.safe_dump(data), encoding="utf-8")
            prose_copy = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(prose_copy.returncode, 0, prose_copy.stdout + prose_copy.stderr)
            self.assertIn("label.ms equals English text exactly", prose_copy.stdout)

    def test_port_normalization_preserves_non_network_uses(self):
        for field, expected in (
            ({"envKey": "HARBOUR", "label": {"ms": "Pelabuhan"}}, "Pelabuhan"),
            ({"envKey": "CUSTOM_PORT", "rule": "paramPort", "label": {"ms": "Pelabuhan HTTP"}}, "Port HTTP"),
            ({"envKey": "PANEL_APP_PORT_HTTP", "label": {"ms": "Port HTTP"}}, "Port HTTP"),
        ):
            with self.subTest(field=field):
                normalize_port_label(field)
                self.assertEqual(field["label"]["ms"], expected)

    def test_summary_normalization_preserves_valid_prose_and_needs_real_source(self):
        root = {"name": "Demo", "title": "Manage tasks", "description": "Manage tasks",
                "additionalProperties": {"name": "Demo", "key": "demo", "shortDescZh": "管理任务",
                                         "shortDescEn": "Manage tasks", "description": DESCRIPTION}}
        original = copy.deepcopy(root)
        normalize_short_descriptions(root)
        self.assertEqual(root, original)
        self.assertEqual(short_description_findings(root), [])
        root["description"] = " Demo "
        root["additionalProperties"].update(shortDescZh="DEMO", shortDescEn="demo", description={"en": "Demo", "zh": "Demo"})
        original = copy.deepcopy(root)
        normalize_short_descriptions(root)
        self.assertEqual(root, original)
        self.assertEqual(len(short_description_findings(root)), 3)

    def test_display_title_copied_to_both_summaries_is_a_placeholder(self):
        root = {"name": "internal-key", "title": "DisplayName", "description": "DisplayName",
                "additionalProperties": {"name": "internal-key", "key": "internal-key",
                                         "shortDescZh": "DisplayName", "shortDescEn": "DisplayName"}}
        original = copy.deepcopy(root)
        self.assertEqual(len(short_description_findings(root)), 3)
        normalize_short_descriptions(root)
        self.assertEqual(root, original)
        root["additionalProperties"]["description"] = DESCRIPTION
        normalize_short_descriptions(root)
        self.assertEqual(root["title"], "DisplayName")
        self.assertEqual(root["description"], DESCRIPTION["zh"])
        self.assertEqual(root["additionalProperties"]["shortDescZh"], DESCRIPTION["zh"])
        self.assertEqual(root["additionalProperties"]["shortDescEn"], DESCRIPTION["en"])
        self.assertEqual(short_description_findings(root), [])

    def test_strict_validator_rejects_english_copies_and_accepts_translations(self):
        with tempfile.TemporaryDirectory(prefix="adapter-i18n-") as tmp:
            app = test_validate_v2.ValidateV2Tests()._write_sample_app(pathlib.Path(tmp))
            command = ["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app), "--i18n-mode", "strict", "--i18n-scope", "description"]
            invalid = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout + invalid.stderr)
            self.assertIn("equals English text exactly", invalid.stdout)
            path = app / "data.yml"
            data = yaml.safe_load(path.read_text())
            data["additionalProperties"]["description"] = DESCRIPTION
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            valid = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            self.assertIn("PASS:", valid.stdout)
            data["additionalProperties"]["description"] = {
                {"zh-hant": "zh-Hant", "pt-br": "pt-BR", "es-es": "es-ES"}.get(key, key): value
                for key, value in DESCRIPTION.items()
            }
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            aliases = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(aliases.returncode, 0, aliases.stdout + aliases.stderr)
            data["additionalProperties"]["description"].pop("en")
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            structural = subprocess.run(["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app),
                                         "--i18n-mode", "off"], text=True, capture_output=True)
            self.assertNotEqual(structural.returncode, 0)
            self.assertIn("root additionalProperties.description missing locale en", structural.stdout)


if __name__ == "__main__":
    unittest.main()
