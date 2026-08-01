#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ANALYZER = REPO_ROOT / "scripts" / "validate_adaptation_safety.py"
RUNTIME_UTILS = REPO_ROOT / "scripts" / "runtime_script_utils.py"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyzer = load_module(ANALYZER, "validate_adaptation_safety_test")
runtime_utils = load_module(RUNTIME_UTILS, "runtime_script_utils_safety_test")


class AdaptationSafetyTests(unittest.TestCase):
    def _analyze_shell(self, content: str, path_keys=None, random_keys=None):
        with tempfile.TemporaryDirectory() as tmp:
            script = pathlib.Path(tmp) / "init.sh"
            script.write_text(content, encoding="utf-8")
            return analyzer.analyze_shell(
                script, set(path_keys or ()), set(random_keys or ())
            )

    def test_fake_resolver_markers_do_not_declassify_form_path(self) -> None:
        findings = self._analyze_shell(
            """#!/usr/bin/env bash
resolve_app_path() { printf '%s\\n' "$2"; }
# realpath -m
# "$ROOT_DIR"/*
# [[ -L "$current" ]]
RAW="${APP_DATA_DIR:-./data}"
RESOLVED="$(resolve_app_path APP_DATA_DIR "$RAW")"
rm -rf -- "$RESOLVED"
""",
            path_keys={"APP_DATA_DIR"},
        )

        self.assertTrue(any(finding.level == "A" for finding in findings), findings)

    def test_generated_resolver_does_not_flag_confined_mutation(self) -> None:
        content = runtime_utils.render_init_script_content(
            {
                "additionalProperties": {
                    "formFields": [{"envKey": "APP_DATA_DIR", "default": "./data"}]
                }
            }
        )

        findings = self._analyze_shell(content, path_keys={"APP_DATA_DIR"})

        self.assertFalse(any(finding.level == "A" for finding in findings), findings)

    def test_encoder_name_cannot_hide_raw_password_output(self) -> None:
        findings = self._analyze_shell(
            """#!/usr/bin/env bash
PASSWORD="${APP_DB_PASSWORD}"
DATABASE_URL="postgresql://user:$(url_encode "$PASSWORD" >/dev/null; printf '%s' "$PASSWORD")@db/app"
""",
            random_keys={"APP_DB_PASSWORD"},
        )

        self.assertTrue(any(finding.level == "B" for finding in findings), findings)

    def test_exact_encoder_value_flow_is_not_flagged(self) -> None:
        findings = self._analyze_shell(
            """#!/usr/bin/env bash
PASSWORD="${APP_DB_PASSWORD}"
ENCODED_PASSWORD="$(url_encode "$PASSWORD")"
DATABASE_URL="postgresql://user:${ENCODED_PASSWORD}@db/app"
""",
            random_keys={"APP_DB_PASSWORD"},
        )

        self.assertFalse(any(finding.level == "B" for finding in findings), findings)

    def test_redirection_and_tee_are_treated_as_path_mutations(self) -> None:
        for mutation in (
            'printf data > "$DATA_DIR/config"',
            'printf data | tee "$DATA_DIR/config"',
        ):
            with self.subTest(mutation=mutation):
                findings = self._analyze_shell(
                    f'#!/usr/bin/env bash\nDATA_DIR="${{APP_DATA_DIR:-./data}}"\n{mutation}\n',
                    path_keys={"APP_DATA_DIR"},
                )
                self.assertTrue(
                    any(finding.level == "A" for finding in findings), findings
                )

    def test_mutating_command_text_inside_echo_is_not_flagged(self) -> None:
        findings = self._analyze_shell(
            '#!/usr/bin/env bash\nDATA_DIR="${APP_DATA_DIR:-./data}"\necho "run mkdir on $DATA_DIR"\n',
            path_keys={"APP_DATA_DIR"},
        )

        self.assertFalse(any(finding.level == "A" for finding in findings), findings)

    def test_directory_named_form_field_is_tainted_without_dot_slash_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version_data = root / "data.yml"
            compose = root / "docker-compose.yml"
            scripts = root / "scripts"
            scripts.mkdir()
            version_data.write_text(
                textwrap.dedent("""\
                    additionalProperties:
                      formFields:
                        - envKey: APP_DATA_DIR
                          default: data
                    """),
                encoding="utf-8",
            )
            compose.write_text(
                "services:\n  app:\n    image: example/app:latest\n",
                encoding="utf-8",
            )
            (scripts / "init.sh").write_text(
                'DATA_DIR="${APP_DATA_DIR:-data}"\nrm -rf -- "$DATA_DIR"\n',
                encoding="utf-8",
            )

            findings = analyzer.analyze(version_data, compose, scripts)

        self.assertTrue(any(finding.level == "A" for finding in findings), findings)

    def test_compose_bind_source_form_field_is_tainted_by_mount_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version_data = root / "data.yml"
            compose = root / "docker-compose.yml"
            scripts = root / "scripts"
            scripts.mkdir()
            version_data.write_text(
                textwrap.dedent("""\
                    additionalProperties:
                      formFields:
                        - envKey: APP_STORAGE_ROOT
                          default: data
                    """),
                encoding="utf-8",
            )
            compose.write_text(
                textwrap.dedent("""\
                    services:
                      app:
                        image: example/app:latest
                        volumes:
                          - ${APP_STORAGE_ROOT:-data}:/data
                    """),
                encoding="utf-8",
            )
            (scripts / "init.sh").write_text(
                'STORAGE="${APP_STORAGE_ROOT:-data}"\nrm -rf -- "$STORAGE"\n',
                encoding="utf-8",
            )

            findings = analyzer.analyze(version_data, compose, scripts)

        self.assertTrue(any(finding.level == "A" for finding in findings), findings)

    def test_tainted_path_fails_closed_across_opaque_shell_flows(self) -> None:
        cases = {
            "function wrapper": """#!/usr/bin/env bash
wipe() { rm -rf -- "$1"; }
wipe "$APP_DATA_DIR"
""",
            "continued mutation": """#!/usr/bin/env bash
RAW="${APP_DATA_DIR:-./data}"
rm -rf -- \\
  "$RAW"
""",
            "eval wrapper": """#!/usr/bin/env bash
COMMAND="rm -rf -- $APP_DATA_DIR"
eval "$COMMAND"
""",
            "sourced path": """#!/usr/bin/env bash
source "$APP_DATA_DIR"
""",
        }
        for label, content in cases.items():
            with self.subTest(label=label):
                findings = self._analyze_shell(
                    content,
                    path_keys={"APP_DATA_DIR"},
                )
                self.assertTrue(
                    any(finding.level == "A" for finding in findings), findings
                )

    def test_random_credential_to_opaque_shell_command_warns(self) -> None:
        findings = self._analyze_shell(
            """#!/usr/bin/env bash
build_url() { printf 'postgresql://user:%s@db/app' "$1"; }
DATABASE_URL="$(build_url "$APP_DB_PASSWORD")"
""",
            random_keys={"APP_DB_PASSWORD"},
        )

        self.assertTrue(any(finding.level == "B" for finding in findings), findings)


if __name__ == "__main__":
    unittest.main()
