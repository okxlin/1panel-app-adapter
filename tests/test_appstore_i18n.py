#!/usr/bin/env python3
import copy
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from appstore_i18n import (LOCALES, compatible_metadata, fill_locales, normalize_locales, normalize_port_label,
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
    def test_compatible_metadata_preserves_translations_and_nested_fields(self):
        data = {"additionalProperties": {"description": DESCRIPTION, "formFields": [
            {"envKey": "CHOICE", "label": PORT_LABELS, "labelEn": "Reviewed label", "child": [
                {"envKey": "HOST", "label": PORT_LABELS, "description": DESCRIPTION},
            ]},
        ]}}
        before = copy.deepcopy(data)
        output = compatible_metadata(data)
        self.assertEqual(data, before)
        self.assertEqual(compatible_metadata(output), output)
        fields = output["additionalProperties"]["formFields"]
        self.assertEqual(fields[0]["labelEn"], "Reviewed label")
        self.assertEqual(fields[0]["child"][0]["labelZh"], PORT_LABELS["zh"])
        for values in (output["additionalProperties"]["description"], fields[0]["label"],
                       fields[0]["child"][0]["label"], fields[0]["child"][0]["description"]):
            for canonical, alias in (("zh-hant", "zh-Hant"), ("pt-br", "pt-BR"), ("es-es", "es-ES")):
                self.assertEqual(values[canonical], values[alias])
            self.assertTrue(set(LOCALES).issubset(values))
        compose = {"services": {"app": {"environment": {"label": {"zh-Hant": "literal"}}}}}
        self.assertEqual(compatible_metadata(compose), compose)
        data["additionalProperties"]["description"] = {"zh-Hant": "甲", "zh-hant": "乙"}
        with self.assertRaisesRegex(ValueError, "conflicting locale aliases"):
            compatible_metadata(data)

    @unittest.skipUnless(shutil.which("node"), "Node is required for JavaScript reader replay")
    def test_serialized_metadata_reaches_legacy_and_current_javascript_readers(self):
        # Consumer contracts: v1 dev@20b89a8, v2.0.0 util.ts:633 and
        # v2.3.2 app-store.ts. This is a reader replay, not live UI evidence.
        data = {"additionalProperties": {"description": DESCRIPTION, "formFields": [
            {"label": PORT_LABELS, "description": DESCRIPTION},
        ]}}
        output = yaml.safe_load(yaml.safe_dump(compatible_metadata(data)))
        js = r"""
const assert = require('assert');
const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const field = data.additionalProperties.formFields[0];
assert.equal(field.labelZh, field.label.zh);
assert.equal(field.labelEn, field.label.en);
for (const values of [field.label, field.description, data.additionalProperties.description]) {
    for (const language of ['zh', 'en', 'tw', 'zh-Hant', 'pt-BR', 'es-ES']) {
        const oldKey = language === 'tw' ? 'zh-Hant' : language;
        const newKey = oldKey.toLowerCase();
        // Old lookup returns undefined for an absent key: undefined != ''.
        const oldValue = values[oldKey] != '' ? values[oldKey] : 'fallback';
        assert.equal(typeof oldValue, 'string');
        assert.equal(oldValue, values[newKey]);
    }
}
"""
        proc = subprocess.run([shutil.which("node"), "-e", js], input=json.dumps(output), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_metadata_normalizer_and_patchers_keep_compatible_output_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "root.yml"
            version = pathlib.Path(tmp) / "version.yml"
            root.write_text(yaml.safe_dump({"additionalProperties": {"description": DESCRIPTION}}), encoding="utf-8")
            version.write_text(yaml.safe_dump({"additionalProperties": {"formFields": [
                {"envKey": "PANEL_APP_PORT_HTTP", "type": "number", "required": True,
                 "label": PORT_LABELS, "description": DESCRIPTION},
            ]}}), encoding="utf-8")
            for command in ([sys.executable, str(ROOT / "scripts/appstore_i18n.py"), str(root), str(version), "--normalize"],
                            [sys.executable, str(ROOT / "scripts/patch_root_data_yml.py"), str(root)],
                            [sys.executable, str(ROOT / "scripts/patch_version_data_yml.py"), str(version)]):
                subprocess.run(command, check=True, capture_output=True)
                before = (root.read_bytes(), version.read_bytes())
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual((root.read_bytes(), version.read_bytes()), before)
            data = yaml.safe_load(version.read_text())["additionalProperties"]["formFields"][0]
            self.assertEqual(data["label"]["zh-Hant"], PORT_LABELS["zh-hant"])
            self.assertEqual(data["description"]["pt-BR"], DESCRIPTION["pt-br"])
            self.assertEqual(yaml.safe_load(root.read_text())["additionalProperties"]["description"]["es-ES"], DESCRIPTION["es-es"])

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
            self.assertEqual(normalize_locales(actual["additionalProperties"]["formFields"][0]["label"]), PORT_LABELS)
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
