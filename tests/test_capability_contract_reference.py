#!/usr/bin/env python3
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOPOLOGY = REPO_ROOT / "references" / "topology-preflight.md"
LIFECYCLE = REPO_ROOT / "references" / "lifecycle-safety.md"
SKILL = REPO_ROOT / "SKILL.md"


class CapabilityContractReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.topology = TOPOLOGY.read_text(encoding="utf-8")
        cls.lifecycle = LIFECYCLE.read_text(encoding="utf-8")
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.flat_topology = " ".join(cls.topology.split()).casefold()
        cls.flat_lifecycle = " ".join(cls.lifecycle.split()).casefold()
        cls.flat_skill = " ".join(cls.skill.split()).casefold()

    def test_preflight_records_a_user_visible_capability_contract(self) -> None:
        for guard in (
            "capability contract",
            "user-visible capabilities",
            "full upstream default",
            "capability-equivalent alternative",
            "service, image, environment, and dependency",
            "enabled by default",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)

    def test_reduced_capability_profiles_are_explicit_and_fail_closed(self) -> None:
        for guard in (
            "reduced-capability profile",
            "preserve the full upstream capability set by default",
            "only when the user explicitly requests reduced capability",
            "which features become unavailable",
            "compatible image variant",
            "do not describe it as the default",
            "disclosure does not substitute for capability preservation",
            "blocks scaffolding",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)

    def test_report_configuration_claims_match_the_delivered_controls(self) -> None:
        for guard in (
            "configuration claim ledger",
            "fixed, defaulted, generated, optional, or user-configurable",
            "editable form field",
            "user-configurable with a default of",
            "compare every report claim",
            "compose, `data.yml`, `.env.sample`, and lifecycle scripts",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_lifecycle)

    def test_primary_skill_exposes_both_completion_gates(self) -> None:
        for guard in (
            "capability contract",
            "reduced-capability profile",
            "configuration claim ledger",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_skill)


if __name__ == "__main__":
    unittest.main()
