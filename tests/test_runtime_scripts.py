import importlib.util
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
FINALIZE = SCRIPTS_DIR / "finalize_runtime_scripts.sh"
GENERATE = SCRIPTS_DIR / "generate-from-appspec.py"
GEN_ENV_SAMPLE = SCRIPTS_DIR / "gen_env_sample.py"
RUNTIME_UTILS = SCRIPTS_DIR / "runtime_script_utils.py"
SCAFFOLD = SCRIPTS_DIR / "scaffold-v2.sh"
MIGRATE = SCRIPTS_DIR / "migrate-v1-to-v2.sh"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime_utils = load_module(RUNTIME_UTILS, "runtime_script_utils_test")


class RuntimeScriptGenerationTest(unittest.TestCase):
    def assert_uninstall_runs_from_version_dir(
        self, uninstall_script: pathlib.Path, version_dir: pathlib.Path
    ) -> None:
        unrelated_cwd = version_dir.parent / "unrelated"
        unrelated_cwd.mkdir()
        for case, docker_version_status, legacy_version_status, expected_command in (
            ("compose-v2", 0, 0, "docker:compose down"),
            ("legacy-fallback", 1, 0, "docker-compose:down"),
            ("compose-unavailable", 1, 1, None),
        ):
            with self.subTest(case=case):
                capture_dir = version_dir.parent / f"capture-{case}"
                fake_bin = version_dir.parent / f"fake-bin-{case}"
                capture_dir.mkdir()
                fake_bin.mkdir()

                fake_docker = fake_bin / "docker"
                fake_docker.write_text(
                    "#!/bin/sh\n"
                    "if [ \"$*\" = 'compose version' ]; then\n"
                    f"  exit {docker_version_status}\n"
                    "fi\n"
                    "printf '%s\\n' \"$PWD\" > \"$CAPTURE_DIR/pwd\"\n"
                    "printf 'docker:%s\\n' \"$*\" > \"$CAPTURE_DIR/command\"\n",
                    encoding="utf-8",
                )
                fake_docker.chmod(0o755)

                legacy_compose = fake_bin / "docker-compose"
                legacy_compose.write_text(
                    "#!/bin/sh\n"
                    "if [ \"$*\" = 'version' ]; then\n"
                    f"  exit {legacy_version_status}\n"
                    "fi\n"
                    "printf '%s\\n' \"$PWD\" > \"$CAPTURE_DIR/pwd\"\n"
                    "printf 'docker-compose:%s\\n' \"$*\" > \"$CAPTURE_DIR/command\"\n",
                    encoding="utf-8",
                )
                legacy_compose.chmod(0o755)

                env = os.environ.copy()
                env["CAPTURE_DIR"] = str(capture_dir)
                env["PATH"] = f"{fake_bin}:{env['PATH']}"

                proc = subprocess.run(
                    ["bash", str(uninstall_script)],
                    cwd=unrelated_cwd,
                    env=env,
                    text=True,
                    capture_output=True,
                )

                if expected_command is None:
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn("Docker Compose is not available", proc.stderr)
                    self.assertFalse((capture_dir / "command").exists())
                    continue

                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(
                    (capture_dir / "pwd").read_text(encoding="utf-8").strip(),
                    str(version_dir.resolve()),
                )
                self.assertEqual(
                    (capture_dir / "command").read_text(encoding="utf-8").strip(),
                    expected_command,
                )

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

    def test_fixed_directory_ownership_specs_are_package_local_direct_children(self):
        permissions = runtime_utils.parse_fixed_directory_permissions(
            [f"./config={os.getuid()}:{os.getgid()}:0750"]
        )

        self.assertEqual(
            permissions,
            {
                "./config": {
                    "uid": str(os.getuid()),
                    "gid": str(os.getgid()),
                    "mode": "0750",
                }
            },
        )

        for value in (
            "/config=472:0:0750",
            "../config=472:0:0750",
            "./config/nested=472:0:0750",
            "./config=unknown:0:0750",
            "./config=472:0:0550",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime_utils.parse_fixed_directory_permissions([value])

    def test_rendered_init_applies_fixed_bind_owner_without_form_field(self):
        fixed_permissions = runtime_utils.parse_fixed_directory_permissions(
            [f"./config={os.getuid()}:{os.getgid()}:0750"]
        )

        content = runtime_utils.render_init_script_content(
            {"additionalProperties": {"formFields": []}},
            fixed_directory_permissions=fixed_permissions,
        )

        self.assertIn(
            f'ensure_fixed_owned_dir "./config" "{os.getuid()}" "{os.getgid()}" "0750"',
            content,
        )
        self.assertNotIn('configured_value "./config"', content)

        if os.geteuid() != 0:
            self.skipTest("ownership mutation requires root")

        with tempfile.TemporaryDirectory(prefix="adapter-fixed-owned-", dir="/opt") as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            init_script = scripts_dir / "init.sh"
            init_script.write_text(content, encoding="utf-8")
            init_script.chmod(0o755)

            subprocess.run(["bash", str(init_script)], check=True, cwd=tmp)

            config_dir = root / "config"
            info = config_dir.stat()
            self.assertEqual(info.st_uid, os.getuid())
            self.assertEqual(info.st_gid, os.getgid())
            self.assertEqual(info.st_mode & 0o777, 0o750)

    def test_fixed_and_form_backed_owner_plans_cannot_target_same_directory(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_CONFIG_DIR", "default": "./config"},
                ]
            }
        }
        path_fields = runtime_utils.collect_runtime_path_fields(version_data)
        directory_permissions = runtime_utils.parse_directory_permissions(
            ["APP_CONFIG_DIR=472:0:0750"], path_fields
        )
        fixed_directory_permissions = runtime_utils.parse_fixed_directory_permissions(
            ["./config=977:977:0700"]
        )

        with self.assertRaisesRegex(ValueError, "duplicate directory ownership target"):
            runtime_utils.render_init_script_content(
                version_data,
                directory_permissions=directory_permissions,
                fixed_directory_permissions=fixed_directory_permissions,
            )

    def test_runtime_form_and_fixed_owner_targets_cannot_converge(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data"},
                ]
            }
        }
        path_fields = runtime_utils.collect_runtime_path_fields(version_data)
        directory_permissions = runtime_utils.parse_directory_permissions(
            ["APP_DATA_DIR=472:0:0750"], path_fields
        )
        fixed_directory_permissions = runtime_utils.parse_fixed_directory_permissions(
            ["./config=977:977:0700"]
        )
        content = runtime_utils.render_init_script_content(
            version_data,
            directory_permissions=directory_permissions,
            fixed_directory_permissions=fixed_directory_permissions,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            (root / ".env").write_text("APP_DATA_DIR=./config\n", encoding="utf-8")
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
            self.assertIn("duplicate directory ownership target", proc.stderr)
            self.assertFalse((root / "config").exists())

    def test_runtime_form_owner_targets_cannot_converge(self):
        version_data = {
            "additionalProperties": {
                "formFields": [
                    {"envKey": "APP_DATA_DIR", "default": "./data"},
                    {"envKey": "APP_CACHE_DIR", "default": "./cache"},
                ]
            }
        }
        path_fields = runtime_utils.collect_runtime_path_fields(version_data)
        directory_permissions = runtime_utils.parse_directory_permissions(
            ["APP_DATA_DIR=472:0:0750", "APP_CACHE_DIR=977:977:0700"],
            path_fields,
        )
        content = runtime_utils.render_init_script_content(
            version_data,
            directory_permissions=directory_permissions,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "app" / "latest"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            (root / ".env").write_text(
                "APP_DATA_DIR=./shared\nAPP_CACHE_DIR=./shared\n", encoding="utf-8"
            )
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
            self.assertIn("duplicate directory ownership target", proc.stderr)
            self.assertFalse((root / "shared").exists())

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

    def test_finalize_runtime_scripts_supports_fixed_bind_owner_without_form_field(self):
        with tempfile.TemporaryDirectory(prefix="adapter-fixed-cli-") as tmp:
            app_dir = pathlib.Path(tmp) / "demo"
            ver_dir = app_dir / "latest"
            ver_dir.mkdir(parents=True)
            (ver_dir / "data.yml").write_text(
                "additionalProperties:\n  formFields: []\n", encoding="utf-8"
            )

            subprocess.run(
                [
                    "bash",
                    str(FINALIZE),
                    str(app_dir),
                    str(ver_dir),
                    "--fixed-dir-owner",
                    f"./config={os.getuid()}:{os.getgid()}:0750",
                ],
                check=True,
                cwd=ROOT,
            )

            init_text = (ver_dir / "scripts" / "init.sh").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                f'ensure_fixed_owned_dir "./config" "{os.getuid()}" "{os.getgid()}" "0750"',
                init_text,
            )

    def test_finalize_lifecycle_preserves_positional_replace_init_argument(self):
        with tempfile.TemporaryDirectory(prefix="adapter-positional-finalize-") as tmp:
            ver_dir = pathlib.Path(tmp) / "latest"
            scripts_dir = ver_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            data_yml = ver_dir / "data.yml"
            data_yml.write_text(
                "additionalProperties:\n  formFields: []\n", encoding="utf-8"
            )
            init_script = scripts_dir / "init.sh"
            init_script.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")

            runtime_utils.finalize_lifecycle_scripts(
                data_yml, init_script, (), True
            )

            self.assertNotIn("exit 7", init_script.read_text(encoding="utf-8"))

    def test_finalize_lifecycle_generates_context_bound_non_destructive_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="adapter-finalize-uninstall-") as tmp:
            ver_dir = pathlib.Path(tmp) / "demo" / "latest"
            scripts_dir = ver_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            data_yml = ver_dir / "data.yml"
            data_yml.write_text(
                "additionalProperties:\n  formFields: []\n", encoding="utf-8"
            )

            runtime_utils.finalize_lifecycle_scripts(
                data_yml, scripts_dir / "init.sh"
            )

            self.assert_uninstall_runs_from_version_dir(
                scripts_dir / "uninstall.sh", ver_dir
            )

    def test_scaffold_generates_context_bound_non_destructive_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="adapter-scaffold-uninstall-") as tmp:
            out_dir = pathlib.Path(tmp) / "out"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(out_dir),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            ver_dir = out_dir / "demo" / "1.0"

            self.assert_uninstall_runs_from_version_dir(
                ver_dir / "scripts" / "uninstall.sh", ver_dir
            )

    def test_env_sample_helper_replaces_legacy_container_name_form_field(self):
        with tempfile.TemporaryDirectory(prefix="adapter-env-container-name-") as tmp:
            version_dir = pathlib.Path(tmp) / "demo" / "1.0"
            version_dir.mkdir(parents=True)
            data_yml = version_dir / "data.yml"
            data_yml.write_text(
                "additionalProperties:\n"
                "  formFields:\n"
                "    - envKey: CONTAINER_NAME\n"
                "      type: text\n"
                "      required: false\n"
                "      default: ''\n",
                encoding="utf-8",
            )
            compose = version_dir / "docker-compose.yml"
            compose.write_text(
                "services:\n"
                "  demo:\n"
                "    image: example/demo:1.0\n"
                "    container_name: ${CONTAINER_NAME}\n",
                encoding="utf-8",
            )
            env_sample = version_dir / ".env.sample"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(GEN_ENV_SAMPLE),
                    str(data_yml),
                    str(env_sample),
                    str(compose),
                    "demo-compose-check",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(
                env_sample.read_text(encoding="utf-8").splitlines(),
                ["CONTAINER_NAME=demo-compose-check"],
            )

    def test_scaffold_delivers_licensed_default_logo_with_hash_bound_evidence(self):
        with tempfile.TemporaryDirectory(prefix="adapter-scaffold-logo-") as tmp:
            out_dir = pathlib.Path(tmp) / "out"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(out_dir),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            app_dir = out_dir / "demo"
            logo = app_dir / "logo.png"
            notice = app_dir / "ASSET-LICENSES" / "default-logo.txt"
            source = app_dir / "assets" / "default-logo.svg"
            evidence = json.loads(
                (app_dir / "source-evidence.json").read_text(encoding="utf-8")
            )

            self.assertTrue(notice.is_file())
            self.assertEqual(
                source.read_bytes(), (ROOT / "assets" / "default-logo.svg").read_bytes()
            )
            self.assertIn(
                "CONTAINER_NAME=demo-compose-check",
                (app_dir / "1.0" / ".env.sample").read_text(encoding="utf-8"),
            )
            self.assertEqual(evidence["logoEvidence"]["license"], "MIT")
            self.assertEqual(
                evidence["logoEvidence"]["sha256"],
                hashlib.sha256(logo.read_bytes()).hexdigest(),
            )
            self.assertEqual(evidence["redistributionEvidence"]["status"], "verified")
            self.assertEqual(
                set(evidence["redistributionEvidence"]["requiredFiles"]),
                {
                    "ASSET-LICENSES/default-logo.txt",
                    "assets/default-logo.svg",
                },
            )
            materials = {
                item["path"]: item
                for item in evidence["redistributionEvidence"]["materials"]
            }
            self.assertEqual(
                materials["ASSET-LICENSES/default-logo.txt"]["sha256"],
                hashlib.sha256(notice.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                materials["assets/default-logo.svg"]["sha256"],
                hashlib.sha256(source.read_bytes()).hexdigest(),
            )

    def test_scaffold_force_rejects_symlinked_default_logo_notice(self):
        with tempfile.TemporaryDirectory(prefix="adapter-scaffold-logo-link-") as tmp:
            tmp_path = pathlib.Path(tmp)
            out_dir = tmp_path / "out"
            license_dir = out_dir / "demo" / "ASSET-LICENSES"
            license_dir.mkdir(parents=True)
            external_notice = tmp_path / "external-notice.txt"
            sentinel = "external sentinel must remain unchanged\n"
            external_notice.write_text(sentinel, encoding="utf-8")
            (license_dir / "default-logo.txt").symlink_to(external_notice)

            proc = subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(out_dir),
                    "--force",
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(external_notice.read_text(encoding="utf-8"), sentinel)

    def test_migration_delivers_licensed_default_logo_with_hash_bound_evidence(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-logo-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            source_app = source_root / "demo"
            (source_app / "logo.png").unlink()
            out_dir = tmp_path / "out"

            subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_app),
                    "--out",
                    str(out_dir),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                check=True,
                cwd=ROOT,
            )
            app_dir = out_dir / "demo"
            logo = app_dir / "logo.png"
            notice = app_dir / "ASSET-LICENSES" / "default-logo.txt"
            source = app_dir / "assets" / "default-logo.svg"
            evidence = json.loads(
                (app_dir / "source-evidence.json").read_text(encoding="utf-8")
            )
            notice_exists = notice.is_file()
            source_exists = source.is_file()
            delivered_logo_hash = hashlib.sha256(logo.read_bytes()).hexdigest()
            delivered_notice_hash = hashlib.sha256(notice.read_bytes()).hexdigest()
            delivered_source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            env_sample = (app_dir / "2.0" / ".env.sample").read_text(encoding="utf-8")

        self.assertTrue(notice_exists)
        self.assertTrue(source_exists)
        self.assertIn("CONTAINER_NAME=demo-compose-check", env_sample)
        redistribution = evidence["redistributionEvidence"]
        self.assertEqual(redistribution["status"], "verified")
        self.assertEqual(
            redistribution["assets"][0]["sha256"],
            delivered_logo_hash,
        )
        material_hashes = {
            item["path"]: item["sha256"] for item in redistribution["materials"]
        }
        self.assertEqual(
            material_hashes["ASSET-LICENSES/default-logo.txt"], delivered_notice_hash
        )
        self.assertEqual(
            material_hashes["assets/default-logo.svg"], delivered_source_hash
        )

    def test_migration_removes_legacy_container_name_form_field(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-container-name-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            source_app = source_root / "demo"
            source_version_data = source_app / "1.0" / "data.yml"
            version_data = yaml.safe_load(
                source_version_data.read_text(encoding="utf-8")
            )
            fields = version_data["additionalProperties"]["formFields"]
            fields.append({
                "default": "",
                "edit": True,
                "envKey": "CONTAINER_NAME",
                "required": False,
                "type": "text",
            })
            source_version_data.write_text(
                yaml.safe_dump(version_data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_app),
                    "--out",
                    str(out_dir),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            delivered_version = out_dir / "demo" / "2.0"
            delivered_data = yaml.safe_load(
                (delivered_version / "data.yml").read_text(encoding="utf-8")
            )
            delivered_fields = delivered_data["additionalProperties"]["formFields"]
            self.assertNotIn(
                "CONTAINER_NAME",
                {field.get("envKey") for field in delivered_fields},
            )
            container_lines = [
                line
                for line in (delivered_version / ".env.sample")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.startswith("CONTAINER_NAME=")
            ]
            self.assertEqual(container_lines, ["CONTAINER_NAME=demo-compose-check"])

    def test_migration_rejects_symlinked_default_logo_notice(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-logo-link-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            source_app = source_root / "demo"
            (source_app / "logo.png").unlink()

            out_dir = tmp_path / "out"
            license_dir = out_dir / "demo" / "ASSET-LICENSES"
            license_dir.mkdir(parents=True)
            external_notice = tmp_path / "external-notice.txt"
            sentinel = "external sentinel must remain unchanged\n"
            external_notice.write_text(sentinel, encoding="utf-8")
            (license_dir / "default-logo.txt").symlink_to(external_notice)

            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_app),
                    "--out",
                    str(out_dir),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(external_notice.read_text(encoding="utf-8"), sentinel)

    def test_scaffold_rejects_escaping_app_key_and_version(self):
        with tempfile.TemporaryDirectory(prefix="adapter-scaffold-components-") as tmp:
            tmp_path = pathlib.Path(tmp)
            cases = (
                ("app-key", "../escaped-app", "1.0", "escaped-app"),
                ("version", "demo", "../../escaped-version", "escaped-version"),
            )
            for label, app_key, version, escaped_name in cases:
                with self.subTest(label=label):
                    case_root = tmp_path / label
                    out_dir = case_root / "out"
                    proc = subprocess.run(
                        [
                            "bash",
                            str(SCAFFOLD),
                            "--app-key",
                            app_key,
                            "--title",
                            "Demo",
                            "--image",
                            "example/demo:1.0",
                            "--version",
                            version,
                            "--out-dir",
                            str(out_dir),
                            "--source-repository",
                            "https://example.invalid/demo",
                            "--source-docker-docs",
                            "https://example.invalid/demo/docker",
                            "--source-compose-file",
                            "https://example.invalid/demo/compose.yml",
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=ROOT,
                    )

                    self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertFalse((case_root / escaped_name).exists())

    def test_migration_rejects_escaping_app_key_and_target_version(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-components-") as tmp:
            tmp_path = pathlib.Path(tmp)
            cases = (
                ("app-key", "../escaped-app", "2.0", "escaped-app"),
                ("version", "demo", "../../escaped-version", "escaped-version"),
            )
            for label, app_key, target_version, escaped_name in cases:
                with self.subTest(label=label):
                    case_root = tmp_path / label
                    source_root = case_root / "source"
                    subprocess.run(
                        [
                            "bash",
                            str(SCAFFOLD),
                            "--app-key",
                            "demo",
                            "--title",
                            "Demo",
                            "--image",
                            "example/demo:1.0",
                            "--version",
                            "1.0",
                            "--out-dir",
                            str(source_root),
                            "--source-repository",
                            "https://example.invalid/demo",
                            "--source-docker-docs",
                            "https://example.invalid/demo/docker",
                            "--source-compose-file",
                            "https://example.invalid/demo/compose.yml",
                        ],
                        check=True,
                        cwd=ROOT,
                    )
                    source_app = source_root / "demo"
                    if app_key != "demo":
                        data_path = source_app / "data.yml"
                        data_path.write_text(
                            data_path.read_text(encoding="utf-8").replace(
                                "key: demo", f"key: {app_key}", 1
                            ),
                            encoding="utf-8",
                        )

                    proc = subprocess.run(
                        [
                            "bash",
                            str(MIGRATE),
                            "--src",
                            str(source_app),
                            "--out",
                            str(case_root / "out"),
                            "--version",
                            "1.0",
                            "--target-version",
                            target_version,
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=ROOT,
                    )

                    self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertFalse((case_root / escaped_name).exists())

    def test_migration_rejects_symlinked_output_app_directory(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-app-link-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            out_dir = tmp_path / "out"
            out_dir.mkdir()
            external = tmp_path / "external"
            external.mkdir()
            sentinel = "external sentinel must remain unchanged\n"
            (external / "data.yml").write_text(sentinel, encoding="utf-8")
            (out_dir / "demo").symlink_to(external, target_is_directory=True)

            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_root / "demo"),
                    "--out",
                    str(out_dir),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual((external / "data.yml").read_text(encoding="utf-8"), sentinel)

    def test_migration_preserves_and_delivers_existing_redistribution_materials(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-materials-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            source_app = source_root / "demo"
            app_license = source_app / "LICENSE"
            app_license.write_text("application license\n", encoding="utf-8")
            evidence_path = source_app / "source-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            redistribution = evidence["redistributionEvidence"]
            redistribution["requiredFiles"].append("LICENSE")
            redistribution["materials"].append({
                "path": "LICENSE",
                "sha256": hashlib.sha256(app_license.read_bytes()).hexdigest(),
                "purpose": "application license",
            })
            evidence["licenseEvidence"] = {"spdx": "MIT"}
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            out_dir = tmp_path / "out"
            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_app),
                    "--out",
                    str(out_dir),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            migrated = out_dir / "demo"
            migrated_evidence = json.loads(
                (migrated / "source-evidence.json").read_text(encoding="utf-8")
            )
            migrated_redistribution = migrated_evidence["redistributionEvidence"]
            self.assertEqual(
                (migrated / "LICENSE").read_text(encoding="utf-8"),
                "application license\n",
            )
            self.assertIn("LICENSE", migrated_redistribution["requiredFiles"])
            self.assertIn(
                "LICENSE",
                {item["path"] for item in migrated_redistribution["materials"]},
            )

    def test_migration_auto_detects_only_real_version_directories(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-auto-version-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            out_dir = tmp_path / "out"

            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_root / "demo"),
                    "--out",
                    str(out_dir),
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((out_dir / "demo" / "2.0" / "docker-compose.yml").is_file())

    def test_migration_rejects_redistribution_material_hash_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-material-hash-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            source_app = source_root / "demo"
            license_path = source_app / "LICENSE"
            license_path.write_text("actual license text\n", encoding="utf-8")
            evidence_path = source_app / "source-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            redistribution = evidence["redistributionEvidence"]
            redistribution["requiredFiles"].append("LICENSE")
            redistribution["materials"].append({
                "path": "LICENSE",
                "sha256": hashlib.sha256(b"different license text\n").hexdigest(),
                "purpose": "application license",
            })
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_app),
                    "--out",
                    str(tmp_path / "out"),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotIn("OK: migrated", proc.stdout)

    def test_migration_copies_unreferenced_redistribution_material_ledger_entries(self):
        with tempfile.TemporaryDirectory(prefix="adapter-migrate-extra-material-") as tmp:
            tmp_path = pathlib.Path(tmp)
            source_root = tmp_path / "source"
            subprocess.run(
                [
                    "bash",
                    str(SCAFFOLD),
                    "--app-key",
                    "demo",
                    "--title",
                    "Demo",
                    "--image",
                    "example/demo:1.0",
                    "--version",
                    "1.0",
                    "--out-dir",
                    str(source_root),
                    "--source-repository",
                    "https://example.invalid/demo",
                    "--source-docker-docs",
                    "https://example.invalid/demo/docker",
                    "--source-compose-file",
                    "https://example.invalid/demo/compose.yml",
                ],
                check=True,
                cwd=ROOT,
            )
            source_app = source_root / "demo"
            extra_notice = source_app / "EXTRA-NOTICE"
            extra_notice.write_text("additional attribution\n", encoding="utf-8")
            evidence_path = source_app / "source-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["redistributionEvidence"]["materials"].append({
                "path": "EXTRA-NOTICE",
                "sha256": hashlib.sha256(extra_notice.read_bytes()).hexdigest(),
                "purpose": "additional attribution",
            })
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            out_dir = tmp_path / "out"
            proc = subprocess.run(
                [
                    "bash",
                    str(MIGRATE),
                    "--src",
                    str(source_app),
                    "--out",
                    str(out_dir),
                    "--version",
                    "1.0",
                    "--target-version",
                    "2.0",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            migrated = out_dir / "demo"
            self.assertEqual(
                (migrated / "EXTRA-NOTICE").read_text(encoding="utf-8"),
                "additional attribution\n",
            )
            validation = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "source_evidence.py"),
                    str(migrated / "source-evidence.json"),
                    "--artifact-root",
                    str(migrated),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

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
            custom_logo = tmp_path / "logo.png"
            custom_logo.write_bytes(b"verified-custom-logo")
            custom_logo_hash = hashlib.sha256(custom_logo.read_bytes()).hexdigest()
            optional_evidence = {
                "sourceRevision": {"tag": "v1.2.3", "commit": "a" * 40},
                "imageEvidence": {
                    "digest": "sha256:" + "b" * 64,
                    "platforms": ["linux/amd64"],
                },
                "images": [{
                    "version": "latest",
                    "service": "demo",
                    "reference": "ghcr.io/example/demo@sha256:" + "b" * 64,
                    "digest": "sha256:" + "b" * 64,
                    "platforms": ["linux/amd64"],
                }],
                "licenseEvidence": {
                    "spdx": "MIT",
                    "url": "https://example.com/LICENSE",
                },
                "logoEvidence": {
                    "source": "https://example.com/logo.png",
                    "license": "MIT",
                    "sha256": custom_logo_hash,
                },
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": [],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": custom_logo_hash,
                        "requiredFiles": [],
                    }],
                },
            }
            spec_path.write_text(
                json.dumps(
                    {
                        "appKey": "demo",
                        "title": "Demo",
                        "version": "latest",
                        "image": "ghcr.io/example/demo:latest",
                        "logoPath": str(custom_logo),
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
