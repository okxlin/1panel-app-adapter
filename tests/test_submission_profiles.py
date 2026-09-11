#!/usr/bin/env python3
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

from package_contract import ensure_evidence_parent, find_evidence, noop_lifecycle_findings, profile_data, readme_version_findings, sample_path


class SubmissionProfileTests(unittest.TestCase):
    def _generate(self, root, profile=None, volumes=True):
        spec = root / "appspec.json"
        spec.write_text(json.dumps({
            "appKey": "demo", "title": "Demo", "version": "1.2.3", "port": 8080,
            "targetPort": 80, "image": "nginx:alpine", "volumes": ["./data:/data"] if volumes else [],
            "description": "Manage tasks", "shortDescZh": "管理任务",
            "repository": "https://example.com/repo", "dockerDocs": "https://example.com/docs",
            "composeFile": "https://example.com/compose",
            "readme": {"featuresZh": ["管理任务"], "featuresEn": ["Manage tasks"],
                       "usageZh": "使用安装时选择的端口访问。", "usageEn": "Use the port selected during installation."},
        }), encoding="utf-8")
        command = ["python3", str(ROOT / "scripts/generate-from-appspec.py"), "--spec", str(spec),
                   "--out-dir", str(root / "out"), "--validate", "--require-validate"]
        if profile:
            command += ["--submission-profile", profile]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return root / "out/demo"

    def test_default_package_keeps_evidence_outside_and_notice_in_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._generate(pathlib.Path(tmp))
            evidence = app.parent / ".evidence/demo/source-evidence.json"
            self.assertTrue(evidence.is_file())
            self.assertFalse((app / "source-evidence.json").exists())
            self.assertFalse((app / "ASSET-LICENSES").exists())
            self.assertFalse((app / "assets/default-logo.svg").exists())
            self.assertTrue((app / "1.2.3/.env.sample").is_file())
            readme = (app / "README.md").read_text(encoding="utf-8")
            english = (app / "README_en.md").read_text(encoding="utf-8")
            self.assertIn("Permission is hereby granted", readme)
            for text in (readme, english):
                self.assertNotIn("1.2.3", text)
                self.assertNotIn("source-evidence.json", text)
            self.assertNotIn("## Introduction", readme)
            self.assertIn("## Introduction", english)
            self.assertEqual(json.loads(evidence.read_text())["submissionProfile"], "third-party")
            fields = yaml.safe_load((app / "1.2.3/data.yml").read_text())["additionalProperties"]["formFields"]
            directory = next(item for item in fields if item["envKey"] == "APP_DATA_DIR")
            self.assertFalse(directory.get("disabled", False))
            result = subprocess.run(["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app), "--source-evidence-mode", "required"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_official_profile_keeps_the_same_compose_and_locks_directory_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._generate(pathlib.Path(tmp), "official")
            version = app / "1.2.3"
            self.assertFalse((version / ".env.sample").exists())
            self.assertTrue((app.parent / ".evidence/demo/1.2.3/.env.sample").is_file())
            fields = yaml.safe_load((version / "data.yml").read_text())["additionalProperties"]["formFields"]
            directory = next(item for item in fields if item["envKey"] == "APP_DATA_DIR")
            self.assertTrue(directory["disabled"])
            self.assertFalse(directory["edit"])
            self.assertEqual(directory["default"], "./data")
            self.assertIn("${APP_DATA_DIR}:/data", (version / "docker-compose.yml").read_text())
            result = subprocess.run(["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app), "--submission-profile", "official", "--source-evidence-mode", "required"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if shutil.which("docker"):
                self.assertIn("docker compose config ok", result.stdout)
            self.assertFalse((version / ".env.sample").exists())

    def test_official_validator_derives_literal_defaults_without_package_writes(self):
        import test_validate_v2
        with tempfile.TemporaryDirectory() as tmp:
            app = test_validate_v2.ValidateV2Tests()._write_sample_app(pathlib.Path(tmp))
            version = app / "latest"
            path = version / "data.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data["additionalProperties"]["formFields"].append({
                "envKey": "GREETING", "type": "text", "required": False,
                "default": "Daily #1's \"news\" $HOME\\tail\nSecond line",
                "labelEn": "Greeting", "labelZh": "问候语",
            })
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            compose_file = version / "docker-compose.yml"
            compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
            compose["services"]["sample"]["environment"].append("GREETING=${GREETING}")
            compose_file.write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")
            (version / ".env.sample").unlink()
            before = {str(path.relative_to(app)): path.read_bytes() for path in app.rglob("*") if path.is_file()}
            result = subprocess.run(["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app),
                                     "--submission-profile", "official"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({str(path.relative_to(app)): path.read_bytes() for path in app.rglob("*") if path.is_file()}, before)

    def test_official_validator_supplies_random_fields_but_not_missing_user_inputs(self):
        import os
        import test_validate_v2
        if shutil.which("docker") is None:
            self.skipTest("Docker Compose CLI is unavailable")
        for random_field in (True, False):
            with self.subTest(random=random_field), tempfile.TemporaryDirectory() as tmp:
                app = test_validate_v2.ValidateV2Tests()._write_sample_app(pathlib.Path(tmp))
                version = app / "latest"
                data_path = version / "data.yml"
                data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
                data["additionalProperties"]["formFields"].append({
                    "envKey": "ADAPTER_REQUIRED_TOKEN", "type": "password", "required": True,
                    "default": "", "random": random_field, "edit": False,
                    "labelEn": "Access token", "labelZh": "访问令牌",
                })
                data_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
                compose_path = version / "docker-compose.yml"
                compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
                compose["services"]["sample"]["environment"].append(
                    "ACCESS_TOKEN=${ADAPTER_REQUIRED_TOKEN:?An access token is required}"
                )
                compose_path.write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")
                (version / ".env.sample").unlink()
                before = {str(path.relative_to(app)): path.read_bytes() for path in app.rglob("*") if path.is_file()}
                environment = os.environ.copy()
                environment.pop("ADAPTER_REQUIRED_TOKEN", None)
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app),
                     "--submission-profile", "official"], text=True, capture_output=True, env=environment,
                )
                if random_field:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("docker compose config ok", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("An access token is required", result.stdout)
                self.assertEqual({str(path.relative_to(app)): path.read_bytes() for path in app.rglob("*") if path.is_file()}, before)

    def test_profile_does_not_change_other_fields(self):
        data = {"additionalProperties": {"formFields": [{"envKey": "API_KEY", "default": "", "edit": False}, {"envKey": "APP_DATA_DIR", "default": "./data", "edit": True}]}}
        transformed = profile_data(data, "official")
        self.assertNotIn("disabled", data["additionalProperties"]["formFields"][1])
        self.assertEqual(transformed["additionalProperties"]["formFields"][0], data["additionalProperties"]["formFields"][0])
        with self.assertRaises(ValueError):
            profile_data(data, "unknown")

    def test_only_needed_lifecycle_hooks_are_generated(self):
        for volumes in (False, True):
            with self.subTest(volumes=volumes), tempfile.TemporaryDirectory() as tmp:
                app = self._generate(pathlib.Path(tmp), volumes=volumes)
                scripts = app / "1.2.3/scripts"
                self.assertEqual(sorted(path.name for path in scripts.glob("*.sh")), ["init.sh"] if volumes else [])
                if volumes:
                    script = scripts / "init.sh"
                    self.assertNotIn("verify_trusted_root_chain", script.read_text())
                    (app / "1.2.3/.env").write_text("APP_DATA_DIR=./custom\n")
                    result = subprocess.run(["bash", str(script)], cwd=tmp, text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue((app / "1.2.3/custom").is_dir())

    def test_readme_version_lint_allows_meaningful_upgrade_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = pathlib.Path(tmp)
            readme = app / "README.md"
            readme.write_text("- 当前版本：1.2.3\n", encoding="utf-8")
            self.assertEqual(len(readme_version_findings(app)), 1)
            readme.write_text("Upgrades from 1.2.3 require a database backup.\n", encoding="utf-8")
            self.assertEqual(readme_version_findings(app), [])
            (app / "README_en.md").write_text("**Version**: `v1.2.3`\n", encoding="utf-8")
            self.assertEqual(len(readme_version_findings(app)), 1)

    def test_noop_hook_lint_is_conservative_and_does_not_execute_scripts(self):
        cases = [
            ("", True),
            ("#!/bin/sh\n# No migration needed\n", True),
            ("#!/bin/bash\nset -eu; set -o pipefail; :; true; exit 0 # Done\n", True),
            ("#!/bin/sh\necho 'Upgrade complete'\nexit 0\n", True),
            ("#!/bin/sh\necho ready > state.txt\n", False),
            ("#!/bin/sh\necho header#data > state.txt\n", False),
            ("#!/bin/sh\necho $(touch state.txt)\n", False),
            ("#!/bin/sh\necho ready && touch state.txt\n", False),
            ("#!/bin/sh\n: > state.txt\n", False),
            ("#!/bin/sh\nset -- changed\n", False),
            ("#!/bin/sh\ntrue $(touch state.txt)\n", False),
            ("#!/bin/sh\nprintf '%s\\n' updated > state.txt\n", False),
            ("#!/bin/sh\nexit 1\n", False),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            version = pathlib.Path(tmp)
            scripts = version / "scripts"
            scripts.mkdir()
            hook = scripts / "init.sh"
            for content, is_noop in cases:
                with self.subTest(content=content):
                    hook.write_text(content, encoding="utf-8")
                    self.assertEqual(bool(noop_lifecycle_findings(version)), is_noop)
                    self.assertFalse((version / "state.txt").exists())
            hook.unlink()
            hook.symlink_to(version / "missing.sh")
            self.assertEqual(noop_lifecycle_findings(version), [])

    def test_sidecar_symlinks_and_conflicting_legacy_evidence_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            app = root / "out/demo"
            app.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (app.parent / ".evidence").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                ensure_evidence_parent(app)
            with self.assertRaisesRegex(ValueError, "symlink"):
                find_evidence(app)
            self.assertEqual(list(outside.iterdir()), [])
            (app.parent / ".evidence").unlink()
            path = ensure_evidence_parent(app)
            path.write_text('{"new": true}')
            (app / "source-evidence.json").write_text('{"old": true}')
            with self.assertRaisesRegex(ValueError, "conflicting"):
                find_evidence(app)

    def test_sample_path_rejects_unsafe_version_and_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            app = root / "out/demo"
            app.mkdir(parents=True)
            for profile in ("official", "third-party"):
                for version in ("../other", "/tmp/other", ".", "..", "a/b", "a\\b", ""):
                    with self.subTest(profile=profile, version=version):
                        with self.assertRaisesRegex(ValueError, "version"):
                            sample_path(app, version, profile)
                parent = app.parent / ".evidence/demo/1.2.3" if profile == "official" else app / "1.2.3"
                parent.parent.mkdir(parents=True, exist_ok=True)
                outside = root / profile
                outside.mkdir()
                parent.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    sample_path(app, "1.2.3", profile)
                self.assertEqual(list(outside.iterdir()), [])

    def test_profile_cli_checks_paths_before_changing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            app = root / "out/demo"
            version = app / "1.2.3"
            version.mkdir(parents=True)
            metadata = version / "data.yml"
            original = "additionalProperties:\n  formFields:\n    - envKey: APP_DATA_DIR\n      default: ./data\n"
            metadata.write_text(original, encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            (app.parent / ".evidence").symlink_to(outside, target_is_directory=True)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/package_contract.py"), str(app),
                                     "--version", "1.2.3", "--submission-profile", "official"], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr)
            self.assertEqual(metadata.read_text(encoding="utf-8"), original)
            self.assertEqual(list(outside.iterdir()), [])

    def test_profile_switch_and_repeated_generation_leave_existing_output_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            app = self._generate(root)
            before = {str(path.relative_to(app.parent)): path.read_bytes()
                      for path in app.parent.rglob("*") if path.is_file()}
            for profile in ("official", "third-party"):
                result = subprocess.run([sys.executable, str(ROOT / "scripts/generate-from-appspec.py"),
                                         "--spec", str(root / "appspec.json"), "--out-dir", str(app.parent),
                                         "--submission-profile", profile], text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("profile" if profile == "official" else "already exists", result.stderr.lower())
                after = {str(path.relative_to(app.parent)): path.read_bytes()
                         for path in app.parent.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

    def test_other_entrypoints_reject_profile_switch_before_writes(self):
        from baota_import_lib import ImportRunner
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            app = self._generate(root)
            before = {str(path.relative_to(app.parent)): path.read_bytes()
                      for path in app.parent.rglob("*") if path.is_file()}
            commands = [
                ["bash", str(ROOT / "scripts/scaffold-v2.sh"), "--app-key", "demo", "--title", "Demo",
                 "--image", "nginx:alpine", "--version", "1.2.3", "--out-dir", str(app.parent),
                 "--force", "--submission-profile", "official", "--source-repository", "https://example.com/repo",
                 "--source-docker-docs", "https://example.com/docs", "--source-compose-file", "https://example.com/compose"],
                ["bash", str(ROOT / "scripts/migrate-v1-to-v2.sh"), "--src", str(app), "--out", str(app.parent),
                 "--version", "1.2.3", "--target-version", "1.2.4", "--submission-profile", "official"],
            ]
            for command in commands:
                result = subprocess.run(command, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("profile", result.stderr.lower())
            with self.assertRaisesRegex(ValueError, "profile"):
                ImportRunner("official")._write_output({"appKey": "demo"}, {}, str(root), str(app.parent), "1.2.4")
            after = {str(path.relative_to(app.parent)): path.read_bytes()
                     for path in app.parent.rglob("*") if path.is_file()}
            self.assertEqual(after, before)
            self.assertFalse((app / "1.2.4").exists())

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is unavailable")
    def test_named_and_file_mounts_keep_their_compose_mechanism(self):
        import importlib.util
        module_spec = importlib.util.spec_from_file_location("appspec_generator", ROOT / "scripts/generate-from-appspec.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        for profile in ("third-party", "official"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as tmp:
                spec = {"appKey": "demo", "version": "1.2.3", "image": "nginx:alpine",
                        "volumes": ["task-data:/data:ro", "/cache"]}
                generator = module.AppSpecGenerator(spec, tmp, submission_profile=profile)
                app = pathlib.Path(generator.generate())
                compose = yaml.safe_load((app / "1.2.3/docker-compose.yml").read_text())
                self.assertEqual(compose["services"]["demo"]["volumes"], ["task-data:/data:ro", "/cache"])
                self.assertEqual(compose["volumes"], {"task-data": {}})
                self.assertFalse((app / "1.2.3/scripts/init.sh").exists())
                self.assertEqual(generator._build_form_fields(), [])
                rendered = subprocess.run(["docker", "compose", "-f", str(app / "1.2.3/docker-compose.yml"),
                                           "--env-file", str(sample_path(app, "1.2.3", profile)), "config"],
                                          text=True, capture_output=True)
                self.assertEqual(rendered.returncode, 0, rendered.stderr)
                spec["version"] = "1.2.4"
                spec["_volumes"] = [{"name": "config", "type": "file", "source": "./config.yml",
                                     "target": "/etc/demo/config.yml", "mode": "ro"}]
                generator = module.AppSpecGenerator(spec, tmp, submission_profile=profile)
                app = pathlib.Path(generator.generate())
                compose = yaml.safe_load((app / "1.2.4/docker-compose.yml").read_text())
                self.assertEqual(compose["services"]["demo"]["volumes"], ["./config.yml:/etc/demo/config.yml:ro"])
                self.assertNotIn("volumes", compose)
                self.assertFalse((app / "1.2.4/scripts/init.sh").exists())

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is unavailable")
    def test_home_and_variable_path_sources_remain_bind_mounts(self):
        import importlib.util
        module_spec = importlib.util.spec_from_file_location("appspec_generator", ROOT / "scripts/generate-from-appspec.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        for profile in ("third-party", "official"):
            for source in ("~/data", "$DATA_DIR"):
                with self.subTest(profile=profile, source=source), tempfile.TemporaryDirectory() as tmp:
                    generator = module.AppSpecGenerator({
                        "appKey": "demo", "version": "1.0", "image": "nginx:alpine", "volumes": [f"{source}:/data"],
                    }, tmp, submission_profile=profile)
                    app = pathlib.Path(generator.generate())
                    compose = app / "1.0/docker-compose.yml"
                    self.assertNotIn("volumes", yaml.safe_load(compose.read_text(encoding="utf-8")))
                    rendered = subprocess.run(["docker", "compose", "-f", str(compose), "--env-file",
                                               str(sample_path(app, "1.0", profile)), "config", "--format", "json"],
                                              text=True, capture_output=True)
                    self.assertEqual(rendered.returncode, 0, rendered.stderr)
                    self.assertEqual(json.loads(rendered.stdout)["services"]["demo"]["volumes"][0]["type"], "bind")


if __name__ == "__main__":
    unittest.main()
