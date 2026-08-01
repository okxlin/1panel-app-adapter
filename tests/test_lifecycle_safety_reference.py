#!/usr/bin/env python3
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "references" / "lifecycle-safety.md"


class LifecycleSafetyReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = REFERENCE.read_text(encoding="utf-8")

    def test_requires_a_mount_and_lifecycle_ledger(self) -> None:
        for field in (
            "host source",
            "container target",
            "file or directory",
            "runtime UID/GID",
            "creation",
            "ownership",
            "upgrade",
            "uninstall",
        ):
            with self.subTest(field=field):
                self.assertIn(field.casefold(), self.text.casefold())

    def test_path_and_ownership_rules_cover_known_escape_modes(self) -> None:
        for guard in (
            "absolute paths",
            "`..` traversal",
            "symbolic links",
            "recursive `chown`",
            "--no-dereference",
            "resolved target",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.text.casefold())

    def test_non_root_writable_bind_has_a_fail_closed_decision_procedure(self) -> None:
        for guard in (
            "upstream-recommended named volume",
            "--dir-owner",
            "--replace-init",
            "root-created `0755`",
            "direct child",
            "root-owned",
            "parent chain",
            "descriptor-based initializer",
            "stat",
            "write probe",
            "blocks delivery",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.text.casefold())

    def test_runtime_identity_requires_published_image_evidence(self) -> None:
        self.assertIn("OCI `Config.User`", self.text)
        self.assertIn("Compose `user`", self.text)
        self.assertIn("Dockerfile", self.text)
        self.assertIn("startup identity", self.text)
        self.assertIn("steady-state identity", self.text)
        self.assertIn("entrypoint", self.text)

    def test_file_secret_and_url_contracts_are_explicit(self) -> None:
        for guard in (
            "exact source file",
            "application's exact format",
            "stable across upgrades",
            "URL-encode",
            "keyword/value DSN",
            "connection string",
            "PKCS#12",
            "Base64",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.text.casefold())

    def test_custom_path_scripts_preserve_generated_confinement(self) -> None:
        self.assertIn("Do not replace the generated confinement", self.text)
        self.assertIn("inside-root symbolic link", self.text)
        self.assertIn("outside-root symbolic link", self.text)
        self.assertIn('for part in "${parts[@]}"', self.text)
        self.assertIn('[[ ! -L "$current" ]]', self.text)

    def test_aio_image_does_not_clear_specialized_route(self) -> None:
        self.assertIn("AIO image", self.text)
        self.assertIn("specialized_conditional", self.text)


if __name__ == "__main__":
    unittest.main()
