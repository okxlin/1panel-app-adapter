#!/usr/bin/env python3
"""
Unit tests for Baota → 1Panel import pipeline.

Tests cover: BaotaPrecheck, BaotaParser, BaotaToAppSpecMapper,
             ComposeTransformer, ImportRunner, and edge cases.
"""

import atexit
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Optional
import yaml

# ── Ensure scripts/ is on path ────────────────────────────────────────
_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from baota_import_lib import (
    BaotaPrecheck,
    BaotaParser,
    BaotaToAppSpecMapper,
    ComposeTransformer,
    ImportRunner,
    E_BAOTA_DISABLED,
    E_BAOTA_APP_KEY_INVALID,
    E_BAOTA_APP_JSON_INVALID,
    E_BAOTA_COMPOSE_INVALID,
    E_BAOTA_COMPOSE_MISSING,
    E_BAOTA_ENV_MISSING,
    E_BAOTA_VERSION_INVALID,
    E_BAOTA_VERSION_DIR_MISSING,
    E_BAOTA_VERSION_MISSING,
    _expand_versions,
    _select_version,
)

_SAMPLE_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="baota_fixtures_"))
_SAMPLE_DIR = _SAMPLE_ROOT / "baota-apps"
atexit.register(lambda: shutil.rmtree(_SAMPLE_ROOT, ignore_errors=True))


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

_ICON_BYTES = b"\x89PNG\r\n\x1a\nfixture"


def _write_text(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: pathlib.Path, data: dict) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=4) + "\n")


def _write_app(
    base_dir: pathlib.Path,
    app_json: dict,
    compose: Optional[str] = "",
    env: str = "APP_PATH=\n",
    version: str = "latest",
) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    _write_json(base_dir / "app.json", app_json)
    (base_dir / "icon.png").write_bytes(_ICON_BYTES)
    _write_text(base_dir / version / ".env", env)
    if compose is not None:
        _write_text(base_dir / version / "docker-compose.yml", compose)


def _base_app_json(
    appname: str,
    apptitle: str,
    appdesc: str,
    *,
    apptype: str = "Tools",
    app_type_cn: str = "工具",
    appstatus: int = 1,
    field: Optional[list] = None,
    env: Optional[list] = None,
    volumes: Optional[dict] = None,
    home: str = "",
    help_url: str = "",
    appversion: Optional[list] = None,
) -> dict:
    return {
        "appid": -1,
        "appname": appname,
        "apptitle": apptitle,
        "apptype": apptype,
        "appTypeCN": app_type_cn,
        "appversion": appversion or [{"m_version": "latest", "s_version": []}],
        "appdesc": appdesc,
        "appstatus": appstatus,
        "home": home,
        "help": help_url,
        "updateat": 1752027587,
        "depend": None,
        "field": field or [],
        "env": env or [],
        "volumes": volumes or {},
    }


def _create_sample_apps() -> None:
    alist_fields = [
        {"attr": "domain", "name": "域名", "type": "textarea", "default": "", "suffix": "浏览器访问的域名,非必填", "unit": ""},
        {"attr": "allow_access", "name": "允许外部访问", "type": "checkbox", "default": True, "suffix": "允许直接通过主机IP+端口访问", "unit": ""},
        {"attr": "alist_web_port", "name": "web管理端口", "type": "number", "default": 15244, "suffix": "alist的web管理端口", "unit": ""},
        {"attr": "s3_server_port", "name": "s3服务端口", "type": "number", "default": 5426, "suffix": "s3服务的端口", "unit": ""},
        {"attr": "cpus", "name": "cpu核心数限制", "type": "number", "default": 0, "suffix": "0为不限制", "unit": ""},
        {"attr": "memory_limit", "name": "内存限制", "type": "number", "default": 0, "suffix": "0为不限制", "unit": ""},
    ]
    alist_env = [
        {"key": "alist_web_port", "type": "port", "default": None, "desc": "web管理端口"},
        {"key": "s3_server_port", "type": "port", "default": None, "desc": "s3服务端口"},
        {"key": "app_path", "type": "path", "default": None, "desc": "应用数据目录"},
        {"key": "host_ip", "type": "string", "default": None, "desc": "主机IP"},
        {"key": "cpus", "type": "number", "default": None, "desc": "CPU核心数限制"},
        {"key": "memory_limit", "type": "number", "default": None, "desc": "内存大小限制"},
    ]
    alist_compose = """services:
  alist:
    image: xhofe/alist:latest
    deploy:
      resources:
        limits:
          cpus: ${CPUS}
          memory: ${MEMORY_LIMIT}
    environment:
      - PUID=0
      - PGID=0
      - UMASK=022
    ports:
      - ${HOST_IP}:${ALIST_WEB_PORT}:5244
      - ${HOST_IP}:${S3_SERVER_PORT}:5426
    restart: always
    volumes:
      - ${APP_PATH}/data:/opt/alist/data
      - ${APP_PATH}/mnt:/mnt/data
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net

networks:
  baota_net:
    external: true
"""
    _write_app(
        _SAMPLE_DIR / "alist",
        _base_app_json(
            "alist",
            "Alist",
            "一个支持多存储的文件列表程序，使用Gin和Solidjs",
            apptype="Storage",
            app_type_cn="存储/网盘",
            field=alist_fields,
            env=alist_env,
            volumes={"data": {"type": "path", "desc": "数据目录"}, "mnt": {"type": "path", "desc": "挂载目录"}},
            help_url="https://alist.nn.ci",
            appversion=[{"m_version": "latest", "s_version": []}, {"m_version": "3", "s_version": ["42.0"]}],
        ),
        alist_compose,
        "ALIST_WEB_PORT=\nS3_SERVER_PORT=\nHOST_IP=\nCPUS=\nMEMORY_LIMIT=\nAPP_PATH=\n",
    )

    _write_app(
        _SAMPLE_DIR / "apphub" / "adguardhome",
        _base_app_json(
            "adguardhome",
            "AdGuard Home",
            "AdGuard Home is a network-wide software for blocking ads and tracking.",
            apptype="Security",
            app_type_cn="安全",
            field=[
                {"attr": "ag_web_port", "name": "Web管理端口", "type": "number", "default": 3000, "suffix": "", "unit": ""},
                {"attr": "ag_dns_port", "name": "DNS端口", "type": "number", "default": 53, "suffix": "", "unit": ""},
            ],
            env=[
                {"key": "ag_web_port", "type": "port", "default": None, "desc": "Web UI端口"},
                {"key": "ag_dns_port", "type": "port", "default": None, "desc": "DNS服务器端口"},
            ],
            volumes={"work": {"type": "path", "desc": "工作目录"}, "conf": {"type": "path", "desc": "配置目录"}},
            help_url="https://github.com/AdguardTeam/AdGuardHome/wiki",
        ),
        """services:
  adguardhome:
    image: adguard/adguardhome:latest
    restart: always
    ports:
      - ${HOST_IP}:${AG_WEB_PORT}:3000
      - ${HOST_IP}:${AG_DNS_PORT}:53/udp
    volumes:
      - ${APP_PATH}/work:/opt/adguardhome/work
      - ${APP_PATH}/conf:/opt/adguardhome/conf
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net

networks:
  baota_net:
    external: true
""",
        "AG_WEB_PORT=\nAG_DNS_PORT=\nHOST_IP=\nAPP_PATH=\n",
    )

    _write_app(
        _SAMPLE_DIR / "apphub" / "redis-dependent-app",
        _base_app_json(
            "redis-dependent-app",
            "Redis App",
            "An application that depends on Redis.",
            field=[{"attr": "web_port", "name": "Web端口", "type": "number", "default": 8080, "suffix": "", "unit": ""}],
            env=[
                {"key": "web_port", "type": "port", "default": None, "desc": "Web UI端口"},
                {"key": "app_path", "type": "path", "default": None, "desc": "应用数据目录"},
            ],
            volumes={"data": {"type": "path", "desc": "数据目录"}},
        ),
        """services:
  app:
    image: example/app:latest
    restart: always
    ports:
      - ${HOST_IP}:${WEB_PORT}:8080
    volumes:
      - ${APP_PATH}/data:/app/data
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net
    depends_on:
      redis:
        condition: service_started

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - ${APP_PATH}/redis-data:/data
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net

networks:
  baota_net:
    external: true
""",
        "WEB_PORT=\nHOST_IP=\nAPP_PATH=\n",
    )

    _write_app(
        _SAMPLE_DIR / "apphub" / "disabled-app",
        _base_app_json("disabled-app", "Disabled App", "This app is disabled in the store.", appstatus=0),
        """services:
  disabled-app:
    image: example/disabled:latest
    restart: unless-stopped
    networks:
      - baota_net
    labels:
      createdBy: "bt_apps"

networks:
  baota_net:
    external: true
""",
    )
    _write_app(
        _SAMPLE_DIR / "apphub" / "file-volume-app",
        _base_app_json(
            "file-volume-app",
            "File Volume App",
            "An app that uses file-type volumes.",
            volumes={"config": {"type": "file", "desc": "配置文件"}, "data": {"type": "path", "desc": "数据目录"}},
        ),
        """services:
  file-app:
    image: example/file-app:latest
    restart: always
    volumes:
      - ${APP_PATH}/config.yml:/app/config.yml
      - ${APP_PATH}/data:/app/data
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net

networks:
  baota_net:
    external: true
""",
    )
    _write_app(
        _SAMPLE_DIR / "apphub" / "broken-field-env-mismatch",
        _base_app_json(
            "broken-field-env-mismatch",
            "Mismatch App",
            "This app has field/env mismatches.",
            field=[{"attr": "webport", "name": "Web Port", "type": "number", "default": 8080, "suffix": "", "unit": ""}],
            env=[{"key": "WEB_PORT", "type": "port", "default": None, "desc": "Web UI port"}],
        ),
        """services:
  mismatch-app:
    image: example/mismatch:latest
    restart: always
    ports:
      - ${HOST_IP}:${WEB_PORT}:8080
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net

networks:
  baota_net:
    external: true
""",
        "WEB_PORT=\nHOST_IP=\n",
    )
    _write_app(
        _SAMPLE_DIR / "apphub" / "broken-missing-compose",
        _base_app_json("broken-missing-compose", "Broken App", "This app is missing its compose file."),
        compose=None,
    )


_create_sample_apps()

def _sample(name: str) -> str:
    """Return path to a sample app directory."""
    # Try main samples first, then apphub
    p = _SAMPLE_DIR / name / "app.json"
    if p.is_file():
        return str(_SAMPLE_DIR / name)
    p2 = _SAMPLE_DIR / "apphub" / name / "app.json"
    if p2.is_file():
        return str(_SAMPLE_DIR / "apphub" / name)
    raise FileNotFoundError(f"Sample '{name}' not found")


# ═══════════════════════════════════════════════════════════════════════
#  Version Helpers
# ═══════════════════════════════════════════════════════════════════════

class TestVersionExpansion(unittest.TestCase):
    def test_latest_only(self):
        versions = _expand_versions([{"m_version": "latest", "s_version": []}])
        self.assertEqual(versions, ["latest"])

    def test_major_minor(self):
        versions = _expand_versions([{"m_version": "3", "s_version": ["42.0", "41.0"]}])
        self.assertEqual(versions, ["3.42.0", "3.41.0"])

    def test_mixed(self):
        versions = _expand_versions([
            {"m_version": "latest", "s_version": []},
            {"m_version": "3", "s_version": ["42.0"]},
        ])
        self.assertEqual(versions, ["latest", "3.42.0"])

    def test_select_latest(self):
        self.assertEqual(_select_version(["latest", "3.42.0"], None), "latest")

    def test_select_requested(self):
        self.assertEqual(_select_version(["latest", "3.42.0"], "3.42.0"), "3.42.0")

    def test_select_missing_raises(self):
        with self.assertRaises(ValueError):
            _select_version(["latest"], "2.0.0")

    def test_select_empty_raises(self):
        with self.assertRaises(ValueError):
            _select_version([], None)


# ═══════════════════════════════════════════════════════════════════════
#  BaotaPrecheck
# ═══════════════════════════════════════════════════════════════════════

class TestBaotaPrecheck(unittest.TestCase):
    def setUp(self):
        self.precheck = BaotaPrecheck()

    def test_valid_app_passes(self):
        report = self.precheck.validate(_sample("alist"))
        self.assertEqual(report["errors"], [])
        self.assertIn("latest", report["fields"]["versions"])

    def test_disabled_app_blocked(self):
        report = self.precheck.validate(_sample("disabled-app"))
        self.assertTrue(report["disabledSourceApp"])
        codes = [e["code"] for e in report["errors"]]
        self.assertIn(E_BAOTA_DISABLED, codes)

    def test_disabled_app_allowed(self):
        report = self.precheck.validate(_sample("disabled-app"), include_disabled=True)
        # With include_disabled, no E_BAOTA_DISABLED error
        codes = [e["code"] for e in report["errors"]]
        self.assertNotIn(E_BAOTA_DISABLED, codes)

    def test_missing_compose_detected(self):
        report = self.precheck.validate(_sample("broken-missing-compose"))
        codes = [e["code"] for e in report["errors"]]
        self.assertIn(E_BAOTA_COMPOSE_MISSING, codes)

    def test_invalid_app_key_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="baota_invalid_key_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "source"
            _write_app(
                app_dir,
                _base_app_json("../escaped", "Escaped", "Invalid app key."),
                "services:\n  app:\n    image: busybox:latest\n",
            )

            report = self.precheck.validate(str(app_dir))

        codes = [error["code"] for error in report["errors"]]
        self.assertIn(E_BAOTA_APP_KEY_INVALID, codes)

    def test_invalid_version_name_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="baota_invalid_version_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "source"
            _write_app(
                app_dir,
                _base_app_json(
                    "safe-app",
                    "Safe App",
                    "Invalid version name.",
                    appversion=[{"m_version": "../outside", "s_version": []}],
                ),
                "services:\n  app:\n    image: busybox:latest\n",
            )

            report = self.precheck.validate(str(app_dir))

        codes = [error["code"] for error in report["errors"]]
        self.assertIn(E_BAOTA_VERSION_INVALID, codes)

    def test_malformed_compose_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="baota_invalid_compose_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "source"
            _write_app(
                app_dir,
                _base_app_json("broken-yaml", "Broken YAML", "Malformed compose."),
                "services: [\n",
            )

            report = self.precheck.validate(str(app_dir))

        codes = [error["code"] for error in report["errors"]]
        self.assertIn(E_BAOTA_COMPOSE_INVALID, codes)

    def test_required_file_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="baota_symlink_file_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "source"
            _write_app(
                app_dir,
                _base_app_json("linked-icon", "Linked Icon", "Symlink input."),
                "services:\n  app:\n    image: busybox:latest\n",
            )
            outside_icon = pathlib.Path(tmpdir) / "outside.png"
            outside_icon.write_bytes(_ICON_BYTES)
            (app_dir / "icon.png").unlink()
            os.symlink(outside_icon, app_dir / "icon.png")

            report = self.precheck.validate(str(app_dir))

        codes = [error["code"] for error in report["errors"]]
        self.assertIn("E_BAOTA_ICON_MISSING", codes)

    def test_version_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="baota_symlink_version_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "source"
            outside_version = pathlib.Path(tmpdir) / "outside-version"
            _write_app(
                app_dir,
                _base_app_json("linked-version", "Linked Version", "Symlink input."),
                None,
            )
            shutil.rmtree(app_dir / "latest")
            _write_text(
                outside_version / "docker-compose.yml",
                "services:\n  app:\n    image: busybox:latest\n",
            )
            os.symlink(outside_version, app_dir / "latest")

            report = self.precheck.validate(str(app_dir))

        codes = [error["code"] for error in report["errors"]]
        self.assertIn(E_BAOTA_VERSION_INVALID, codes)

    def test_env_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="baota_symlink_env_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "source"
            _write_app(
                app_dir,
                _base_app_json("linked-env", "Linked Env", "Symlink input."),
                "services:\n  app:\n    image: busybox:latest\n",
            )
            outside_env = pathlib.Path(tmpdir) / "outside.env"
            outside_env.write_text("SECRET=not-for-import\n", encoding="utf-8")
            (app_dir / "latest" / ".env").unlink()
            os.symlink(outside_env, app_dir / "latest" / ".env")

            report = self.precheck.validate(str(app_dir))

        codes = [error["code"] for error in report["errors"]]
        self.assertIn(E_BAOTA_ENV_MISSING, codes)

    def test_standard_fields_detected(self):
        parser = BaotaParser()
        app_json = parser.parse_app_json(_sample("alist"))
        std_fields = BaotaPrecheck.validate_standard_fields(app_json.get("field", []))
        self.assertIn("domain", std_fields)
        self.assertIn("allow_access", std_fields)
        self.assertIn("cpus", std_fields)
        self.assertIn("memory_limit", std_fields)

    def test_standard_env_detected(self):
        parser = BaotaParser()
        app_json = parser.parse_app_json(_sample("alist"))
        std_env = BaotaPrecheck.validate_standard_env(app_json.get("env", []))
        self.assertIn("app_path", std_env)
        self.assertIn("host_ip", std_env)
        self.assertIn("cpus", std_env)
        self.assertIn("memory_limit", std_env)

    def test_field_env_mismatch_detected(self):
        parser = BaotaParser()
        app_json = parser.parse_app_json(_sample("broken-field-env-mismatch"))
        mismatches = BaotaPrecheck.validate_field_env_relationship(
            app_json.get("field", []), app_json.get("env", [])
        )
        self.assertTrue(len(mismatches) > 0)
        self.assertIn("webport", mismatches[0]["field_attr"])


# ═══════════════════════════════════════════════════════════════════════
#  BaotaParser
# ═══════════════════════════════════════════════════════════════════════

class TestBaotaParser(unittest.TestCase):
    def setUp(self):
        self.parser = BaotaParser()

    def test_parse_app_json(self):
        app_json = self.parser.parse_app_json(_sample("alist"))
        self.assertEqual(app_json["appname"], "alist")
        self.assertEqual(app_json["apptype"], "Storage")
        self.assertIsInstance(app_json["updateat"], int)
        self.assertIsNone(app_json["depend"])

    def test_list_versions(self):
        versions = self.parser.list_versions(_sample("alist"))
        self.assertIn("latest", versions)
        self.assertIn("3.42.0", versions)

    def test_parse_env_file(self):
        env_path = str(pathlib.Path(_sample("alist")) / "latest" / ".env")
        env = self.parser.parse_env_file(env_path)
        self.assertIn("ALIST_WEB_PORT", env)
        self.assertIn("APP_PATH", env)

    def test_load_compose(self):
        compose_path = str(pathlib.Path(_sample("alist")) / "latest" / "docker-compose.yml")
        compose = self.parser.load_compose(compose_path)
        self.assertIn("services", compose)
        self.assertIn("alist", compose["services"])
        self.assertEqual(compose["services"]["alist"]["image"], "xhofe/alist:latest")

    def test_volumes_is_object(self):
        app_json = self.parser.parse_app_json(_sample("alist"))
        volumes = app_json.get("volumes", {})
        self.assertIsInstance(volumes, dict)
        self.assertIn("data", volumes)
        self.assertEqual(volumes["data"]["type"], "path")

    def test_env_has_type_field(self):
        app_json = self.parser.parse_app_json(_sample("alist"))
        env_list = app_json.get("env", [])
        for e in env_list:
            self.assertIn("type", e)
        port_envs = [e for e in env_list if e.get("type") == "port"]
        self.assertTrue(len(port_envs) >= 2)

    def test_field_default_is_native_type(self):
        app_json = self.parser.parse_app_json(_sample("alist"))
        fields = app_json.get("field", [])
        allow_access = [f for f in fields if f["attr"] == "allow_access"]
        self.assertTrue(len(allow_access) > 0)
        self.assertIsInstance(allow_access[0]["default"], bool)

        web_port = [f for f in fields if f["attr"] == "alist_web_port"]
        self.assertTrue(len(web_port) > 0)
        self.assertIsInstance(web_port[0]["default"], int)


# ═══════════════════════════════════════════════════════════════════════
#  ComposeTransformer
# ═══════════════════════════════════════════════════════════════════════

class TestComposeTransformer(unittest.TestCase):
    def setUp(self):
        self.transformer = ComposeTransformer()

    def _get_service(self, compose, name="alist"):
        return compose.get("services", {}).get(name, {})

    def test_transform_alist(self):
        compose = self.transformer.transform(_sample("alist"), "latest")
        svc = self._get_service(compose)

        # Container name injected
        self.assertEqual(svc.get("container_name"), "${CONTAINER_NAME}")

        # Ports transformed
        ports = svc.get("ports", [])
        self.assertIn("${PANEL_APP_PORT_HTTP}:5244", ports)
        self.assertIn("${PANEL_APP_PORT_5426}:5426", ports)

        # Volumes transformed
        volumes = svc.get("volumes", [])
        self.assertIn("${APP_DATA_DIR_DATA}:/opt/alist/data", volumes)
        self.assertIn("${APP_DATA_DIR_MNT}:/mnt/data", volumes)

        # Network replaced
        self.assertIn("1panel-network", svc.get("networks", []))

        # Label replaced
        self.assertEqual(svc.get("labels", {}).get("createdBy"), "Apps")

        # Deploy removed
        self.assertNotIn("deploy", svc)

        # External network defined
        networks = compose.get("networks", {})
        self.assertIn("1panel-network", networks)
        self.assertTrue(networks["1panel-network"].get("external"))

    def test_transform_adguardhome(self):
        compose = self.transformer.transform(_sample("adguardhome"), "latest")
        svc = self._get_service(compose, "adguardhome")
        ports = svc.get("ports", [])
        # Should have two ports
        port_strs = [str(p) for p in ports]
        self.assertTrue(any("PANEL_APP_PORT_HTTP" in p for p in port_strs))
        self.assertIn("${PANEL_APP_PORT_53}:53/udp", port_strs)

    def test_file_volume_app(self):
        compose = self.transformer.transform(_sample("file-volume-app"), "latest")
        vol_info = compose.get("_transform", {}).get("volumeInfo", [])
        self.assertEqual(len(vol_info), 2)
        self.assertTrue(any(item["containerPath"] == "/app/config.yml" for item in vol_info))

    def test_network_mapping_preserves_aliases(self):
        with tempfile.TemporaryDirectory(prefix="baota_network_mapping_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "network-app"
            _write_app(
                app_dir,
                _base_app_json("network-app", "Network App", "Mapping-style networks."),
                """services:
  app:
    image: busybox:latest
    networks:
      baota_net:
        aliases:
          - app-alias
      private: {}
networks:
  baota_net:
    external: true
  private: {}
""",
            )

            compose = self.transformer.transform(str(app_dir), "latest")

        networks = compose["services"]["app"]["networks"]
        self.assertIsInstance(networks, dict)
        self.assertEqual(networks["1panel-network"]["aliases"], ["app-alias"])
        self.assertIn("private", networks)

    def test_long_syntax_requires_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="baota_long_syntax_") as tmpdir:
            app_dir = pathlib.Path(tmpdir) / "long-syntax"
            _write_app(
                app_dir,
                _base_app_json("long-syntax", "Long Syntax", "Long Compose syntax."),
                """services:
  app:
    image: busybox:latest
    ports:
      - target: 8080
        published: ${WEB_PORT}
    volumes:
      - type: bind
        source: ${APP_PATH}/data
        target: /data
""",
            )

            compose = self.transformer.transform(str(app_dir), "latest")

        transform = compose["_transform"]
        self.assertTrue(transform["manualReviewRequired"])
        self.assertEqual(
            {reason["code"] for reason in transform["manualReviewReasons"]},
            {"compose-long-port-syntax", "compose-long-volume-syntax"},
        )

    def test_unresolved_variables_collected(self):
        compose = self.transformer.transform(_sample("alist"), "latest")
        unresolved = compose.get("_transform", {}).get("unresolved", [])
        # APP_PATH, HOST_IP, CPUS, MEMORY_LIMIT should not remain
        for bad_var in ("APP_PATH", "HOST_IP", "CPUS", "MEMORY_LIMIT"):
            self.assertNotIn(bad_var, unresolved)


# ═══════════════════════════════════════════════════════════════════════
#  BaotaToAppSpecMapper
# ═══════════════════════════════════════════════════════════════════════

class TestBaotaToAppSpecMapper(unittest.TestCase):
    def setUp(self):
        self.mapper = BaotaToAppSpecMapper()
        self.transformer = ComposeTransformer()

    def test_build_appspec_alist(self):
        parser = BaotaParser()
        app_json = parser.parse_app_json(_sample("alist"))
        compose = self.transformer.transform(_sample("alist"), "latest")
        appspec = self.mapper.build_appspec(app_json, "latest", compose, _sample("alist"))

        self.assertEqual(appspec["appKey"], "alist")
        self.assertEqual(appspec["type"], "Storage")
        self.assertIn("importSource", appspec)
        self.assertEqual(appspec["importSource"]["type"], "baota")
        self.assertIn("formFields", appspec)
        self.assertIn("composeOverride", appspec)
        self.assertTrue(appspec["composeOverride"]["enabled"])

        # Migration notes should skip platform fields
        notes = appspec.get("migrationNotes", [])
        self.assertTrue(any("domain" in n for n in notes))
        self.assertTrue(any("cpus" in n for n in notes))

        # Non-platform fields should be in formFields
        ff = appspec.get("formFields", [])
        env_keys = {f["envKey"] for f in ff}
        self.assertIn("PANEL_APP_PORT_HTTP", env_keys)
        self.assertIn("PANEL_APP_PORT_5426", env_keys)
        self.assertNotIn("ALIST_WEB_PORT", env_keys)
        self.assertNotIn("S3_SERVER_PORT", env_keys)
        # Platform keys should NOT be in formFields
        self.assertNotIn("CPUS", env_keys)
        self.assertNotIn("MEMORY_LIMIT", env_keys)

    def test_evidence_level_third_party(self):
        parser = BaotaParser()
        app_json = parser.parse_app_json(_sample("alist"))
        compose = self.transformer.transform(_sample("alist"), "latest")
        appspec = self.mapper.build_appspec(app_json, "latest", compose)
        # alist has empty home, help=https://alist.nn.ci (not a known pattern)
        self.assertEqual(appspec["evidenceStatus"], "third_party_only")

    def test_declared_github_urls_remain_unverified_hints(self):
        app_json = _base_app_json(
            "source-hints",
            "Source Hints",
            "Unverified source declarations.",
            home="https://github.com/unrelated/project",
            help_url="https://github.com/unrelated/project/wiki",
        )

        appspec = self.mapper.build_appspec(
            app_json,
            "latest",
            {"services": {"app": {"image": "busybox:latest"}}},
        )

        self.assertEqual(appspec["evidenceStatus"], "third_party_only")
        self.assertEqual(
            appspec["importSource"]["declaredHome"],
            "https://github.com/unrelated/project",
        )
        self.assertEqual(
            appspec["importSource"]["declaredHelp"],
            "https://github.com/unrelated/project/wiki",
        )
        self.assertEqual(appspec["architectureEvidence"], "unverified_default")


# ═══════════════════════════════════════════════════════════════════════
#  ImportRunner
# ═══════════════════════════════════════════════════════════════════════

class TestImportRunner(unittest.TestCase):
    def setUp(self):
        self.runner = ImportRunner()
        self.tmpdir = tempfile.mkdtemp(prefix="baota_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_import_rejects_output_path_escape(self):
        source = pathlib.Path(self.tmpdir) / "source"
        out_dir = pathlib.Path(self.tmpdir) / "out"
        _write_app(
            source,
            _base_app_json("../escaped", "Escaped", "Invalid output path."),
            "services:\n  app:\n    image: busybox:latest\n",
        )

        result = self.runner.import_one(str(source), str(out_dir), "latest")

        self.assertFalse(result["success"])
        self.assertEqual(result["errorCode"], E_BAOTA_APP_KEY_INVALID)
        self.assertFalse((pathlib.Path(self.tmpdir) / "escaped" / "data.yml").exists())

    def test_import_rejects_existing_symlink_escape(self):
        out_dir = pathlib.Path(self.tmpdir) / "out"
        outside = pathlib.Path(self.tmpdir) / "outside"
        out_dir.mkdir()
        outside.mkdir()
        (out_dir / "alist").symlink_to(outside, target_is_directory=True)

        result = self.runner.import_one(_sample("alist"), str(out_dir), "latest")

        self.assertFalse(result["success"])
        self.assertEqual(result["errorCode"], "E_BAOTA_OUTPUT_PATH_INVALID")
        self.assertFalse((outside / "data.yml").exists())

    def test_import_rejects_existing_output_file_symlink(self):
        out_dir = pathlib.Path(self.tmpdir) / "file-symlink-output"
        app_dir = out_dir / "alist"
        outside = pathlib.Path(self.tmpdir) / "outside-data.yml"
        app_dir.mkdir(parents=True)
        outside.write_text("sentinel\n", encoding="utf-8")
        os.symlink(outside, app_dir / "data.yml")

        result = self.runner.import_one(_sample("alist"), str(out_dir), "latest")

        self.assertFalse(result["success"])
        self.assertEqual(result["errorCode"], "E_BAOTA_OUTPUT_PATH_INVALID")
        self.assertEqual(outside.read_text(encoding="utf-8"), "sentinel\n")

    def test_import_alist_success(self):
        result = self.runner.import_one(
            _sample("alist"), self.tmpdir, "latest", validate=True, require_validate=True,
        )
        self.assertTrue(result["success"], f"Import failed: {result.get('errors')}")
        self.assertEqual(result["app"], "alist")
        self.assertEqual(result.get("validation", {}).get("valid"), True)
        self.assertEqual(result["stage"], "converted_candidate")
        self.assertEqual(result["candidateStatus"], "manual_review_required")
        self.assertFalse(result["delivery"]["ready"])
        self.assertEqual(
            {blocker["code"] for blocker in result["delivery"]["blockers"]},
            {
                "unverified-source",
                "unverified-architectures",
                "unverified-application-license",
                "unverified-redistribution",
            },
        )

        out = pathlib.Path(result["outputPath"])
        self.assertTrue((out / "data.yml").is_file())
        self.assertTrue((out / "logo.png").is_file())
        self.assertTrue((out / "source-evidence.json").is_file())
        self.assertTrue((out / "latest" / "data.yml").is_file())
        self.assertTrue((out / "latest" / "docker-compose.yml").is_file())
        self.assertTrue((out / "latest" / ".env.sample").is_file())
        self.assertTrue((out / "README.md").is_file())
        readme_text = (out / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("- Version: latest", readme_text)
        self.assertIn("app store version list", readme_text)
        for heading in ("## 产品介绍", "## 主要功能", "## 访问说明", "## Introduction", "## Features"):
            self.assertIn(heading, readme_text)
        self.assertTrue((out / "latest" / "data").is_dir())
        self.assertTrue((out / "latest" / "scripts" / "init.sh").is_file())
        self.assertTrue((out / "latest" / "scripts" / "upgrade.sh").is_file())
        self.assertTrue((out / "latest" / "scripts" / "uninstall.sh").is_file())
        uninstall_text = (out / "latest" / "scripts" / "uninstall.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('cd "$ROOT_DIR"', uninstall_text)
        self.assertIn("docker-compose down\n", uninstall_text)
        self.assertNotIn("--volumes", uninstall_text)

        root_data = yaml.safe_load((out / "data.yml").read_text(encoding="utf-8"))
        desc = root_data.get("additionalProperties", {}).get("description")
        self.assertIsInstance(desc, dict)
        self.assertIn("zh-Hant", desc)

        ver_data = yaml.safe_load((out / "latest" / "data.yml").read_text(encoding="utf-8"))
        fields = ver_data.get("additionalProperties", {}).get("formFields", [])
        self.assertTrue(fields)
        self.assertTrue(all(isinstance(field.get("label"), dict) for field in fields))
        form_keys = {field.get("envKey") for field in fields}
        compose_text = (out / "latest" / "docker-compose.yml").read_text(encoding="utf-8")
        env_sample = (out / "latest" / ".env.sample").read_text(encoding="utf-8")
        compose_vars = set(__import__("re").findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", compose_text))
        self.assertFalse(compose_vars - form_keys - {"CONTAINER_NAME"})
        self.assertIn("${APP_DATA_DIR_DATA}:/opt/alist/data", compose_text)
        self.assertIn("${APP_DATA_DIR_MNT}:/mnt/data", compose_text)
        self.assertIn("PANEL_APP_PORT_HTTP=15244", env_sample)
        self.assertIn("PANEL_APP_PORT_5426=5426", env_sample)
        self.assertIn("APP_DATA_DIR_DATA=./data/data", env_sample)
        self.assertIn("APP_DATA_DIR_MNT=./data/mnt", env_sample)
        evidence = json.loads((out / "source-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["architectureEvidence"], "unverified_default")
        self.assertEqual(root_data["additionalProperties"]["architectures"], ["amd64"])

    def test_strict_store_validation_requires_provenance_and_delivery_evidence(self):
        result = self.runner.import_one(
            _sample("alist"),
            self.tmpdir,
            "latest",
            strict_store_validate=True,
            require_validate=True,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "strict_store_validate")
        self.assertEqual(result["validation"]["mode"], "strict-store")
        self.assertIn("validate-v2.sh", result["validation"]["validator"])
        evidence = json.loads(
            (pathlib.Path(result["outputPath"]) / "source-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["repository"], "")
        self.assertEqual(evidence["composeFile"], "")
        self.assertNotIn("licenseEvidence", evidence)
        self.assertEqual(evidence["redistributionEvidence"]["status"], "unresolved")
        self.assertNotEqual(result["validation"]["returncode"], 0)
        self.assertFalse(result["validation"]["valid"])
        self.assertTrue(result["validation"]["failed"])
        self.assertIn("source-evidence.json missing key: repository", result["validation"]["stdout"])
        self.assertIn("source-evidence.json missing key: licenseEvidence", result["validation"]["stdout"])
        self.assertIn(
            "redistributionEvidence.status must be verified for delivery",
            result["validation"]["stdout"],
        )
        self.assertIn("SUMMARY:", result["validation"]["stdout"])
        self.assertFalse(result["delivery"]["ready"])

    def test_require_validate_without_validation_mode_fails(self):
        result = self.runner.import_one(
            _sample("alist"), self.tmpdir, "latest", require_validate=True,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["errorCode"], "E_1PANEL_VALIDATION_MODE_REQUIRED")
        self.assertFalse((pathlib.Path(self.tmpdir) / "alist").exists())

    def test_import_records_git_compose_source_url(self):
        source_root = pathlib.Path(self.tmpdir) / "source-root"
        app_dir = source_root / "apphub" / "alist"
        shutil.copytree(_sample("alist"), app_dir)
        git_dir = source_root / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (git_dir / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/example/apphub.git\n',
            encoding="utf-8",
        )

        result = self.runner.import_one(str(app_dir), self.tmpdir, "latest")
        self.assertTrue(result["success"], result.get("errors"))
        evidence = json.loads((pathlib.Path(result["outputPath"]) / "source-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["repository"], "https://github.com/example/apphub")
        self.assertEqual(
            evidence["composeFile"],
            "https://github.com/example/apphub/blob/main/apphub/alist/latest/docker-compose.yml",
        )

    def test_repeated_imports_record_all_packaged_versions(self):
        source = pathlib.Path(self.tmpdir) / "source"
        shutil.copytree(_sample("alist"), source)
        shutil.copytree(source / "latest", source / "3.42.0")
        out_dir = pathlib.Path(self.tmpdir) / "versions-out"

        latest = self.runner.import_one(str(source), str(out_dir), "latest")
        fixed = self.runner.import_one(str(source), str(out_dir), "3.42.0")

        self.assertTrue(latest["success"], latest.get("errors"))
        self.assertTrue(fixed["success"], fixed.get("errors"))
        self.assertEqual(fixed["availableVersions"], ["latest", "3.42.0"])
        self.assertEqual(fixed["selectedVersion"], "3.42.0")
        self.assertEqual(fixed["packagedVersions"], ["latest", "3.42.0"])
        evidence = json.loads(
            (out_dir / "alist" / "source-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["importSource"]["versions"], ["latest", "3.42.0"])
        self.assertEqual(set(evidence["versionEvidence"]), {"latest", "3.42.0"})

    def test_cross_source_import_keeps_per_version_provenance_separate(self):
        source_a = pathlib.Path(self.tmpdir) / "source-a"
        source_b = pathlib.Path(self.tmpdir) / "source-b"
        shutil.copytree(_sample("alist"), source_a)
        shutil.copytree(_sample("alist"), source_b)
        shutil.copytree(source_b / "latest", source_b / "3.42.0")
        out_dir = pathlib.Path(self.tmpdir) / "cross-source-out"

        first = self.runner.import_one(str(source_a), str(out_dir), "latest")
        second = self.runner.import_one(str(source_b), str(out_dir), "3.42.0")

        self.assertTrue(first["success"], first.get("errors"))
        self.assertTrue(second["success"], second.get("errors"))
        evidence = json.loads(
            (out_dir / "alist" / "source-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["importSource"]["versions"], ["3.42.0"])
        self.assertEqual(
            evidence["versionEvidence"]["latest"]["importSource"]["sourcePath"],
            str(source_a),
        )
        self.assertEqual(
            evidence["versionEvidence"]["3.42.0"]["importSource"]["sourcePath"],
            str(source_b),
        )

    def test_invalid_existing_evidence_does_not_leave_partial_version(self):
        source = pathlib.Path(self.tmpdir) / "bad-evidence-source"
        shutil.copytree(_sample("alist"), source)
        shutil.copytree(source / "latest", source / "3.42.0")
        out_dir = pathlib.Path(self.tmpdir) / "bad-evidence-out"
        first = self.runner.import_one(str(source), str(out_dir), "latest")
        self.assertTrue(first["success"], first.get("errors"))
        (out_dir / "alist" / "source-evidence.json").write_text("{", encoding="utf-8")

        second = self.runner.import_one(str(source), str(out_dir), "3.42.0")

        self.assertFalse(second["success"])
        self.assertEqual(second["errorCode"], "E_BAOTA_EVIDENCE_INVALID")
        self.assertFalse((out_dir / "alist" / "3.42.0").exists())

    def test_packaged_versions_are_stable_unique_and_ignore_symlinks(self):
        app_dir = pathlib.Path(self.tmpdir) / "packaged"
        _write_text(app_dir / "latest" / "docker-compose.yml", "services: {}\n")
        _write_text(app_dir / "2.0" / "docker-compose.yml", "services: {}\n")
        os.symlink(app_dir / "latest", app_dir / "linked")

        versions = self.runner._list_packaged_versions(
            str(app_dir), ["2.0", "latest", "2.0"]
        )

        self.assertEqual(versions, ["latest", "2.0"])

    def test_import_disabled_skipped(self):
        result = self.runner.import_one(
            _sample("disabled-app"), self.tmpdir, "latest",
        )
        self.assertTrue(result.get("success"))
        self.assertTrue(result.get("skipped"))
        self.assertEqual(result.get("reason"), "App is disabled")

    def test_import_disabled_included(self):
        result = self.runner.import_one(
            _sample("disabled-app"), self.tmpdir, "latest",
            include_disabled=True,
        )
        self.assertTrue(result["success"])
        self.assertFalse(result.get("skipped", False))

    def test_import_broken_compose_fails(self):
        result = self.runner.import_one(
            _sample("broken-missing-compose"), self.tmpdir, "latest",
        )
        self.assertFalse(result["success"])
        codes = [e.get("code") for e in result.get("errors", [])]
        self.assertIn(E_BAOTA_COMPOSE_MISSING, codes)

    def test_import_missing_version_fails(self):
        result = self.runner.import_one(
            _sample("alist"), self.tmpdir, "missing-version",
        )
        self.assertFalse(result["success"])
        codes = [e.get("code") for e in result.get("errors", [])]
        self.assertIn(E_BAOTA_VERSION_DIR_MISSING, codes)

    def test_emitted_appspec_has_no_transform_metadata(self):
        parser = BaotaParser()
        app_json = parser.parse_app_json(_sample("alist"))
        compose = ComposeTransformer().transform(_sample("alist"), "latest")
        appspec = BaotaToAppSpecMapper().build_appspec(app_json, "latest", compose, _sample("alist"))
        compose_override = appspec.get("composeOverride", {}).get("compose", {})
        self.assertNotIn("_transform", compose_override)

    def test_batch_import(self):
        batch_dir = str(_SAMPLE_DIR / "apphub")
        result = self.runner.import_batch(batch_dir, self.tmpdir)
        self.assertIn("results", result)
        self.assertIn("success_count", result)
        self.assertIn("failed_count", result)
        self.assertGreater(len(result["results"]), 0)

        # disabled-app should be skipped
        disabled_items = [
            r for r in result["results"]
            if r.get("app") == "disabled-app" and r.get("skipped")
        ]
        self.assertTrue(len(disabled_items) > 0, "disabled-app should be skipped")

        # broken-missing-compose should fail
        broken_items = [
            r for r in result["results"]
            if r.get("app") == "broken-missing-compose" and not r.get("success")
        ]
        self.assertTrue(len(broken_items) > 0, "broken-missing-compose should fail")

class TestCliAndGenerator(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="baota_cli_test_")
        self.project_dir = pathlib.Path(__file__).resolve().parent.parent

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_cli(self, *args):
        cmd = [sys.executable, str(self.project_dir / "scripts" / "import-baota-app.py"), *args]
        return subprocess.run(cmd, cwd=str(self.project_dir), text=True, capture_output=True)

    def test_cli_missing_version_exits_nonzero(self):
        proc = self._run_cli(
            "--input", _sample("alist"),
            "--out-dir", self.tmpdir,
            "--version", "missing-version",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("FAILED", proc.stdout)
        self.assertFalse((pathlib.Path(self.tmpdir) / "alist").exists())

    def test_cli_batch_single_app_exits_nonzero(self):
        proc = self._run_cli(
            "--input", _sample("alist"),
            "--batch",
            "--out-dir", self.tmpdir,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("No app directories found", proc.stderr)

    def test_cli_batch_and_emit_appspec_conflict(self):
        proc = self._run_cli(
            "--input", _sample("alist"),
            "--batch",
            "--emit-appspec", str(pathlib.Path(self.tmpdir) / "alist.json"),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not allowed with argument", proc.stderr)

    def test_cli_require_validate_requires_mode(self):
        proc = self._run_cli(
            "--input", _sample("alist"),
            "--out-dir", self.tmpdir,
            "--require-validate",
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("requires --validate or --strict-store-validate", proc.stderr)

    def test_cli_precheck_only_does_not_create_adapter_output(self):
        out_dir = pathlib.Path(self.tmpdir) / "must-not-exist"
        report_path = pathlib.Path(self.tmpdir) / "precheck.json"

        proc = self._run_cli(
            "--input", _sample("alist"),
            "--out-dir", str(out_dir),
            "--precheck-only",
            "--report", str(report_path),
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(out_dir.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "precheck")
        self.assertTrue(report["success"])
        self.assertIn("latest", report["result"]["fields"]["versions"])

    def test_cli_batch_precheck_reports_every_immediate_directory(self):
        source = pathlib.Path(self.tmpdir) / "prepared-market"
        shutil.copytree(_sample("alist"), source / "valid")
        (source / "invalid").mkdir(parents=True)
        report_path = pathlib.Path(self.tmpdir) / "batch-precheck.json"

        proc = self._run_cli(
            "--input", str(source),
            "--batch",
            "--precheck-only",
            "--report", str(report_path),
        )

        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "batch-precheck")
        self.assertEqual(report["checked_count"], 2)
        self.assertEqual(report["passed_count"], 1)
        self.assertEqual(report["failed_count"], 1)
        self.assertEqual(
            {item["directory"] for item in report["items"]},
            {"valid", "invalid"},
        )

    def test_generate_from_appspec_roundtrip_complete_structure(self):
        appspec_path = pathlib.Path(self.tmpdir) / "alist.appspec.json"
        out_dir = pathlib.Path(self.tmpdir) / "generated"
        emit_proc = self._run_cli(
            "--input", _sample("alist"),
            "--emit-appspec", str(appspec_path),
            "--version", "latest",
        )
        self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)
        appspec = json.loads(appspec_path.read_text(encoding="utf-8"))
        self.assertNotIn("_transform", appspec.get("composeOverride", {}).get("compose", {}))

        gen_cmd = [
            sys.executable,
            str(self.project_dir / "scripts" / "generate-from-appspec.py"),
            "--spec", str(appspec_path),
            "--out-dir", str(out_dir),
            "--validate",
            "--require-validate",
        ]
        gen_proc = subprocess.run(gen_cmd, cwd=str(self.project_dir), text=True, capture_output=True)
        self.assertEqual(gen_proc.returncode, 0, gen_proc.stderr)

        root = out_dir / "alist"
        self.assertTrue((root / "README.md").is_file())
        readme_text = (root / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("- **Version**: latest", readme_text)
        self.assertIn("source-evidence.json", readme_text)
        self.assertTrue((root / "logo.png").is_file())
        self.assertTrue((root / "latest" / "data").is_dir())
        self.assertTrue((root / "latest" / "scripts" / "init.sh").is_file())
        self.assertTrue((root / "latest" / "scripts" / "upgrade.sh").is_file())
        self.assertTrue((root / "latest" / "scripts" / "uninstall.sh").is_file())
        uninstall_text = (root / "latest" / "scripts" / "uninstall.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('cd "$ROOT_DIR"', uninstall_text)
        self.assertIn("docker-compose down\n", uninstall_text)
        self.assertNotIn("--volumes", uninstall_text)

        root_data = yaml.safe_load((root / "data.yml").read_text(encoding="utf-8"))
        self.assertIsInstance(root_data.get("additionalProperties", {}).get("description"), dict)
        source_evidence = json.loads((root / "source-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(source_evidence["architectures"], ["amd64"])
        self.assertEqual(source_evidence["architectureEvidence"], "unverified_default")
        ver_data = yaml.safe_load((root / "latest" / "data.yml").read_text(encoding="utf-8"))
        fields = ver_data.get("additionalProperties", {}).get("formFields", [])
        self.assertTrue(fields)
        self.assertTrue(all(isinstance(field.get("label"), dict) for field in fields))

    def test_generate_from_baota_appspec_strict_validation_fails_closed(self):
        appspec_path = pathlib.Path(self.tmpdir) / "alist.appspec.json"
        out_dir = pathlib.Path(self.tmpdir) / "strict-generated"
        report_path = pathlib.Path(self.tmpdir) / "strict-report.json"
        emit_proc = self._run_cli(
            "--input", _sample("alist"),
            "--emit-appspec", str(appspec_path),
            "--version", "latest",
        )
        self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)

        gen_proc = subprocess.run(
            [
                sys.executable,
                str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                "--spec", str(appspec_path),
                "--out-dir", str(out_dir),
                "--strict-store-validate",
                "--report", str(report_path),
            ],
            cwd=str(self.project_dir),
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(gen_proc.returncode, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertFalse(report["strictValidation"]["valid"])
        self.assertTrue(report["strictValidation"]["failed"])
        self.assertNotEqual(report["strictValidation"]["returncode"], 0)
        self.assertTrue(
            any("missing key: licenseEvidence" in error for error in report["strictValidation"]["errors"]),
            report["strictValidation"]["errors"],
        )
        self.assertEqual(report["strictValidation"]["mode"], "strict-store")
        self.assertIn("validate-v2.sh", report["strictValidation"]["validator"])
        self.assertFalse(report["delivery"]["ready"])
        self.assertEqual(
            {blocker["code"] for blocker in report["delivery"]["blockers"]},
            {
                "unverified-source",
                "unverified-architectures",
                "unverified-application-license",
                "unverified-redistribution",
            },
        )

    def test_generate_from_multiple_baota_appspecs_merges_version_evidence(self):
        source = pathlib.Path(self.tmpdir) / "multi-source"
        shutil.copytree(_sample("alist"), source)
        shutil.copytree(source / "latest", source / "3.42.0")
        out_dir = pathlib.Path(self.tmpdir) / "multi-generated"

        for version in ("latest", "3.42.0"):
            appspec_path = pathlib.Path(self.tmpdir) / f"alist-{version}.json"
            emit_proc = self._run_cli(
                "--input", str(source),
                "--emit-appspec", str(appspec_path),
                "--version", version,
            )
            self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)
            gen_proc = subprocess.run(
                [
                    sys.executable,
                    str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                    "--spec", str(appspec_path),
                    "--out-dir", str(out_dir),
                ],
                cwd=str(self.project_dir),
                text=True,
                capture_output=True,
            )
            self.assertEqual(gen_proc.returncode, 0, gen_proc.stderr)

        evidence = json.loads(
            (out_dir / "alist" / "source-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["importSource"]["versions"], ["latest", "3.42.0"])
        self.assertEqual(set(evidence["versionEvidence"]), {"latest", "3.42.0"})
        self.assertTrue((out_dir / "alist" / "latest" / "docker-compose.yml").is_file())
        self.assertTrue((out_dir / "alist" / "3.42.0" / "docker-compose.yml").is_file())

    def test_generate_from_appspec_rejects_unsafe_output_paths(self):
        base_spec_path = pathlib.Path(self.tmpdir) / "safe-appspec.json"
        emit_proc = self._run_cli(
            "--input", _sample("alist"),
            "--emit-appspec", str(base_spec_path),
            "--version", "latest",
        )
        self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)
        base_spec = json.loads(base_spec_path.read_text(encoding="utf-8"))

        cases = (
            ("../escaped-app", "latest", pathlib.Path(self.tmpdir) / "escaped-app"),
            ("alist", "../escaped-version", pathlib.Path(self.tmpdir) / "generated" / "escaped-version"),
        )
        for index, (app_key, version, escaped_path) in enumerate(cases):
            with self.subTest(app_key=app_key, version=version):
                spec = dict(base_spec)
                spec["appKey"] = app_key
                spec["version"] = version
                spec_path = pathlib.Path(self.tmpdir) / f"unsafe-{index}.json"
                _write_json(spec_path, spec)
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                        "--spec", str(spec_path),
                        "--out-dir", str(pathlib.Path(self.tmpdir) / "generated"),
                    ],
                    cwd=str(self.project_dir),
                    text=True,
                    capture_output=True,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertFalse(escaped_path.exists())

    def test_generate_rejects_output_symlink_escape(self):
        spec_path = pathlib.Path(self.tmpdir) / "symlink-appspec.json"
        emit_proc = self._run_cli(
            "--input", _sample("alist"),
            "--emit-appspec", str(spec_path),
            "--version", "latest",
        )
        self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)
        out_dir = pathlib.Path(self.tmpdir) / "symlink-output"
        outside = pathlib.Path(self.tmpdir) / "outside"
        out_dir.mkdir()
        outside.mkdir()
        os.symlink(outside, out_dir / "alist")

        proc = subprocess.run(
            [
                sys.executable,
                str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                "--spec", str(spec_path),
                "--out-dir", str(out_dir),
            ],
            cwd=str(self.project_dir),
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_generate_rejects_existing_output_file_symlink(self):
        spec_path = pathlib.Path(self.tmpdir) / "file-symlink-appspec.json"
        emit_proc = self._run_cli(
            "--input", _sample("alist"),
            "--emit-appspec", str(spec_path),
            "--version", "latest",
        )
        self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)
        out_dir = pathlib.Path(self.tmpdir) / "file-symlink-generated"
        app_dir = out_dir / "alist"
        outside = pathlib.Path(self.tmpdir) / "outside-generated-data.yml"
        app_dir.mkdir(parents=True)
        outside.write_text("sentinel\n", encoding="utf-8")
        os.symlink(outside, app_dir / "data.yml")

        proc = subprocess.run(
            [
                sys.executable,
                str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                "--spec", str(spec_path),
                "--out-dir", str(out_dir),
            ],
            cwd=str(self.project_dir),
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(outside.read_text(encoding="utf-8"), "sentinel\n")

    def test_generate_invalid_existing_evidence_leaves_no_partial_version(self):
        source = pathlib.Path(self.tmpdir) / "generator-source"
        shutil.copytree(_sample("alist"), source)
        shutil.copytree(source / "latest", source / "3.42.0")
        out_dir = pathlib.Path(self.tmpdir) / "generator-output"

        for version in ("latest", "3.42.0"):
            spec_path = pathlib.Path(self.tmpdir) / f"generator-{version}.json"
            emit_proc = self._run_cli(
                "--input", str(source),
                "--emit-appspec", str(spec_path),
                "--version", version,
            )
            self.assertEqual(emit_proc.returncode, 0, emit_proc.stderr)
            if version == "latest":
                first = subprocess.run(
                    [
                        sys.executable,
                        str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                        "--spec", str(spec_path),
                        "--out-dir", str(out_dir),
                    ],
                    cwd=str(self.project_dir),
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(first.returncode, 0, first.stderr)
                (out_dir / "alist" / "source-evidence.json").write_text("{", encoding="utf-8")
            else:
                second = subprocess.run(
                    [
                        sys.executable,
                        str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                        "--spec", str(spec_path),
                        "--out-dir", str(out_dir),
                    ],
                    cwd=str(self.project_dir),
                    text=True,
                    capture_output=True,
                )
                self.assertNotEqual(second.returncode, 0)

        self.assertFalse((out_dir / "alist" / "3.42.0").exists())

    def test_generate_from_legacy_appspec_preserves_core_fields(self):
        spec_path = self.project_dir / "assets" / "sample-appspec.json"
        out_dir = pathlib.Path(self.tmpdir) / "legacy-generated"
        report_path = pathlib.Path(self.tmpdir) / "legacy-report.json"
        gen_cmd = [
            sys.executable,
            str(self.project_dir / "scripts" / "generate-from-appspec.py"),
            "--spec", str(spec_path),
            "--out-dir", str(out_dir),
            "--validate",
            "--require-validate",
            "--report", str(report_path),
        ]
        gen_proc = subprocess.run(gen_cmd, cwd=str(self.project_dir), text=True, capture_output=True)
        self.assertEqual(gen_proc.returncode, 0, gen_proc.stderr)

        root = out_dir / "demo-app"
        self.assertGreater((root / "logo.png").stat().st_size, 0)
        evidence = json.loads((root / "source-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["repository"], "https://github.com/nginx/nginx")
        self.assertEqual(evidence["dockerDocs"], "https://hub.docker.com/_/nginx")
        compose_text = (root / "1.0.0" / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("${PANEL_APP_PORT_HTTP}:80", compose_text)
        self.assertIn("${APP_DATA_DIR}:/usr/share/nginx/html", compose_text)
        ver_data = yaml.safe_load((root / "1.0.0" / "data.yml").read_text(encoding="utf-8"))
        fields = ver_data.get("additionalProperties", {}).get("formFields", [])
        self.assertIn("PANEL_APP_PORT_HTTP", {field.get("envKey") for field in fields})
        self.assertTrue(report_path.is_file())

    def test_generate_from_appspec_uses_default_logo(self):
        spec_path = pathlib.Path(self.tmpdir) / "min.appspec.json"
        out_dir = pathlib.Path(self.tmpdir) / "out"
        report_path = pathlib.Path(self.tmpdir) / "report.json"
        spec_path.write_text(json.dumps({
            "appKey": "minapp",
            "title": "Min App",
            "description": "Minimal app",
            "shortDescZh": "最小应用",
            "type": "Tool",
            "tag": "Tool",
            "version": "latest",
            "image": "nginx:latest",
            "ports": [{"envKey": "PANEL_APP_PORT_HTTP", "containerPort": 80, "hostDefault": 8080}],
        }), encoding="utf-8")
        gen_cmd = [
            sys.executable,
            str(self.project_dir / "scripts" / "generate-from-appspec.py"),
            "--spec", str(spec_path),
            "--out-dir", str(out_dir),
            "--validate",
            "--require-validate",
            "--report", str(report_path),
        ]
        proc = subprocess.run(gen_cmd, cwd=str(self.project_dir), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        app_dir = out_dir / "minapp"
        logo_path = app_dir / "logo.png"
        self.assertGreater(logo_path.stat().st_size, 0)
        notice_path = app_dir / "ASSET-LICENSES" / "default-logo.txt"
        self.assertTrue(notice_path.is_file())
        self.assertIn("Permission is hereby granted", notice_path.read_text(encoding="utf-8"))
        evidence = json.loads((app_dir / "source-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["logoEvidence"]["license"], "MIT")
        self.assertEqual(
            evidence["logoEvidence"]["sha256"],
            hashlib.sha256(logo_path.read_bytes()).hexdigest(),
        )
        redistribution = evidence["redistributionEvidence"]
        self.assertEqual(redistribution["status"], "verified")
        self.assertEqual(
            redistribution["requiredFiles"],
            ["ASSET-LICENSES/default-logo.txt"],
        )
        self.assertEqual(
            redistribution["materials"][0]["sha256"],
            hashlib.sha256(notice_path.read_bytes()).hexdigest(),
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "generated_candidate")
        self.assertFalse(report["delivery"]["ready"])
        self.assertIn(
            "unverified-application-license",
            {blocker["code"] for blocker in report["delivery"]["blockers"]},
        )

    def test_default_logo_preserves_application_redistribution_requirements(self):
        spec_path = pathlib.Path(self.tmpdir) / "licensed.appspec.json"
        out_dir = pathlib.Path(self.tmpdir) / "licensed-output"
        app_dir = out_dir / "licensed-app"
        license_bytes = b"MIT application license\n"
        app_dir.mkdir(parents=True)
        (app_dir / "LICENSE").write_bytes(license_bytes)
        default_logo = self.project_dir / "assets" / "default-logo.png"
        _write_json(spec_path, {
            "appKey": "licensed-app",
            "title": "Licensed App",
            "description": "Application with redistribution obligations",
            "shortDescZh": "带再分发要求的应用",
            "type": "Tool",
            "tag": "Tool",
            "version": "latest",
            "image": "nginx:latest",
            "licenseEvidence": {"spdx": "MIT"},
            "redistributionEvidence": {
                "status": "verified",
                "requiredFiles": ["LICENSE"],
                "materials": [{
                    "path": "LICENSE",
                    "sha256": hashlib.sha256(license_bytes).hexdigest(),
                    "purpose": "application license",
                }],
                "assets": [{
                    "path": "logo.png",
                    "source": "bundled:assets/default-logo.svg",
                    "license": "MIT",
                    "sha256": hashlib.sha256(default_logo.read_bytes()).hexdigest(),
                    "requiredFiles": [],
                }],
            },
            "ports": [{
                "envKey": "PANEL_APP_PORT_HTTP",
                "containerPort": 80,
                "hostDefault": 8080,
            }],
        })

        proc = subprocess.run(
            [
                sys.executable,
                str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                "--spec", str(spec_path),
                "--out-dir", str(out_dir),
            ],
            cwd=str(self.project_dir),
            text=True,
            capture_output=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        evidence = json.loads(
            (app_dir / "source-evidence.json").read_text(encoding="utf-8")
        )
        redistribution = evidence["redistributionEvidence"]
        self.assertEqual(redistribution["status"], "verified")
        self.assertCountEqual(
            redistribution["requiredFiles"],
            ["LICENSE", "ASSET-LICENSES/default-logo.txt"],
        )
        materials_by_path = {
            material["path"]: material
            for material in redistribution["materials"]
        }
        self.assertEqual(
            materials_by_path["LICENSE"]["sha256"],
            hashlib.sha256(license_bytes).hexdigest(),
        )
        self.assertIn("ASSET-LICENSES/default-logo.txt", materials_by_path)
        logo_assets = [
            asset
            for asset in redistribution["assets"]
            if asset.get("path") == "logo.png"
        ]
        self.assertEqual(len(logo_assets), 1)
        self.assertEqual(
            logo_assets[0]["requiredFiles"],
            ["ASSET-LICENSES/default-logo.txt"],
        )

    def test_generation_without_validation_cannot_report_delivery_ready(self):
        spec_path = pathlib.Path(self.tmpdir) / "unvalidated.appspec.json"
        out_dir = pathlib.Path(self.tmpdir) / "unvalidated-output"
        report_path = pathlib.Path(self.tmpdir) / "unvalidated-report.json"
        default_logo = self.project_dir / "assets" / "default-logo.png"
        _write_json(spec_path, {
            "appKey": "unvalidated-app",
            "title": "Unvalidated App",
            "description": "License-complete but structurally unvalidated",
            "shortDescZh": "许可完整但未校验的应用",
            "type": "Tool",
            "tag": "Tool",
            "version": "latest",
            "image": "nginx:latest",
            "licenseEvidence": {"spdx": "MIT"},
            "redistributionEvidence": {
                "status": "verified",
                "requiredFiles": [],
                "materials": [],
                "assets": [{
                    "path": "logo.png",
                    "source": "bundled:assets/default-logo.svg",
                    "license": "MIT",
                    "sha256": hashlib.sha256(default_logo.read_bytes()).hexdigest(),
                    "requiredFiles": [],
                }],
            },
            "ports": [{
                "envKey": "PANEL_APP_PORT_HTTP",
                "containerPort": 80,
                "hostDefault": 8080,
            }],
        })

        proc = subprocess.run(
            [
                sys.executable,
                str(self.project_dir / "scripts" / "generate-from-appspec.py"),
                "--spec", str(spec_path),
                "--out-dir", str(out_dir),
                "--report", str(report_path),
            ],
            cwd=str(self.project_dir),
            text=True,
            capture_output=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertFalse(report["validateRequested"])
        self.assertIsNone(report["validation"])
        self.assertIsNone(report["strictValidation"])
        self.assertEqual(
            {
                "reportStatus": report["status"],
                "applicable": report["delivery"]["applicable"],
                "baotaApplicable": report["delivery"]["baotaApplicable"],
                "ready": report["delivery"]["ready"],
                "deliveryStatus": report["delivery"]["status"],
                "blockerCodes": {
                    blocker["code"]
                    for blocker in report["delivery"]["blockers"]
                },
            },
            {
                "reportStatus": "generated_candidate",
                "applicable": True,
                "baotaApplicable": False,
                "ready": False,
                "deliveryStatus": "manual_review_required",
                "blockerCodes": {"validation-not-run"},
            },
        )


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
