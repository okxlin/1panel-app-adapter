import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from panel_form_contract import service_derived_envkeys
import test_validate_v2


class PanelFormContractTests(unittest.TestCase):
    def metadata(self):
        return {"additionalProperties": {"formFields": [{
            "envKey": "PANEL_DB_TYPE", "type": "apps", "required": True,
            "default": "mysql", "values": [{"value": "mysql"}, {"value": "mariadb"}],
            "child": {"envKey": "PANEL_DB_HOST", "type": "service", "required": True},
        }]}}

    def test_only_required_known_database_selectors_derive_port(self):
        self.assertEqual(service_derived_envkeys(self.metadata()), {"PANEL_DB_PORT"})
        for key in ("mysql", "mariadb", "postgresql"):
            data = {"additionalProperties": {"formFields": [{
                "envKey": "PANEL_DB_HOST", "type": "service", "key": key, "required": True,
            }]}}
            self.assertEqual(service_derived_envkeys(data), {"PANEL_DB_PORT"})
        for mutate in (
            lambda f: f[0]["child"].update(type="text"),
            lambda f: f[0]["child"].update(required=False),
            lambda f: f[0]["child"].update(envKey="REDIS_HOST"),
            lambda f: f[0].update(required=False),
            lambda f: f[0].update(envKey="UNRELATED_TYPE"),
            lambda f: f[0].update(values=[{"value": "redis"}]),
            lambda f: f[0].update(default="unknown"),
            lambda f: f[0].update(values=[]),
            lambda f: f.append(copy.deepcopy(f[0])),
        ):
            data = self.metadata()
            mutate(data["additionalProperties"]["formFields"])
            self.assertEqual(service_derived_envkeys(data), set(), data)
        for data in ({}, {"additionalProperties": []}, {"additionalProperties": {"formFields": "invalid"}}):
            self.assertEqual(service_derived_envkeys(data), set())

    def test_validator_accepts_bound_shape_without_global_exemption(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = test_validate_v2.ValidateV2Tests()._write_sample_app(Path(tmp))
            version = app / "latest"
            compose = version / "docker-compose.yml"
            compose.write_text(compose.read_text().replace(
                "      - DB_HOST=${PANEL_DB_HOST}",
                "      - DB_HOST=${PANEL_DB_HOST}\n      - DB_PORT=${PANEL_DB_PORT}",
            ))
            sample = version / ".env.sample"
            # Explicit fixture binding; no guessed value is added by the generator.
            sample.write_text(sample.read_text() + "PANEL_DB_PORT=13306\n")
            command = ["bash", str(ROOT / "scripts/validate-v2.sh"), "--dir", str(app)]
            good = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            self.assertIn("PANEL_DB_PORT is service-derived", good.stdout)
            self.assertIn("selector structure is not runtime evidence", good.stdout)
            metadata = version / "data.yml"
            original = yaml.safe_load(metadata.read_text())
            for field_type in ("text", "service"):
                data = copy.deepcopy(original)
                data["additionalProperties"]["formFields"][0] = {
                    "envKey": "PANEL_DB_HOST", "type": field_type,
                    "required": True, "key": "redis",
                }
                metadata.write_text(yaml.safe_dump(data))
                bad = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn("compose variable not declared in formFields envKey: PANEL_DB_PORT", bad.stdout)
            metadata.write_text(yaml.safe_dump(original))
            compose.write_text(compose.read_text().replace("${PANEL_DB_PORT}", "${UNRELATED_PORT}"))
            bad = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("compose variable not declared in formFields envKey: UNRELATED_PORT", bad.stdout)


if __name__ == "__main__":
    unittest.main()
