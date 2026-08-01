import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
        for default in (
            "/srv/demo",
            "../outside",
            "./data/../../outside",
            "./data\tbad",
        ):
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

        self.assertIn(
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            content,
        )
        self.assertIn('ensure_dir "APP_DATA_DIR" "./data"', content)
        self.assertIn('ensure_dir "CUSTOM_CACHE_DIR" "./cache"', content)
        self.assertNotIn("ensure_file_parent", content)
        self.assertIn('ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"', content)
        self.assertNotIn("mkdir -p ./data\n", content)

    def test_rendered_init_applies_exact_nonrecursive_directory_ownership(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data"},
                ]
            }
        }
        permissions = runtime_utils.parse_directory_permissions(
            [f"APP_DATA_DIR={os.getuid()}:{os.getgid()}:0750"],
            runtime_utils.collect_runtime_path_fields(version_data),
        )

        content = runtime_utils.render_init_script_content(
            version_data,
            directory_permissions=permissions,
        )

        self.assertIn("ensure_owned_dir()", content)
        self.assertIn(
            f'ensure_owned_dir "APP_DATA_DIR" "./data" "{os.getuid()}" "{os.getgid()}" "0750"',
            content,
        )
        self.assertIn('[[ "$(id -u)" == "0" ]]', content)
        self.assertIn('mkdir -- "$path"', content)
        self.assertIn('chmod "$mode" -- "$path"', content)
        self.assertIn('chown --no-dereference "$uid:$gid" -- "$path"', content)
        self.assertNotIn("install -d", content)
        self.assertNotIn("chown -R", content)
        self.assertNotIn("chmod -R", content)

        if os.geteuid() != 0:
            self.skipTest("ownership mutation requires root")

        with tempfile.TemporaryDirectory(prefix="adapter-owned-", dir="/opt") as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(content, encoding="utf-8")
            init_script.chmod(0o755)

            subprocess.run(["bash", str(init_script)], check=True, cwd=tmp)

            data_dir = root / "data"
            stat = data_dir.stat()
            self.assertEqual(stat.st_uid, os.getuid())
            self.assertEqual(stat.st_gid, os.getgid())
            self.assertEqual(stat.st_mode & 0o777, 0o750)

    def test_rendered_init_preserves_nested_directory_support_without_owner_plan(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data/nested"},
                ]
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(
                runtime_utils.render_init_script_content(version_data), encoding="utf-8"
            )
            init_script.chmod(0o755)

            subprocess.run(["bash", str(init_script)], check=True, cwd=tmp)

            self.assertTrue((root / "data" / "nested").is_dir())

    def test_owned_directory_rejects_nested_path_before_mutation(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data/nested"},
                ]
            }
        }
        permissions = runtime_utils.parse_directory_permissions(
            [f"APP_DATA_DIR={os.getuid()}:{os.getgid()}:0700"],
            runtime_utils.collect_runtime_path_fields(version_data),
        )

        content = runtime_utils.render_init_script_content(
            version_data,
            directory_permissions=permissions,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(content, encoding="utf-8")
            init_script.chmod(0o755)

            proc = subprocess.run(
                ["bash", str(init_script)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("direct child", proc.stderr)
            self.assertFalse((root / "data").exists())

    def test_owned_directory_requires_privileged_init(self):
        if os.geteuid() == 0:
            self.skipTest("non-root behavior requires a non-root test process")

        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data"},
                ]
            }
        }
        permissions = runtime_utils.parse_directory_permissions(
            [f"APP_DATA_DIR={os.getuid()}:{os.getgid()}:0700"],
            runtime_utils.collect_runtime_path_fields(version_data),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(
                runtime_utils.render_init_script_content(
                    version_data,
                    directory_permissions=permissions,
                ),
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
            self.assertIn("must run as root", proc.stderr)
            self.assertFalse((root / "data").exists())

    def test_directory_ownership_specs_fail_closed(self):
        path_fields = [{"envKey": "APP_DATA_DIR", "default": "./data"}]
        invalid_specs = (
            "UNKNOWN_DIR=472:0:0750",
            "APP_DATA_DIR=unknown:0:0750",
            "APP_DATA_DIR=472:group:0750",
            "APP_DATA_DIR=472:0:07777",
            "APP_DATA_DIR=472:0:0550",
            "APP_DATA_DIR=472:0",
            "APP_DATA_DIR=4294967295:0:0750",
            "APP_DATA_DIR=472:4294967295:0750",
        )

        for value in invalid_specs:
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime_utils.parse_directory_permissions([value], path_fields)

        with self.assertRaisesRegex(ValueError, "duplicate"):
            runtime_utils.parse_directory_permissions(
                ["APP_DATA_DIR=472:0:0750", "APP_DATA_DIR=472:0:0755"],
                path_fields,
            )

    def test_owned_directory_rejects_symlink_before_permission_change(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data"},
                ]
            }
        }
        permissions = runtime_utils.parse_directory_permissions(
            [f"APP_DATA_DIR={os.getuid()}:{os.getgid()}:0700"],
            runtime_utils.collect_runtime_path_fields(version_data),
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            root = tmp_path / "app" / "latest"
            scripts_dir = root / "scripts"
            outside = tmp_path / "outside"
            scripts_dir.mkdir(parents=True)
            outside.mkdir(mode=0o755)
            original = outside.stat()
            (root / "data").symlink_to(outside, target_is_directory=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(
                runtime_utils.render_init_script_content(
                    version_data,
                    directory_permissions=permissions,
                ),
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

            after = outside.stat()
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("unsafe APP_DATA_DIR path", proc.stderr)
            self.assertEqual(after.st_uid, original.st_uid)
            self.assertEqual(after.st_gid, original.st_gid)
            self.assertEqual(after.st_mode & 0o777, original.st_mode & 0o777)

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
            init_script.write_text(
                runtime_utils.render_init_script_content(version_data), encoding="utf-8"
            )
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
            with self.subTest(
                configured=configured
            ), tempfile.TemporaryDirectory() as tmp:
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
""".strip() + "\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["bash", str(FINALIZE), str(app_dir), str(ver_dir)],
                check=True,
                cwd=ROOT,
            )

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
""".strip() + "\n",
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

    def test_finalize_runtime_scripts_requires_explicit_replacement_for_owner_plan(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp) / "demo"
            ver_dir = app_dir / "latest"
            scripts_dir = ver_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (ver_dir / "data.yml").write_text(
                """
additionalProperties:
  formFields:
    - envKey: APP_DATA_DIR
      type: text
      required: true
      default: ./data
""".strip() + "\n",
                encoding="utf-8",
            )
            (scripts_dir / "init.sh").write_text(
                "#!/bin/sh\nexit 0\n", encoding="utf-8"
            )

            base_args = [
                "bash",
                str(FINALIZE),
                str(app_dir),
                str(ver_dir),
                "--dir-owner",
                f"APP_DATA_DIR={os.getuid()}:{os.getgid()}:0750",
            ]
            refused = subprocess.run(
                base_args,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
            self.assertIn("--replace-init", refused.stderr)
            self.assertEqual(
                (scripts_dir / "init.sh").read_text(encoding="utf-8"),
                "#!/bin/sh\nexit 0\n",
            )

            subprocess.run(base_args + ["--replace-init"], check=True, cwd=ROOT)
            init_text = (scripts_dir / "init.sh").read_text(encoding="utf-8")
            self.assertIn(
                f'ensure_owned_dir "APP_DATA_DIR" "./data" "{os.getuid()}" "{os.getgid()}" "0750"',
                init_text,
            )

    def test_finalize_runtime_scripts_rejects_symlinked_scripts_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            app_dir = tmp_path / "demo"
            ver_dir = app_dir / "latest"
            outside = tmp_path / "outside"
            ver_dir.mkdir(parents=True)
            outside.mkdir()
            (ver_dir / "data.yml").write_text(
                "additionalProperties:\n  formFields: []\n", encoding="utf-8"
            )
            (ver_dir / "scripts").symlink_to(outside, target_is_directory=True)

            proc = subprocess.run(
                ["bash", str(FINALIZE), str(app_dir), str(ver_dir)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("scripts directory", proc.stderr)
            self.assertFalse((outside / "init.sh").exists())

    def test_finalize_runtime_scripts_rejects_symlinked_init_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            app_dir = tmp_path / "demo"
            ver_dir = app_dir / "latest"
            scripts_dir = ver_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (ver_dir / "data.yml").write_text(
                """
additionalProperties:
  formFields:
    - envKey: APP_DATA_DIR
      type: text
      required: true
      default: ./data
""".strip() + "\n",
                encoding="utf-8",
            )
            outside_init = tmp_path / "outside-init.sh"
            outside_init.write_text("do not replace\n", encoding="utf-8")
            (scripts_dir / "init.sh").symlink_to(outside_init)

            proc = subprocess.run(
                [
                    "bash",
                    str(FINALIZE),
                    str(app_dir),
                    str(ver_dir),
                    "--dir-owner",
                    f"APP_DATA_DIR={os.getuid()}:{os.getgid()}:0750",
                    "--replace-init",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("init.sh", proc.stderr)
            self.assertEqual(
                outside_init.read_text(encoding="utf-8"), "do not replace\n"
            )

    def test_finalizer_directory_fd_does_not_follow_swapped_scripts_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = pathlib.Path(tmp) / "latest"
            scripts_dir = version_dir / "scripts"
            moved_scripts = version_dir / "scripts-original"
            outside = pathlib.Path(tmp) / "outside"
            scripts_dir.mkdir(parents=True)
            outside.mkdir()
            (version_dir / "data.yml").write_text(
                "additionalProperties:\n  formFields: []\n", encoding="utf-8"
            )
            real_replace = os.replace
            swapped = False

            def swap_before_replace(*args, **kwargs):
                nonlocal swapped
                if not swapped:
                    scripts_dir.rename(moved_scripts)
                    scripts_dir.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return real_replace(*args, **kwargs)

            with mock.patch.object(
                runtime_utils.os, "replace", side_effect=swap_before_replace
            ), self.assertRaisesRegex(ValueError, "changed during finalization"):
                runtime_utils.finalize_lifecycle_scripts(
                    version_dir / "data.yml",
                    scripts_dir / "init.sh",
                )

            self.assertTrue((moved_scripts / "init.sh").is_file())
            self.assertFalse((outside / "init.sh").exists())
            self.assertFalse((outside / "upgrade.sh").exists())
            self.assertFalse((outside / "uninstall.sh").exists())

    def test_finalizer_atomic_replace_does_not_follow_swapped_init_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = pathlib.Path(tmp) / "latest"
            scripts_dir = version_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (version_dir / "data.yml").write_text(
                "additionalProperties:\n  formFields: []\n", encoding="utf-8"
            )
            init_script = scripts_dir / "init.sh"
            init_script.write_text("old init\n", encoding="utf-8")
            outside_init = pathlib.Path(tmp) / "outside-init.sh"
            outside_init.write_text("do not replace\n", encoding="utf-8")
            real_replace = os.replace
            swapped = False

            def swap_before_replace(*args, **kwargs):
                nonlocal swapped
                if not swapped:
                    init_script.unlink()
                    init_script.symlink_to(outside_init)
                    swapped = True
                return real_replace(*args, **kwargs)

            with mock.patch.object(
                runtime_utils.os, "replace", side_effect=swap_before_replace
            ):
                runtime_utils.finalize_lifecycle_scripts(
                    version_dir / "data.yml",
                    init_script,
                    replace_init=True,
                )

            self.assertFalse(init_script.is_symlink())
            self.assertTrue(init_script.read_text(encoding="utf-8").startswith("#!/"))
            self.assertEqual(
                outside_init.read_text(encoding="utf-8"), "do not replace\n"
            )

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
                [
                    "python3",
                    str(GENERATE),
                    "--spec",
                    str(spec_path),
                    "--out-dir",
                    str(out_dir),
                ],
                check=True,
                cwd=ROOT,
            )

            init_text = (out_dir / "demo" / "latest" / "scripts" / "init.sh").read_text(
                encoding="utf-8"
            )

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
                [
                    "python3",
                    str(GENERATE),
                    "--spec",
                    str(spec_path),
                    "--out-dir",
                    str(out_dir),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("exact file lifecycle", proc.stderr)
            self.assertFalse((out_dir / "demo").exists())

    def test_generate_from_appspec_preserves_optional_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            spec_path = tmp_path / "spec.json"
            out_dir = tmp_path / "out"
            optional_evidence = {
                "sourceRevision": {"tag": "v1.2.3", "commit": "a" * 40},
                "imageEvidence": {
                    "digest": "sha256:" + "b" * 64,
                    "platforms": ["linux/amd64"],
                },
                "licenseEvidence": {
                    "spdx": "MIT",
                    "url": "https://example.com/LICENSE",
                },
                "logoEvidence": {
                    "source": "https://example.com/logo.png",
                    "license": "MIT",
                    "sha256": "c" * 64,
                },
            }
            spec_path.write_text(
                json.dumps(
                    {
                        "appKey": "demo",
                        "title": "Demo",
                        "version": "latest",
                        "image": "ghcr.io/example/demo:latest",
                        "sourceEvidence": {
                            "repository": "https://github.com/example/demo",
                            "dockerDocs": "https://example.com/docker",
                            "composeFile": "https://example.com/compose.yml",
                            **optional_evidence,
                        },
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python3",
                    str(GENERATE),
                    "--spec",
                    str(spec_path),
                    "--out-dir",
                    str(out_dir),
                ],
                check=True,
                cwd=ROOT,
            )
            evidence = json.loads(
                (out_dir / "demo" / "source-evidence.json").read_text(encoding="utf-8")
            )

        for field, value in optional_evidence.items():
            with self.subTest(field=field):
                self.assertEqual(evidence[field], value)

    def test_generate_from_appspec_validation_rejects_invalid_optional_evidence(self):
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
                        "sourceEvidence": {
                            "repository": "https://github.com/example/demo",
                            "dockerDocs": "https://example.com/docker",
                            "composeFile": "https://example.com/compose.yml",
                            "imageEvidence": {
                                "digest": "sha256:not-a-digest",
                                "platforms": ["linux/amd64"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python3",
                    str(GENERATE),
                    "--spec",
                    str(spec_path),
                    "--out-dir",
                    str(out_dir),
                    "--validate",
                    "--require-validate",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("imageEvidence.digest", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
