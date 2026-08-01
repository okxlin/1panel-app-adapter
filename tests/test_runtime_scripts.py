import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
FINALIZE = SCRIPTS_DIR / "finalize_runtime_scripts.sh"
GENERATE = SCRIPTS_DIR / "generate-from-appspec.py"
RUNTIME_UTILS = SCRIPTS_DIR / "runtime_script_utils.py"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime_utils = load_module(RUNTIME_UTILS, "runtime_script_utils_test")


class RuntimeScriptGenerationTest(unittest.TestCase):
    def test_collect_runtime_paths_rejects_unsafe_defaults(self):
        for default in ("/srv/demo", "../outside", "./data/../../outside", "./data\tbad"):
            with self.subTest(default=default):
                version_data = {
                    "additionalProperties": {
                        "formFields": [
                            {
                                "envKey": "APP_DATA_DIR",
                                "type": "text",
                                "required": True,
                                "default": default,
                            }
                        ]
                    }
                }

                with self.assertRaisesRegex(ValueError, "package-local relative path"):
                    runtime_utils.collect_runtime_path_fields(version_data)

    def test_collect_runtime_paths_rejects_invalid_environment_keys(self):
        for env_key in ("APP.DATA_DIR", "APP-DATA-DIR", "APP_DATA_DIR[$(id)]"):
            with self.subTest(env_key=env_key):
                version_data = {
                    "additionalProperties": {
                        "formFields": [
                            {
                                "envKey": env_key,
                                "type": "text",
                                "required": True,
                                "default": "./data",
                            }
                        ]
                    }
                }

                with self.assertRaisesRegex(ValueError, "environment variable name"):
                    runtime_utils.collect_runtime_path_fields(version_data)

    def test_collect_runtime_paths_rejects_ambiguous_file_like_fields(self):
        for env_key, default in (
            ("APP_CONFIG", "./config/app.toml"),
            ("APP_CONFIG", "./config/Caddyfile"),
            ("APP_DATA_PATH", "./data"),
            ("APP_CONFIG_FILE", "./config"),
        ):
            with self.subTest(env_key=env_key, default=default):
                version_data = {
                    "additionalProperties": {
                        "formFields": [{"envKey": env_key, "default": default}]
                    }
                }

                with self.assertRaisesRegex(ValueError, "exact file lifecycle"):
                    runtime_utils.collect_runtime_path_fields(version_data)

    def test_render_init_script_uses_directory_path_fields(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {
                        "envKey": "APP_DATA_DIR",
                        "type": "text",
                        "required": True,
                        "default": "./data",
                    },
                    {
                        "envKey": "CUSTOM_CACHE_DIR",
                        "type": "text",
                        "required": False,
                        "default": "./cache",
                    },
                ]
            }
        }

        content = runtime_utils.render_init_script_content(version_data)

        self.assertIn('ensure_dir "APP_DATA_DIR" "./data"', content)
        self.assertIn('ensure_dir "CUSTOM_CACHE_DIR" "./cache"', content)
        self.assertNotIn("ensure_file_parent", content)
        self.assertIn('ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"', content)
        self.assertNotIn("mkdir -p ./data\n", content)

    def test_rendered_init_reads_quoted_env_paths_from_app_root(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data"},
                    {"envKey": "CUSTOM_CACHE_DIR", "default": "./cache"},
                ]
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(runtime_utils.render_init_script_content(version_data), encoding="utf-8")
            init_script.chmod(0o755)
            (root / ".env").write_text(
                "APP_DATA_DIR='./custom-data'\nCUSTOM_CACHE_DIR=\"./custom-cache\"\n",
                encoding="utf-8",
            )

            subprocess.run(["bash", str(init_script)], check=True, cwd=tmp)

            self.assertTrue((root / "custom-data").is_dir())
            self.assertTrue((root / "custom-cache").is_dir())
            self.assertFalse((pathlib.Path(tmp) / "custom-data").exists())

    def test_rendered_init_rejects_absolute_and_parent_traversal_values(self):
        version_data = {
            "additionalProperties": {
                "formFields": [{"envKey": "APP_DATA_DIR", "default": "./data"}]
            }
        }

        for configured in ("/tmp/adapter-escape", "../adapter-escape", "./data\tbad"):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp) / "app" / "latest"
                scripts_dir = root / "scripts"
                scripts_dir.mkdir(parents=True)
                init_script = scripts_dir / "init.sh"
                init_script.write_text(
                    runtime_utils.render_init_script_content(version_data),
                    encoding="utf-8",
                )
                init_script.chmod(0o755)
                (root / ".env").write_text(
                    f"APP_DATA_DIR={configured}\n",
                    encoding="utf-8",
                )

                proc = subprocess.run(
                    ["bash", str(init_script)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=tmp,
                )

                self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("unsafe APP_DATA_DIR path", proc.stderr)

    def test_rendered_init_rejects_symlink_escape(self):
        version_data = {
            "additionalProperties": {
                "formFields": [{"envKey": "APP_DATA_DIR", "default": "./data"}]
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            root = tmp_path / "app" / "latest"
            scripts_dir = root / "scripts"
            outside = tmp_path / "outside"
            scripts_dir.mkdir(parents=True)
            outside.mkdir()
            (root / "data").symlink_to(outside, target_is_directory=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(
                runtime_utils.render_init_script_content(version_data),
                encoding="utf-8",
            )
            init_script.chmod(0o755)
            (root / ".env").write_text("APP_DATA_DIR=./data/nested\n", encoding="utf-8")

            proc = subprocess.run(
                ["bash", str(init_script)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("unsafe APP_DATA_DIR path", proc.stderr)
            self.assertFalse((outside / "nested").exists())

    def test_rendered_init_rejects_inside_root_symlink(self):
        version_data = {
            "additionalProperties": {
                "formFields": [{"envKey": "APP_DATA_DIR", "default": "./data"}]
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            real_data = root / "real-data"
            scripts_dir.mkdir(parents=True)
            real_data.mkdir()
            (root / "data").symlink_to(real_data, target_is_directory=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(
                runtime_utils.render_init_script_content(version_data),
                encoding="utf-8",
            )
            init_script.chmod(0o755)
            (root / ".env").write_text("APP_DATA_DIR=./data/nested\n", encoding="utf-8")

            proc = subprocess.run(
                ["bash", str(init_script)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("unsafe APP_DATA_DIR path", proc.stderr)
            self.assertFalse((real_data / "nested").exists())

    def test_rendered_default_data_directory_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            root = tmp_path / "app" / "latest"
            scripts_dir = root / "scripts"
            outside = tmp_path / "outside"
            scripts_dir.mkdir(parents=True)
            outside.mkdir()
            (root / "data").symlink_to(outside, target_is_directory=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(
                runtime_utils.render_init_script_content({}),
                encoding="utf-8",
            )
            init_script.chmod(0o755)

            proc = subprocess.run(
                ["bash", str(init_script)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("unsafe PACKAGE_DATA_DIR path", proc.stderr)

    def test_finalize_runtime_scripts_uses_version_data_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp) / "demo"
            ver_dir = app_dir / "latest"
            ver_dir.mkdir(parents=True)
            (ver_dir / "data.yml").write_text(
                """
additionalProperties:
  formFields:
    - envKey: CONFIG_DIR
      type: text
      required: true
      default: ./data/config
""".strip()
                + "\n",
                encoding="utf-8",
            )

            subprocess.run(["bash", str(FINALIZE), str(app_dir), str(ver_dir)], check=True, cwd=ROOT)

            init_text = (ver_dir / "scripts" / "init.sh").read_text(encoding="utf-8")

            self.assertIn('ensure_dir "CONFIG_DIR" "./data/config"', init_text)
            self.assertNotIn("ensure_file_parent", init_text)
            self.assertNotIn("mkdir -p ./data\n", init_text)

    def test_finalize_runtime_scripts_fails_closed_for_file_like_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp) / "demo"
            ver_dir = app_dir / "latest"
            ver_dir.mkdir(parents=True)
            (ver_dir / "data.yml").write_text(
                """
additionalProperties:
  formFields:
    - envKey: APP_CONFIG
      type: text
      required: true
      default: ./config/app.toml
""".strip()
                + "\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["bash", str(FINALIZE), str(app_dir), str(ver_dir)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("exact file lifecycle", proc.stderr)
            self.assertFalse((ver_dir / "scripts" / "init.sh").exists())

    def test_generate_from_appspec_runtime_files_follow_volume_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            spec_path = tmp_path / "spec.json"
            out_dir = tmp_path / "out"
            spec_path.write_text(
                json.dumps(
                    {
                        "appKey": "demo",
                        "title": "Demo",
                        "description": "Demo app",
                        "shortDescZh": "示例应用",
                        "version": "latest",
                        "image": "ghcr.io/example/demo:latest",
                        "repository": "https://github.com/example/demo",
                        "dockerDocs": "https://hub.docker.com/r/example/demo",
                        "composeFile": "https://example.com/compose.yml",
                        "ports": [
                            {
                                "envKey": "PANEL_APP_PORT_HTTP",
                                "name": "HTTP Port",
                                "hostDefault": 18080,
                                "containerPort": 8080,
                            }
                        ],
                        "volumes": ["./data:/app/data"],
                        "formFields": [
                            {
                                "envKey": "CUSTOM_CACHE_DIR",
                                "type": "text",
                                "required": False,
                                "default": "./cache",
                                "labelZh": "自定义缓存目录",
                                "labelEn": "Custom cache directory",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            subprocess.run(
                ["python3", str(GENERATE), "--spec", str(spec_path), "--out-dir", str(out_dir)],
                check=True,
                cwd=ROOT,
            )

            init_text = (out_dir / "demo" / "latest" / "scripts" / "init.sh").read_text(encoding="utf-8")

            self.assertIn('ensure_dir "APP_DATA_DIR" "./data"', init_text)
            self.assertIn('ensure_dir "CUSTOM_CACHE_DIR" "./cache"', init_text)

    def test_generate_from_appspec_fails_before_output_for_file_like_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            spec_path = tmp_path / "spec.json"
            out_dir = tmp_path / "out"
            spec_path.write_text(
                json.dumps(
                    {
                        "appKey": "demo",
                        "title": "Demo",
                        "version": "latest",
                        "image": "ghcr.io/example/demo:latest",
                        "formFields": [
                            {
                                "envKey": "APP_CONFIG",
                                "type": "text",
                                "required": True,
                                "default": "./config/app.toml",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["python3", str(GENERATE), "--spec", str(spec_path), "--out-dir", str(out_dir)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("exact file lifecycle", proc.stderr)
            self.assertFalse((out_dir / "demo").exists())


if __name__ == "__main__":
    unittest.main()
