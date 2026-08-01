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

    def test_completion_gates_front_load_low_model_quality_guards(self) -> None:
        router = self.skill[self.start : self.rule_priority]
        for guard in (
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
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, router)


if __name__ == "__main__":
    unittest.main()
