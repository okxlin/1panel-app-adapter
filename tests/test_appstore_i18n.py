#!/usr/bin/env python3
import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from appstore_i18n import LOCALES, fill_locales, normalize_locales, translation_findings
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
