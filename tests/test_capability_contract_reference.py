#!/usr/bin/env python3
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOPOLOGY = REPO_ROOT / "references" / "topology-preflight.md"
LIFECYCLE = REPO_ROOT / "references" / "lifecycle-safety.md"
SOURCE_POLICY = REPO_ROOT / "references" / "source-policy.md"
SKILL = REPO_ROOT / "SKILL.md"


class CapabilityContractReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.topology = TOPOLOGY.read_text(encoding="utf-8")
        cls.lifecycle = LIFECYCLE.read_text(encoding="utf-8")
        cls.source_policy = SOURCE_POLICY.read_text(encoding="utf-8")
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.flat_topology = " ".join(cls.topology.split()).casefold()
        cls.flat_lifecycle = " ".join(cls.lifecycle.split()).casefold()
        cls.flat_source_policy = " ".join(cls.source_policy.split()).casefold()
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
                self.assertIn(guard.casefold(), self.flat_skill)

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

    def test_default_profile_does_not_pre_publish_optional_access(self) -> None:
        for guard in (
            "default capability set excludes optional features that are not enabled by default",
            "do not pre-publish optional listeners, mounts, devices, capabilities, or host permissions",
            "selected profile explicitly enables and fully configures",
            "for later configuration",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)
                self.assertIn(guard.casefold(), self.flat_skill)

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

    def test_missing_page_uses_historical_official_source_fallback(self) -> None:
        for guard in (
            "a single 404 or moved page is not a terminal condition",
            "exact release tag or source tree",
            "official documentation repositories",
            "historical compose",
            "record every attempted official source",
            "concrete unsafe unknown",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_source_policy)

        for guard in (
            "historical official source fallback",
            "a single 404",
            "concrete unsafe unknown",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)
                self.assertIn(guard.casefold(), self.flat_skill)

    def test_preflight_census_covers_every_official_deployment_root(self) -> None:
        for guard in (
            "deployment-shape census",
            "official install guides",
            "every referenced sample or compose root",
            "selected or rejected",
            "include/template chain",
            "before assigning any route",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)
                self.assertIn(guard.casefold(), self.flat_skill)

    def test_terminal_route_does_not_skip_published_image_inspection(self) -> None:
        for guard in (
            "terminal route does not waive",
            "oci manifest",
            "oci config",
            "base, bootstrap, or runtime images",
            "record the unavailable registry fact",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)
                self.assertIn(guard.casefold(), self.flat_skill)

    def test_complex_shape_does_not_veto_a_supported_smaller_shape(self) -> None:
        for guard in (
            "evaluate each deployment shape independently",
            "a more complex production topology does not invalidate a smaller official topology",
            "production-ready label is scoped evidence, not an exclusivity claim",
            "officially required, exclusive, deprecated, or capability-incomplete",
            "external-service boundary",
            "platform_stack_terminal only after",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)
                self.assertIn(guard.casefold(), self.flat_skill)

    def test_shape_selection_uses_an_explicit_decision_ledger(self) -> None:
        for guard in (
            "deployment-shape decision ledger",
            "support scope",
            "default capability set",
            "external dependency ownership",
            "migration and upgrade boundary",
            "selected, conditional, or rejected",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.flat_topology)
                self.assertIn(guard.casefold(), self.flat_skill)


if __name__ == "__main__":
    unittest.main()
