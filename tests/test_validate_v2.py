#!/usr/bin/env python3
import pathlib
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
            "PANEL_DB_TYPE=mysql\nPANEL_DB_HOST=mysql\nPANEL_APP_PORT_HTTP=8080\nCONTAINER_NAME=\n",
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
