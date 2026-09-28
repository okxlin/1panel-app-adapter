import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "patch_compose_yml.py"
spec = importlib.util.spec_from_file_location("patch_compose_names", SCRIPT)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class ContainerNameTests(unittest.TestCase):
    def test_duplicate_names_and_reserved_suffixes_are_stable(self):
        for names in (
            ["${CONTAINER_NAME}", "${CONTAINER_NAME}", None],
            ["${CONTAINER_NAME}-shared", "${CONTAINER_NAME}-shared", None],
            ["${CONTAINER_NAME}", "${CONTAINER_NAME}", "${CONTAINER_NAME}-worker"],
            [None, "${CONTAINER_NAME}", "${CONTAINER_NAME}-web"],
        ):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "compose.yml"
                lines = ["services:"]
                for service, name in zip(("web", "worker", "cache"), names):
                    lines.extend([f"  {service}:", "    image: example/app:1.0"])
                    if name is not None:
                        lines.append(f"    container_name: {name}")
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                patcher.patch_compose(path)
                first = path.read_bytes()
                result = yaml.safe_load(first)["services"]
                actual = [service["container_name"] for service in result.values()]
                self.assertEqual(3, len(set(actual)), actual)
                for name in set(names) - {None}:
                    self.assertIn(name, actual)
                patcher.patch_compose(path)
                self.assertEqual(first, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
