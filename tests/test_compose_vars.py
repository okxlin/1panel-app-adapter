#!/usr/bin/env python3
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPOSE_VARS = REPO_ROOT / "scripts" / "compose_env_vars.py"
CLOSURE = REPO_ROOT / "scripts" / "test-env-sample-closure.sh"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ComposeVariableTests(unittest.TestCase):
    def _write_app(self, root: pathlib.Path, sample_names: list[str]) -> pathlib.Path:
        app = root / "sample"
        version = app / "latest"
        version.mkdir(parents=True)
        (version / "docker-compose.yml").write_text(
            textwrap.dedent("""\
                services:
                  sample:
                    image: example/sample:latest
                    environment:
                      - PLAIN=${PLAIN}
                      - COLON_DEFAULT=${COLON_DEFAULT:-fallback}
                      - DASH_DEFAULT=${DASH_DEFAULT-fallback}
                      - COLON_REQUIRED=${COLON_REQUIRED:?required}
                      - REQUIRED=${REQUIRED?required}
                """),
            encoding="utf-8",
        )
        (version / ".env.sample").write_text(
            "".join(f"{name}=value\n" for name in sample_names),
            encoding="utf-8",
        )
        return app

    def test_shared_extractor_normalizes_supported_parameter_expansions(self) -> None:
        self.assertTrue(
            COMPOSE_VARS.is_file(), "shared Compose variable extractor is missing"
        )
        module = load_module(COMPOSE_VARS, "compose_env_vars_test")
        text = " ".join(
            (
                "${PLAIN}",
                "${COLON_DEFAULT:-fallback}",
                "${DASH_DEFAULT-fallback}",
                "${COLON_REQUIRED:?required}",
                "${REQUIRED?required}",
            )
        )

        self.assertEqual(
            module.extract_compose_variable_names(text),
            {"PLAIN", "COLON_DEFAULT", "DASH_DEFAULT", "COLON_REQUIRED", "REQUIRED"},
        )

    def test_shared_extractor_follows_nested_and_unbraced_fallbacks(self) -> None:
        self.assertTrue(
            COMPOSE_VARS.is_file(), "shared Compose variable extractor is missing"
        )
        module = load_module(COMPOSE_VARS, "compose_env_vars_nested_test")
        text = "${PRIMARY:-${FALLBACK:-$DEEP}} $${LITERAL} $$${ACTIVE}"

        self.assertEqual(
            module.extract_compose_variable_names(text),
            {"PRIMARY", "FALLBACK", "DEEP", "ACTIVE"},
        )

    def test_shared_extractor_ignores_yaml_comments(self) -> None:
        module = load_module(COMPOSE_VARS, "compose_env_vars_comments_test")
        text = textwrap.dedent("""\
            # $TOP_LEVEL_COMMENT
            services:
              app:
                image: example/app:latest
                # ${SERVICE_COMMENT}
                environment:
                  - ACTIVE=${ACTIVE}
                  - 'HASH_VALUE=literal # ${QUOTED_VALUE}'
            """)

        self.assertEqual(
            module.extract_compose_variable_names(text),
            {"ACTIVE", "QUOTED_VALUE"},
        )

    def test_env_sample_closure_requires_nested_fallback_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_app(
                pathlib.Path(tmp),
                [
                    "PLAIN",
                    "COLON_DEFAULT",
                    "DASH_DEFAULT",
                    "COLON_REQUIRED",
                    "REQUIRED",
                ],
            )
            compose = app / "latest" / "docker-compose.yml"
            compose_text = compose.read_text(encoding="utf-8")
            compose.write_text(
                compose_text.replace(
                    "      - REQUIRED=${REQUIRED?required}\n",
                    "      - REQUIRED=${REQUIRED?required}\n"
                    "      - NESTED=${PRIMARY:-${FALLBACK}}\n",
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", str(CLOSURE), str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PRIMARY", proc.stdout)
        self.assertIn("FALLBACK", proc.stdout)

    def test_env_sample_closure_accepts_supported_parameter_expansions(self) -> None:
        names = ["PLAIN", "COLON_DEFAULT", "DASH_DEFAULT", "COLON_REQUIRED", "REQUIRED"]
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_app(pathlib.Path(tmp), names)
            proc = subprocess.run(
                ["bash", str(CLOSURE), str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("compose_vars=5", proc.stdout)

    def test_env_sample_closure_rejects_empty_container_name(self) -> None:
        for empty_value in (
            "",
            "   ",
            " # empty",
            '""',
            '"" # empty',
            "''",
            "'' # empty",
        ):
            with self.subTest(empty_value=empty_value), tempfile.TemporaryDirectory() as tmp:
                app = self._write_app(
                    pathlib.Path(tmp),
                    [
                        "PLAIN",
                        "COLON_DEFAULT",
                        "DASH_DEFAULT",
                        "COLON_REQUIRED",
                        "REQUIRED",
                        "CONTAINER_NAME",
                    ],
                )
                version = app / "latest"
                compose = version / "docker-compose.yml"
                compose.write_text(
                    compose.read_text(encoding="utf-8").replace(
                        "    image: example/sample:latest\n",
                        "    image: example/sample:latest\n"
                        "    container_name: ${CONTAINER_NAME}\n",
                    ),
                    encoding="utf-8",
                )
                env_sample = version / ".env.sample"
                env_sample.write_text(
                    env_sample.read_text(encoding="utf-8").replace(
                        "CONTAINER_NAME=value", f"CONTAINER_NAME={empty_value}"
                    ),
                    encoding="utf-8",
                )
                proc = subprocess.run(
                    ["bash", str(CLOSURE), str(app)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("CONTAINER_NAME must be non-empty", proc.stdout)

    def test_env_sample_closure_reports_normalized_missing_name(self) -> None:
        names = ["PLAIN", "COLON_DEFAULT", "DASH_DEFAULT", "COLON_REQUIRED"]
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_app(pathlib.Path(tmp), names)
            proc = subprocess.run(
                ["bash", str(CLOSURE), str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("REQUIRED", proc.stdout)
        self.assertNotIn("REQUIRED?required", proc.stdout)

    def test_env_sample_closure_rejects_invalid_compose_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_app(pathlib.Path(tmp), [])
            (app / "latest" / "docker-compose.yml").write_text(
                "services:\n  app: [\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["bash", str(CLOSURE), str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("cannot extract Compose variables", proc.stderr)


if __name__ == "__main__":
    unittest.main()
