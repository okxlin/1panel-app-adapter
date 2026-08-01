#!/usr/bin/env python3
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "references" / "lifecycle-safety.md"
SKILL = REPO_ROOT / "SKILL.md"


class LifecycleSafetyReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = REFERENCE.read_text(encoding="utf-8")
        cls.skill_text = SKILL.read_text(encoding="utf-8")
        cls.flat_text = " ".join(cls.text.split())
        cls.flat_skill_text = " ".join(cls.skill_text.split())

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
            "selected authoritative deployment uses a named volume",
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
                self.assertIn(guard.casefold(), self.flat_text.casefold())

    def test_mount_mechanism_preserves_operator_access_contract(self) -> None:
        for guard in (
            "mount mechanism",
            "mount options",
            "read/write mode",
            "`z`/`Z`",
            "host-side editing",
            "not a drop-in replacement",
            "fixed package-local bind",
            "do not add an `APP_DATA_DIR` form",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_text.casefold())

    def test_official_mount_options_are_required_until_incompatibility_is_proven(self) -> None:
        for guard in (
            "authoritative Compose",
            "required delivery defaults",
            "target-platform documentation or runtime evidence",
            "not proven necessary",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.text.casefold())

        self.assertIn("required delivery defaults", self.skill_text)
        self.assertIn("target-platform evidence", self.skill_text)
        self.assertIn(
            "Change a mount default only when target-platform documentation or runtime "
            "evidence proves it incompatible",
            self.flat_text,
        )
        for weakened_rule in (
            "when they are required by the upstream deployment contract",
            "Use a named volume only when direct host access is unnecessary",
            "prefer an upstream-recommended named volume when direct host access is not required",
        ):
            with self.subTest(weakened_rule=weakened_rule):
                self.assertNotIn(weakened_rule.casefold(), self.flat_skill_text.casefold())
        self.assertNotIn(
            "Convert a bind to a named volume only when direct host access is not required",
            self.flat_text,
        )
        self.assertNotIn(
            "Prefer an upstream-recommended named volume when direct host access is not a "
            "package requirement".casefold(),
            self.flat_text.casefold(),
        )
        for text in (self.flat_skill_text, self.flat_text):
            with self.subTest(text=text[:32]):
                self.assertIn(
                    "selected authoritative deployment uses a named volume",
                    text.casefold(),
                )

    def test_primary_skill_has_one_bind_parameterization_rule(self) -> None:
        for obsolete in (
            "Only when upstream explicitly uses host path mapping, convert to `APP_DATA_DIR_*`",
            "our adaptation artifacts prioritize recommending `APP_DATA_DIR(_N)`",
            "Default at least provide one `APP_DATA_DIR`",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete.casefold(), self.skill_text.casefold())

        self.assertIn("operator-access contract", self.skill_text)
        self.assertIn("selectable host path", self.skill_text)
        self.assertIn("mount options", self.skill_text)

    def test_fixed_non_root_bind_uses_dedicated_helper_option(self) -> None:
        self.assertIn("--fixed-dir-owner", self.text)
        self.assertIn("without a form field", self.text)

    def test_runtime_identity_requires_published_image_evidence(self) -> None:
        self.assertIn("OCI `Config.User`", self.text)
        self.assertIn("Compose `user`", self.text)
        self.assertIn("Dockerfile", self.text)
        self.assertIn("startup identity", self.text)
        self.assertIn("steady-state identity", self.text)
        self.assertIn("entrypoint", self.text)

    def test_observed_owner_and_mode_are_not_reported_as_portable_guarantees(self) -> None:
        for text in (self.text, self.skill_text):
            with self.subTest(source=text[:32]):
                self.assertIn("invoking UID/GID", text)
                self.assertIn("umask", text)
                self.assertIn("portable guarantee", text)
                self.assertIn("explicitly enforces", text)

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
