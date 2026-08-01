#!/usr/bin/env python3
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "SKILL.md"


class SkillRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.start = cls.skill.find("## Start Here")
        cls.rule_priority = cls.skill.find("## Rule Priority")

    def test_execution_router_is_front_loaded(self) -> None:
        self.assertNotEqual(self.start, -1, "SKILL.md needs a Start Here router")
        self.assertNotEqual(self.rule_priority, -1, "SKILL.md needs its rule priority section")
        self.assertLess(self.start, self.rule_priority)
        self.assertLess(self.skill[: self.start].count("\n"), 40)

    def test_router_covers_every_advertised_workflow(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        for workflow in (
            "official Docker/Compose",
            "AppSpec",
            "v1 or mixed package",
            "aaPanel/Baota",
            "existing v2 app",
            "validate only",
            "PHP runtime",
        ):
            with self.subTest(workflow=workflow):
                self.assertIn(workflow.casefold(), router.casefold())

    def test_router_names_exact_commands_and_conditional_references(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        self.assertIn("Open and read every reference", router)
        for command in (
            "bash scripts/scaffold-v2.sh",
            "python3 scripts/generate-from-appspec.py",
            "bash scripts/migrate-v1-to-v2.sh",
            "python3 scripts/import-baota-app.py",
            "python3 scripts/patch_root_data_yml.py",
            "python3 scripts/patch_version_data_yml.py",
            "python3 scripts/patch_compose_yml.py",
            "bash scripts/gen-env-sample.sh",
            "bash scripts/finalize_runtime_scripts.sh <app-dir> <app-dir>/<version>",
            "bash scripts/normalize-logo.sh",
            "bash scripts/validate-v2.sh",
        ):
            with self.subTest(command=command):
                self.assertIn(command, router)

        for reference in (
            "references/source-policy.md",
            "references/topology-preflight.md",
            "references/lifecycle-safety.md",
            "references/appspec.md",
            "references/baota-app-format.md",
            "references/baota-migration-workflow.md",
            "references/baota-to-1panel-mapping.md",
            "references/upgrade-maintenance.md",
            "references/php-runtime.md",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, router)

    def test_each_route_binds_its_command_references_and_review_step(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        expected = {
            1: (
                "scripts/scaffold-v2.sh",
                "references/source-policy.md",
                "references/topology-preflight.md",
                "references/lifecycle-safety.md",
            ),
            2: (
                "scripts/generate-from-appspec.py",
                "references/appspec.md",
                "references/source-policy.md",
                "references/lifecycle-safety.md",
            ),
            3: (
                "scripts/migrate-v1-to-v2.sh",
                "references/upgrade-maintenance.md",
                "references/lifecycle-safety.md",
            ),
            4: (
                "scripts/import-baota-app.py",
                "references/baota-app-format.md",
                "references/baota-migration-workflow.md",
                "references/baota-to-1panel-mapping.md",
                "references/lifecycle-safety.md",
            ),
            5: (
                "helper commands",
                "references/upgrade-maintenance.md",
                "references/lifecycle-safety.md",
            ),
            6: (
                "scripts/validate-v2.sh",
                "references/source-policy.md",
                "references/lifecycle-safety.md",
            ),
            7: (
                "helper commands",
                "references/php-runtime.md",
                "references/lifecycle-safety.md",
            ),
        }

        for number, required in expected.items():
            route = next(
                (line for line in router.splitlines() if line.startswith(f"{number}. ")),
                "",
            )
            with self.subTest(route=number):
                self.assertTrue(route, f"route {number} is missing")
                self.assertIn("review", route.casefold())
                for item in required:
                    self.assertIn(item, route)

        baota_route = next(line for line in router.splitlines() if line.startswith("4. "))
        self.assertIn("--precheck-only", baota_route)
        self.assertIn("--version <exact-version>", baota_route)
        self.assertNotIn("--version latest", baota_route)

    def test_completion_gates_cover_static_and_runtime_readiness(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        for gate in (
            "baseline validation",
            "--strict-store --i18n-mode strict",
            "real 1Panel",
            "install",
            "readiness",
            "restart",
            "uninstall",
            "cleanup",
            "assumptions",
            "warnings",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, router)

    def test_new_app_route_stops_before_scaffolding_unsuitable_topologies(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        route = next(line for line in router.splitlines() if line.startswith("1. "))
        for requirement in (
            "preflight decision before scaffolding",
            "platform_stack_terminal",
            "specialized_conditional",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, route)

    def test_new_app_route_defines_parent_output_and_public_url_contracts(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        route = next(line for line in router.splitlines() if line.startswith("1. "))
        for requirement in (
            '--out-dir "$RUN_ROOT/artifact"',
            '"$RUN_ROOT/artifact/<app-key>"',
            "data.yml",
            "source-evidence.json",
            "<app-key>/<app-key>",
            "localhost",
            "127.0.0.1",
            "required form field",
            "optional",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, route)

    def test_source_policy_documents_backward_compatible_optional_evidence(self) -> None:
        policy = (REPO_ROOT / "references" / "source-policy.md").read_text(encoding="utf-8")
        appspec = (REPO_ROOT / "references" / "appspec.md").read_text(encoding="utf-8")
        for field in (
            "sourceRevision",
            "imageEvidence",
            "images",
            "licenseEvidence",
            "logoEvidence",
            "redistributionEvidence",
        ):
            with self.subTest(field=field):
                self.assertIn(field, policy)
                self.assertIn(field, appspec)

    def test_source_policy_requires_an_authoritative_control_inventory(self) -> None:
        policy = (REPO_ROOT / "references" / "source-policy.md").read_text(encoding="utf-8")
        flat_policy = " ".join(policy.split())
        for guard in (
            "authoritative control inventory",
            "environment variables",
            "healthchecks",
            "capabilities",
            "security options",
            "justify every omission or change",
            "compare the final Compose",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, policy)

        self.assertIn(
            "compare the final Compose control by control with the inventory. Preserve every "
            "source-backed control and justify every omission or change",
            flat_policy,
        )
        self.assertIn(
            "Keep official fixed hardening values fixed in Compose; do not drop one merely "
            "because it does not need an install form field.",
            flat_policy,
        )
        for weakened_rule in (
            "fixed hardening values without form fields may be omitted",
            "drop fixed environment values that do not need user input",
            "only preserve controls exposed through the install form",
        ):
            with self.subTest(weakened_rule=weakened_rule):
                self.assertNotIn(weakened_rule.casefold(), flat_policy.casefold())

    def test_cycle_one_evidence_repairs_are_explicit(self) -> None:
        policy = (REPO_ROOT / "references" / "source-policy.md").read_text(
            encoding="utf-8"
        )
        for guard in (
            "platform child digest",
            "same registry descriptor",
            "index digest",
            "assets/default-logo.svg",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), policy.casefold())

        for guard in (
            "CONTAINER_NAME=<app-key>-compose-check",
            "must be non-empty",
            "platform child digest",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard.casefold(), self.skill.casefold())

    def test_public_url_policy_separates_external_origin_from_internal_listener(self) -> None:
        policy = (REPO_ROOT / "references" / "source-policy.md").read_text(encoding="utf-8")
        for guard in (
            "full public URL",
            "current upstream variable",
            "internal listener",
            "reverse proxy",
            "TLS termination",
            "trusted-proxy",
            "Do not reconstruct",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, policy)

    def test_source_policy_delivers_material_license_restrictions_to_users(self) -> None:
        policy = (REPO_ROOT / "references" / "source-policy.md").read_text(encoding="utf-8")
        flat_policy = " ".join(policy.split())
        for guard in (
            "material use restrictions",
            "README",
            "not only `source-evidence.json`",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, flat_policy)

    def test_source_policy_delivers_required_redistribution_materials(self) -> None:
        policy = (REPO_ROOT / "references" / "source-policy.md").read_text(encoding="utf-8")
        flat_policy = " ".join(policy.split())
        required_rule = (
            "When the exact application or asset terms require attribution, a copyright notice, "
            "a license copy, source disclosure, or a NOTICE file for redistribution, include the "
            "required material in the delivered AppStore package; a URL in `source-evidence.json` "
            "is not a substitute."
        )
        self.assertIn(required_rule, flat_policy)
        self.assertIn(
            "Verify asset terms separately; do not assume the application code license covers a "
            "logo, icon, font, trademark, or other bundled media.",
            flat_policy,
        )
        for weakened_rule in (
            "permissive licenses never require notice delivery",
            "a license URL is always sufficient for redistribution",
            "the application license automatically covers the logo",
        ):
            with self.subTest(weakened_rule=weakened_rule):
                self.assertNotIn(weakened_rule, flat_policy.casefold())

    def test_output_contract_distinguishes_delivered_files_from_run_only_evidence(self) -> None:
        output_contract = self.skill[
            self.skill.index("## Output Contract") : self.skill.index("## Notes")
        ]
        flat_skill = " ".join(output_contract.split())
        self.assertIn(
            "Which cited files are delivered in the AppStore package and which evidence caches "
            "remain run-only",
            flat_skill,
        )

    def test_completion_gates_front_load_low_model_quality_guards(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        flat_router = " ".join(router.split())
        for guard in (
            "authoritative control inventory",
            "startup configuration contract",
            "official install examples",
            "configuration reference",
            "startup source",
            "required value",
            "environment variables",
            "healthchecks",
            "capabilities",
            "security options",
            "justify every omission or change",
            "full public URL",
            "internal listener",
            "current upstream variable",
            "material use restrictions",
            "redistribution",
            "minimal install form",
            "Never `source` or `eval`",
            "every Compose service",
            "exact delivered artifact",
            "license",
            "English fields",
            "runtime UID/GID",
            "confined",
            "exact source file",
            "secret format",
            "URL-encode",
            "unresolved asset license",
            "neutral placeholder immediately",
            "run-only evidence caches",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, router)

        self.assertIn(
            "Compare the final Compose against that inventory, preserve every source-backed "
            "control, and justify every omission or change",
            flat_router,
        )
        self.assertIn(
            "A fixed upstream hardening value is not an optional install-form setting; keep it "
            "fixed unless evidence supports changing it.",
            flat_router,
        )
        for weakened_rule in (
            "fixed hardening values without form fields may be omitted",
            "drop fixed environment values that do not need user input",
            "only preserve controls exposed through the install form",
        ):
            with self.subTest(weakened_rule=weakened_rule):
                self.assertNotIn(weakened_rule.casefold(), flat_router.casefold())

    def test_completion_gates_require_startup_configuration_closure(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        flat_router = " ".join(router.split())
        for invariant in (
            "every available exact-version authority",
            "record unavailable authorities",
            "source or exact-image/runtime evidence",
            "required, startup-fatal, stability-bearing, or coupled",
            "selected or default-dependent optional",
            "official Compose",
            "final Compose",
            "`data.yml`",
            "`.env.sample`",
            "source-backed lifecycle logic",
            "`required: true`",
            "`paramComplexity`",
            "application-specific validation contract",
            "before Compose starts",
            "successful Compose render",
            "application startup",
        ):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, flat_router)


if __name__ == "__main__":
    unittest.main()
