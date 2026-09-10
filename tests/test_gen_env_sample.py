#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gen_env_sample import format_env_value, read_env_sample, write_env_sample


LITERALS = [
    ("EMPTY", "", ""),
    ("NULL", None, ""),
    ("TRUE", True, "true"),
    ("FALSE", False, "false"),
    ("INTEGER", 8080, "8080"),
    ("DECIMAL", 1.25, "1.25"),
    ("COMMENT", "Daily #1 news", "Daily #1 news"),
    ("QUOTES", """It's a "label" """, """It's a "label" """),
    ("BACKSLASH", r"C:\raw\path\n\t", r"C:\raw\path\n\t"),
    ("ODD_TRAILING", "ends\\", "ends\\"),
    ("EVEN_TRAILING", "ends\\\\", "ends\\\\"),
    ("SPACE", "  leading and trailing \t ", "  leading and trailing \t "),
    ("MULTILINE", 'one\n"two"\r\nthree\n', 'one\n"two"\r\nthree\n'),
    ("DOLLARS", "$ADAPTER_TEST_REPLACEMENT ${ADAPTER_TEST_REPLACEMENT:-wrong} $$", "$ADAPTER_TEST_REPLACEMENT ${ADAPTER_TEST_REPLACEMENT:-wrong} $$"),
    ("SHELL_TEXT", "$(printf nope); `literal`", "$(printf nope); `literal`"),
    ("UNICODE", "目录/内容", "目录/内容"),
]


class GenEnvSampleTests(unittest.TestCase):
    def _write_metadata(self, directory, fields, environment=None):
        version = directory / "data.yml"
        version.write_text(
            yaml.safe_dump({"additionalProperties": {"formFields": fields}}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        compose = directory / "compose.yml"
        compose.write_text(
            yaml.safe_dump({"services": {"sample": {"image": "busybox:1.37", "environment": environment or {}}}}, sort_keys=False),
            encoding="utf-8",
        )
        return version, compose, directory / ".env.sample"

    def _compose(self, compose, sample, *flags):
        if shutil.which("docker") is None:
            self.skipTest("Docker Compose CLI is unavailable")
        # Only fixture environment values are exposed by config --environment.
        environment = {"PATH": os.environ.get("PATH", ""), "ADAPTER_TEST_REPLACEMENT": "must-not-be-expanded"}
        probe = subprocess.run(["docker", "compose", "version"], text=True, capture_output=True, env=environment)
        if probe.returncode:
            self.skipTest("Docker Compose CLI is unavailable")
        result = subprocess.run(
            ["docker", "compose", "--env-file", str(sample), "-f", str(compose), "config", *flags],
            text=True, capture_output=True, env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_yaml_scalars_round_trip_through_literal_sample(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-literals-") as tmp:
            fields = [{"envKey": key, "type": "text", "default": value} for key, value, _ in LITERALS]
            version, compose, sample = self._write_metadata(Path(tmp), fields, {key: f"${{{key}}}" for key, _, _ in LITERALS})
            actual = write_env_sample(version, sample, compose, "sample-compose-check")
            expected = {"CONTAINER_NAME": "sample-compose-check", **{key: value for key, _, value in LITERALS}}
            self.assertEqual(actual, expected)
            self.assertEqual(read_env_sample(sample), expected)
            self.assertEqual(len(sample.read_text().splitlines()), len(expected))
            self.assertIn("INTEGER=8080\n", sample.read_text())
            self.assertIn('COMMENT="Daily #1 news"\n', sample.read_text())

    def test_real_compose_preserves_literal_scalar_values(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-compose-") as tmp:
            fields = [{"envKey": key, "default": value} for key, value, _ in LITERALS]
            version, compose, sample = self._write_metadata(Path(tmp), fields, {key: f"${{{key}}}" for key, _, _ in LITERALS})
            write_env_sample(version, sample, compose, "sample-compose-check")
            rendered = json.loads(self._compose(compose, sample, "--format", "json"))
            # config re-escapes dollars when serializing reusable Compose output.
            expected = {key: value.replace("$", "$$") for key, _, value in LITERALS}
            self.assertEqual(rendered["services"]["sample"]["environment"], expected)

    def test_compose_interpolation_environment_keeps_dollars_and_newlines_literal(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-interpolation-") as tmp:
            literal = "cost ${ADAPTER_TEST_REPLACEMENT}\nsecond line\\"
            version, compose, sample = self._write_metadata(
                Path(tmp), [{"envKey": "ZZ_ADAPTER_VALUE", "default": literal}],
                {"VALUE": "${ZZ_ADAPTER_VALUE}"},
            )
            write_env_sample(version, sample, compose, "sample-compose-check")
            output = self._compose(compose, sample, "--environment")
            # With the controlled environment, this fixture key sorts last.
            self.assertEqual(output.split("ZZ_ADAPTER_VALUE=", 1)[1], literal + "\n")

    def test_nested_children_and_referenced_app_selectors_keep_defaults(self):
        fields = [
            {"envKey": "PANEL_DB_TYPE", "type": "apps", "default": "mysql",
             "child": {"envKey": "PANEL_DB_HOST", "type": "service", "default": "database"},
             "values": [{"label": "MySQL", "value": "mysql"}]},
            {"envKey": "PARENT", "default": "unused", "child": [
                {"envKey": "NESTED", "default": "child"},
            ]},
            {"envKey": "UNUSED", "default": "unused"},
            {"envKey": "ESCAPED", "default": "must-not-be-included"},
        ]
        environment = {
            "TYPE": "$PANEL_DB_TYPE", "HOST": "${PANEL_DB_HOST}", "NESTED": "${NESTED}",
            "UPSTREAM": "${UNDECLARED-upstream-default}", "LITERAL": "$${ESCAPED}",
        }
        with tempfile.TemporaryDirectory(prefix="adapter-env-fields-") as tmp:
            version, compose, sample = self._write_metadata(Path(tmp), fields, environment)
            write_env_sample(version, sample, compose, "sample-compose-check")
            self.assertEqual(read_env_sample(sample), {
                "CONTAINER_NAME": "sample-compose-check", "PANEL_DB_TYPE": "mysql",
                "PANEL_DB_HOST": "database", "NESTED": "child",
            })
            unfiltered = Path(tmp) / "without-compose.env"
            write_env_sample(version, unfiltered, container_name="sample-compose-check")
            self.assertNotIn("PANEL_DB_TYPE", read_env_sample(unfiltered))
            self.assertIn("PANEL_DB_HOST", read_env_sample(unfiltered))
            rendered = json.loads(self._compose(compose, sample, "--format", "json"))
            self.assertEqual(rendered["services"]["sample"]["environment"]["UPSTREAM"], "upstream-default")

    def test_literal_reader_supports_conventional_quotes_comments_and_multiline(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-reader-") as tmp:
            sample = Path(tmp) / ".env"
            sample.write_text(
                "# comment\nexport PLAIN = value # comment\n"
                "HASH=value#literal\nSINGLE='Let\\'s go!'\n"
                "DOLLAR='${UNCHANGED}'\n"
                "MULTI='first\nsecond'\n"
                'DOUBLE="quote: \\"value\\" and \\\\ path" # comment\n',
                encoding="utf-8",
            )
            self.assertEqual(read_env_sample(sample), {
                "PLAIN": "value", "HASH": "value#literal", "SINGLE": "Let's go!",
                "DOLLAR": "${UNCHANGED}", "MULTI": "first\nsecond",
                "DOUBLE": 'quote: "value" and \\ path',
            })
            for value in ("$INTERPOLATED", '"${INTERPOLATED}"', "'unterminated"):
                with self.subTest(value=value):
                    sample.write_text("VALUE=" + value + "\n", encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_env_sample(sample)

    def test_optional_unresolved_interpolation_never_reads_process_environment(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-unresolved-") as tmp:
            sample = Path(tmp) / ".env"
            sample.write_text(
                "PLAIN=$ADAPTER_TEST_REPLACEMENT\n"
                'BRACED="${ADAPTER_TEST_REPLACEMENT:-fallback}"\n'
                'MIXED="$$ADAPTER_TEST_REPLACEMENT ${ADAPTER_TEST_REPLACEMENT} \\nnext"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"ADAPTER_TEST_REPLACEMENT": "must-not-be-expanded"}):
                self.assertEqual(read_env_sample(sample, allow_interpolation=True), {
                    "PLAIN": "$ADAPTER_TEST_REPLACEMENT",
                    "BRACED": "${ADAPTER_TEST_REPLACEMENT:-fallback}",
                    "MIXED": "$ADAPTER_TEST_REPLACEMENT ${ADAPTER_TEST_REPLACEMENT} \nnext",
                })
                with self.assertRaises(ValueError):
                    read_env_sample(sample)
            sample.write_text("INHERITED_KEY\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_env_sample(sample, allow_interpolation=True)

    def test_invalid_input_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-invalid-") as tmp:
            directory = Path(tmp)
            for field in ({"envKey": "BROKEN\nINJECTED", "default": "value"},
                          {"envKey": "VALUE", "default": {"nested": "unsupported"}},
                          {"envKey": "VALUE", "default": "contains\0nul"}):
                with self.subTest(field=field):
                    version, _, sample = self._write_metadata(directory, [field])
                    sample.write_text("EXISTING=keep\n", encoding="utf-8")
                    with self.assertRaises(ValueError):
                        write_env_sample(version, sample)
                    self.assertEqual(sample.read_text(), "EXISTING=keep\n")
            with self.assertRaises(ValueError):
                write_env_sample(version, sample, container_name="")
            self.assertEqual(format_env_value(True), "true")

    def test_cli_preserves_positional_arguments_and_implicit_container_name(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-cli-") as tmp:
            directory = Path(tmp) / "demo" / "1.0"
            directory.mkdir(parents=True)
            version, compose, sample = self._write_metadata(
                directory, [{"envKey": "CONTAINER_NAME", "default": ""}],
                {"NAME": "${CONTAINER_NAME}"},
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/gen_env_sample.py"), str(version), str(sample), str(compose)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(read_env_sample(sample), {"CONTAINER_NAME": "demo-compose-check"})
            invalid = subprocess.run(
                [sys.executable, str(ROOT / "scripts/gen_env_sample.py"), str(version), str(sample), str(compose), "bad/name"],
                text=True, capture_output=True,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual(read_env_sample(sample), {"CONTAINER_NAME": "demo-compose-check"})


if __name__ == "__main__":
    unittest.main()
