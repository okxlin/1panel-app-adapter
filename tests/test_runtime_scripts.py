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
    def test_render_init_script_uses_path_fields_and_file_parents(self):
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
                        "envKey": "CUSTOM_ENV_FILE",
                        "type": "text",
                        "required": False,
                        "default": "./data/custom.env",
                    },
                ]
            }
        }

        content = runtime_utils.render_init_script_content(version_data)

        self.assertIn('mkdir -p "${APP_DATA_DIR:-./data}"', content)
        self.assertIn('ensure_parent_dir "${CUSTOM_ENV_FILE:-./data/custom.env}"', content)
        self.assertNotIn("mkdir -p ./data\n", content)

    def test_finalize_runtime_scripts_uses_version_data_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp) / "demo"
            ver_dir = app_dir / "latest"
            ver_dir.mkdir(parents=True)
            (ver_dir / "data.yml").write_text(
                """
additionalProperties:
  formFields:
    - envKey: CONFIG_PATH
      type: text
      required: true
      default: ./data/config
    - envKey: CUSTOM_ENV_FILE
      type: text
      required: false
      default: ./data/custom.env
""".strip()
                + "\n",
                encoding="utf-8",
            )

            subprocess.run(["bash", str(FINALIZE), str(app_dir), str(ver_dir)], check=True, cwd=ROOT)

            init_text = (ver_dir / "scripts" / "init.sh").read_text(encoding="utf-8")

            self.assertIn('mkdir -p "${CONFIG_PATH:-./data/config}"', init_text)
            self.assertIn('ensure_parent_dir "${CUSTOM_ENV_FILE:-./data/custom.env}"', init_text)
            self.assertNotIn("mkdir -p ./data\n", init_text)

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
                                "envKey": "CUSTOM_ENV_FILE",
                                "type": "text",
                                "required": False,
                                "default": "./data/custom.env",
                                "labelZh": "自定义环境文件",
                                "labelEn": "Custom env file",
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

            self.assertIn('mkdir -p "${APP_DATA_DIR:-./data}"', init_text)
            self.assertIn('ensure_parent_dir "${CUSTOM_ENV_FILE:-./data/custom.env}"', init_text)


if __name__ == "__main__":
    unittest.main()
