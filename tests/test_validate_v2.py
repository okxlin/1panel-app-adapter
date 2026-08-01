#!/usr/bin/env python3
import pathlib
import hashlib
import json
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "scripts" / "validate-v2.sh"
PATCH_COMPOSE = REPO_ROOT / "scripts" / "patch_compose_yml.py"


class ValidateV2Tests(unittest.TestCase):
    def _write_sample_app(self, root: pathlib.Path) -> pathlib.Path:
        app = root / "apps" / "sample"
        version = app / "latest"
        version.mkdir(parents=True)
        (app / "data.yml").write_text(
            textwrap.dedent(
                """\
                name: sample
                tags:
                - Tool
                title: Sample
                description: Sample
                additionalProperties:
                  key: sample
                  name: sample
                  tags:
                  - Tool
                  type: tool
                  website: https://example.com/sample
                  document: https://example.com/sample/docs
                  github: https://example.com/sample/repo
                  shortDescZh: Sample
                  shortDescEn: Sample
                  crossVersionUpdate: true
                  limit: 0
                  architectures:
                  - amd64
                  description:
                    en: Sample
                    zh: Sample
                    zh-Hant: Sample
                    ja: Sample
                    ko: Sample
                    ru: Sample
                    ms: Sample
                    pt-br: Sample
                """
            ),
            encoding="utf-8",
        )
        (app / "source-evidence.json").write_text(
            textwrap.dedent(
                """\
                {
                  "repository": "https://example.com/sample",
                  "dockerDocs": "https://example.com/sample/docs",
                  "composeFile": "https://example.com/sample/compose"
                }
                """
            ),
            encoding="utf-8",
        )
        (version / "data.yml").write_text(
            textwrap.dedent(
                """\
                additionalProperties:
                  formFields:
                  - default: mysql
                    envKey: PANEL_DB_TYPE
                    labelEn: Database Service
                    labelZh: 数据库服务
                    required: true
                    type: apps
                    child:
                      default: ''
                      envKey: PANEL_DB_HOST
                      required: true
                      type: service
                    values:
                    - label: MySQL
                      value: mysql
                    - label: MariaDB
                      value: mariadb
                    label:
                      en: Database Service
                      zh: 数据库服务
                      zh-Hant: 資料庫服務
                      ja: データベースサービス
                      ko: 데이터베이스 서비스
                      ru: Сервис базы данных
                      ms: Perkhidmatan Pangkalan Data
                      pt-br: Serviço de Banco de Dados
                  - default: 8080
                    edit: true
                    envKey: PANEL_APP_PORT_HTTP
                    labelEn: Port
                    labelZh: 端口
                    required: true
                    rule: paramPort
                    type: number
                """
            ),
            encoding="utf-8",
        )
        (version / ".env.sample").write_text(
            "PANEL_DB_TYPE=mysql\nPANEL_DB_HOST=mysql\nPANEL_APP_PORT_HTTP=8080\nCONTAINER_NAME=sample-compose-check\n",
            encoding="utf-8",
        )
        (version / "docker-compose.yml").write_text(
            textwrap.dedent(
                """\
                services:
                  sample:
                    image: nginx:alpine
                    container_name: ${CONTAINER_NAME}
                    environment:
                      - DB_TYPE=${PANEL_DB_TYPE}
                      - DB_HOST=${PANEL_DB_HOST}
                    ports:
                      - "${PANEL_APP_PORT_HTTP}:80"
                    labels:
                      createdBy: "Apps"
                networks:
                  1panel-network:
                    external: true
                """
            ),
            encoding="utf-8",
        )
        return app

    def test_empty_container_name_sample_fails_before_compose_render(self) -> None:
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
                app = self._write_sample_app(pathlib.Path(tmp))
                sample = app / "latest" / ".env.sample"
                sample.write_text(
                    sample.read_text(encoding="utf-8").replace(
                        "CONTAINER_NAME=sample-compose-check",
                        f"CONTAINER_NAME={empty_value}",
                    ),
                    encoding="utf-8",
                )
                proc = subprocess.run(
                    ["bash", str(VALIDATE), "--dir", str(app)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("CONTAINER_NAME must be non-empty", proc.stdout)

    def test_container_name_must_not_be_an_install_form_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            version_data = app / "latest" / "data.yml"
            version_data.write_text(
                version_data.read_text(encoding="utf-8").replace(
                    "  formFields:\n",
                    "  formFields:\n"
                    "  - default: sample-compose-check\n"
                    "    edit: true\n"
                    "    envKey: CONTAINER_NAME\n"
                    "    labelEn: Container Name\n"
                    "    labelZh: 容器名称\n"
                    "    required: false\n"
                    "    type: text\n",
                    1,
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("CONTAINER_NAME must not be a formFields envKey", proc.stdout)

    def test_values_items_are_not_counted_as_form_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("formFields item missing envKey/type/required", proc.stdout)

    def test_strict_c_allows_missing_healthcheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--strict-c", "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("healthcheck not found", proc.stdout)

    def test_strict_store_rejects_non_executable_lifecycle_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            (app / "README.md").write_text(
                "## 产品介绍\nSample\n\n"
                "## 主要功能\nSample\n\n"
                "## 访问说明\nSample\n\n"
                "## Introduction\nSample\n\n"
                "## Features\nSample\n",
                encoding="utf-8",
            )
            (app / "logo.png").write_bytes(b"not-a-real-logo")
            scripts = app / "latest" / "scripts"
            scripts.mkdir()
            for name in ("init.sh", "upgrade.sh", "uninstall.sh"):
                path = scripts / name
                path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                path.chmod(0o755)
            (scripts / "upgrade.sh").chmod(0o644)

            proc = subprocess.run(
                ["bash", str(VALIDATE), "--strict-store", "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("version upgrade.sh is not executable", proc.stdout)

    def test_strict_store_rejects_symlinked_lifecycle_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            app = self._write_sample_app(tmp_path)
            (app / "README.md").write_text(
                "## 产品介绍\nSample\n\n"
                "## 主要功能\nSample\n\n"
                "## 访问说明\nSample\n\n"
                "## Introduction\nSample\n\n"
                "## Features\nSample\n",
                encoding="utf-8",
            )
            (app / "logo.png").write_bytes(b"not-a-real-logo")
            scripts = app / "latest" / "scripts"
            scripts.mkdir()
            external = tmp_path / "external-upgrade.sh"
            external.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            external.chmod(0o755)
            for name in ("init.sh", "uninstall.sh"):
                path = scripts / name
                path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                path.chmod(0o755)
            (scripts / "upgrade.sh").symlink_to(external)

            proc = subprocess.run(
                ["bash", str(VALIDATE), "--strict-store", "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("version upgrade.sh is a symbolic link", proc.stdout)

    def test_strict_store_rejects_symlinked_lifecycle_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            app = self._write_sample_app(tmp_path)
            (app / "README.md").write_text(
                "## 产品介绍\nSample\n\n"
                "## 主要功能\nSample\n\n"
                "## 访问说明\nSample\n\n"
                "## Introduction\nSample\n\n"
                "## Features\nSample\n",
                encoding="utf-8",
            )
            (app / "logo.png").write_bytes(b"not-a-real-logo")
            external_scripts = tmp_path / "external-scripts"
            external_scripts.mkdir()
            for name in ("init.sh", "upgrade.sh", "uninstall.sh"):
                path = external_scripts / name
                path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                path.chmod(0o755)
            (app / "latest" / "scripts").symlink_to(
                external_scripts, target_is_directory=True
            )

            proc = subprocess.run(
                ["bash", str(VALIDATE), "--strict-store", "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("version scripts directory is a symbolic link", proc.stdout)

    def test_source_evidence_default_allows_package_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            (app / "source-evidence.json").unlink()
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[B][WARN] missing source-evidence.json", proc.stdout)
        self.assertIn("PASS:", proc.stdout)

    def test_source_evidence_required_mode_fails_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            (app / "source-evidence.json").unlink()
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app), "--source-evidence-mode", "required"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[A][FAIL] missing source-evidence.json", proc.stdout)

    def test_source_evidence_accepts_documented_optional_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            evidence_path = app / "source-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence.update(
                {
                    "sourceRevision": {
                        "tag": "v1.2.3",
                        "commit": "0123456789abcdef0123456789abcdef01234567",
                    },
                    "imageEvidence": {
                        "digest": "sha256:" + "a" * 64,
                        "platforms": ["linux/amd64", "linux/arm64"],
                    },
                    "licenseEvidence": {
                        "spdx": "MIT",
                        "url": "https://example.com/sample/LICENSE",
                    },
                    "logoEvidence": {
                        "source": "https://example.com/sample/logo.png",
                        "license": "MIT",
                        "sha256": "b" * 64,
                    },
                }
            )
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app), "--source-evidence-mode", "required"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_source_evidence_rejects_invalid_optional_image_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            evidence_path = app / "source-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["imageEvidence"] = {
                "digest": "sha256:not-a-digest",
                "platforms": ["linux/amd64"],
            }
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app), "--source-evidence-mode", "required"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("imageEvidence.digest", proc.stdout)

    def test_source_evidence_required_mode_verifies_delivered_asset_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            logo = app / "logo.png"
            logo.write_bytes(b"actual-logo")
            notice = app / "ASSET-LICENSES" / "logo.txt"
            notice.parent.mkdir()
            notice.write_text("license notice\n", encoding="utf-8")
            evidence_path = app / "source-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence.update({
                "licenseEvidence": {"spdx": "MIT"},
                    "redistributionEvidence": {
                        "status": "verified",
                        "requiredFiles": ["ASSET-LICENSES/logo.txt"],
                        "materials": [{
                            "path": "ASSET-LICENSES/logo.txt",
                            "sha256": hashlib.sha256(notice.read_bytes()).hexdigest(),
                        }],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": hashlib.sha256(b"different-logo").hexdigest(),
                        "requiredFiles": ["ASSET-LICENSES/logo.txt"],
                    }],
                },
            })
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            proc = subprocess.run(
                [
                    "bash",
                    str(VALIDATE),
                    "--dir",
                    str(app),
                    "--source-evidence-mode",
                    "required",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("sha256 does not match delivered logo.png", proc.stdout)

    def test_source_evidence_required_mode_keeps_legacy_provenance_semantics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            proc = subprocess.run(
                [
                    "bash",
                    str(VALIDATE),
                    "--dir",
                    str(app),
                    "--source-evidence-mode",
                    "required",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_delivery_evidence_mode_requires_license_and_redistribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            proc = subprocess.run(
                [
                    "bash",
                    str(VALIDATE),
                    "--dir",
                    str(app),
                    "--source-evidence-mode",
                    "required",
                    "--require-delivery-evidence",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("missing key: licenseEvidence", proc.stdout)
        self.assertIn("missing key: redistributionEvidence", proc.stdout)

    def test_delivery_evidence_flag_alone_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            proc = subprocess.run(
                [
                    "bash",
                    str(VALIDATE),
                    "--dir",
                    str(app),
                    "--require-delivery-evidence",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("missing key: licenseEvidence", proc.stdout)
        self.assertIn("missing key: redistributionEvidence", proc.stdout)

    def test_delivery_evidence_flag_cannot_be_disabled_by_source_mode_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            proc = subprocess.run(
                [
                    "bash",
                    str(VALIDATE),
                    "--dir",
                    str(app),
                    "--source-evidence-mode",
                    "off",
                    "--require-delivery-evidence",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_version_option_validates_selected_version_in_multi_version_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            historical = app / "1.0.0"
            historical.mkdir()
            (historical / "data.yml").write_text("additionalProperties:\n  formFields: []\n", encoding="utf-8")
            (historical / ".env.sample").write_text("CONTAINER_NAME=\n", encoding="utf-8")
            (historical / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app), "--version", "latest"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("selected version directory: latest", proc.stdout)

    def test_multi_version_app_requires_explicit_version_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            historical = app / "1.0.0"
            historical.mkdir()
            (historical / "data.yml").write_text("additionalProperties:\n  formFields: []\n", encoding="utf-8")
            (historical / ".env.sample").write_text("CONTAINER_NAME=\n", encoding="utf-8")
            (historical / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("multiple version directories found", proc.stdout)

    def test_duplicate_nested_app_root_is_rejected_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            nested = app / app.name
            nested.mkdir()
            for name in ("data.yml", "source-evidence.json", "latest"):
                (app / name).rename(nested / name)
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("duplicate nested app root", proc.stdout)

    def test_lifecycle_path_from_form_cannot_reach_mutating_command_unconfined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            version = app / "latest"
            with (version / "data.yml").open("a", encoding="utf-8") as handle:
                handle.write(
                    "  - default: ./data\n"
                    "    edit: true\n"
                    "    envKey: APP_DATA_DIR\n"
                    "    labelEn: Data directory\n"
                    "    labelZh: 数据目录\n"
                    "    required: true\n"
                    "    type: text\n"
                )
            scripts = version / "scripts"
            scripts.mkdir()
            (scripts / "init.sh").write_text(
                '#!/usr/bin/env bash\nDATA_DIR="${APP_DATA_DIR:-./data}"\nmkdir -p -- "$DATA_DIR"\n',
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("unconfined form path reaches mutating command", proc.stdout)

    def test_random_form_credential_raw_in_connection_url_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            version = app / "latest"
            with (version / "data.yml").open("a", encoding="utf-8") as handle:
                handle.write(
                    "  - default: ''\n"
                    "    edit: true\n"
                    "    envKey: APP_DB_PASSWORD\n"
                    "    labelEn: Database password\n"
                    "    labelZh: 数据库密码\n"
                    "    random: true\n"
                    "    required: true\n"
                    "    type: password\n"
                )
            with (version / ".env.sample").open("a", encoding="utf-8") as handle:
                handle.write("APP_DB_PASSWORD=test-password\n")
            compose_path = version / "docker-compose.yml"
            compose_text = compose_path.read_text(encoding="utf-8")
            compose_path.write_text(
                compose_text.replace(
                    "      - DB_TYPE=${PANEL_DB_TYPE}\n",
                    "      - DB_TYPE=${PANEL_DB_TYPE}\n"
                    "      - DATABASE_URL=postgresql://sample:${APP_DB_PASSWORD}@db/sample\n",
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("random credential is interpolated raw into a connection URL", proc.stdout)

    def test_nested_compose_fallback_must_be_declared_in_form_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            version = app / "latest"
            with (version / "data.yml").open("a", encoding="utf-8") as handle:
                handle.write(
                    "  - default: primary\n"
                    "    edit: true\n"
                    "    envKey: PRIMARY\n"
                    "    labelEn: Primary value\n"
                    "    labelZh: 主值\n"
                    "    required: false\n"
                    "    type: text\n"
                )
            with (version / ".env.sample").open("a", encoding="utf-8") as handle:
                handle.write("PRIMARY=primary\n")
            compose_path = version / "docker-compose.yml"
            compose_text = compose_path.read_text(encoding="utf-8")
            compose_path.write_text(
                compose_text.replace(
                    "      - DB_TYPE=${PANEL_DB_TYPE}\n",
                    "      - DB_TYPE=${PANEL_DB_TYPE}\n"
                    "      - NESTED=${PRIMARY:-${FALLBACK}}\n",
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("compose variable not declared in formFields envKey: FALLBACK", proc.stdout)

    def test_patch_compose_does_not_inject_default_healthcheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            compose = pathlib.Path(tmp) / "docker-compose.yml"
            compose.write_text(
                textwrap.dedent(
                    """\
                    services:
                      sample:
                        image: nginx:alpine
                        ports:
                          - "8080:80"
                    """
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["python3", str(PATCH_COMPOSE), str(compose), "website"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            patched = compose.read_text(encoding="utf-8")

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("container_name: ${CONTAINER_NAME}", patched)
        self.assertIn('createdBy: "Apps"', patched)
        self.assertNotIn("healthcheck:", patched)

    def test_multi_network_generic_internal_service_name_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._write_sample_app(pathlib.Path(tmp))
            compose = app / "latest" / "docker-compose.yml"
            compose.write_text(
                textwrap.dedent(
                    """\
                    services:
                      sample:
                        image: "nginx:alpine"
                        container_name: ${CONTAINER_NAME}
                        environment:
                          - REDIS_HOST=redis
                        ports:
                          - "${PANEL_APP_PORT_HTTP}:80"
                        networks:
                          - 1panel-network
                          - sample-network
                        labels:
                          createdBy: "Apps"
                      redis:
                        image: "redis:7.4"
                        container_name: ${CONTAINER_NAME}-redis
                        networks:
                          - sample-network
                        labels:
                          createdBy: "Apps"
                    networks:
                      1panel-network:
                        external: true
                      sample-network:
                        driver: bridge
                    """
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["bash", str(VALIDATE), "--dir", str(app)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("generic internal service name", proc.stdout)
        self.assertIn("sample->redis", proc.stdout)


if __name__ == "__main__":
    unittest.main()
