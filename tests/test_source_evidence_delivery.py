#!/usr/bin/env python3

import hashlib
import pathlib
import sys
import tempfile
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from baota_import_lib import evaluate_baota_delivery_readiness
from source_evidence import validate_source_evidence


class SourceEvidenceDeliveryTests(unittest.TestCase):
    def test_required_delivery_rejects_placeholder_application_spdx(self) -> None:
        for spdx in ("unknown", "placeholder"):
            with self.subTest(spdx=spdx):
                payload = {
                    "licenseEvidence": {
                        "spdx": spdx,
                        "url": "https://example.com/LICENSE",
                    },
                    "redistributionEvidence": {
                        "status": "verified",
                        "requiredFiles": [],
                        "assets": [{
                            "path": "logo.png",
                            "source": "https://example.com/logo.png",
                            "license": "MIT",
                            "sha256": "a" * 64,
                            "requiredFiles": [],
                        }],
                    },
                }

                errors = validate_source_evidence(
                    payload,
                    require_urls=False,
                    require_delivery=True,
                )

                self.assertTrue(
                    any("licenseEvidence.spdx" in error for error in errors),
                    errors,
                )

    def test_required_delivery_rejects_placeholder_verified_asset_license(self) -> None:
        for asset_license in ("unknown", "placeholder"):
            with self.subTest(asset_license=asset_license):
                payload = {
                    "licenseEvidence": {
                        "spdx": "MIT",
                        "url": "https://example.com/LICENSE",
                    },
                    "redistributionEvidence": {
                        "status": "verified",
                        "requiredFiles": [],
                        "assets": [{
                            "path": "logo.png",
                            "source": "https://example.com/logo.png",
                            "license": asset_license,
                            "sha256": "a" * 64,
                            "requiredFiles": [],
                        }],
                    },
                }

                errors = validate_source_evidence(
                    payload,
                    require_urls=False,
                    require_delivery=True,
                )

                self.assertTrue(
                    any(
                        "redistributionEvidence.assets[0].license" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_logo_evidence_hash_must_match_delivered_logo_and_asset_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            logo = app_dir / "logo.png"
            logo.write_bytes(b"verified-logo")
            logo_hash = hashlib.sha256(logo.read_bytes()).hexdigest()
            payload = {
                "licenseEvidence": {"spdx": "MIT"},
                "logoEvidence": {
                    "source": "https://example.com/logo.png",
                    "license": "MIT",
                    "sha256": "a" * 64,
                },
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": [],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": logo_hash,
                        "requiredFiles": [],
                    }],
                },
            }

            errors = validate_source_evidence(
                payload,
                require_urls=False,
                artifact_root=app_dir,
                require_delivery=True,
            )

        self.assertTrue(
            any("logoEvidence.sha256" in error for error in errors),
            errors,
        )

    def test_logo_evidence_source_must_match_delivered_logo_asset_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            logo = app_dir / "logo.png"
            logo.write_bytes(b"verified-logo")
            logo_hash = hashlib.sha256(logo.read_bytes()).hexdigest()
            payload = {
                "licenseEvidence": {"spdx": "MIT"},
                "logoEvidence": {
                    "source": "https://example.com/wrong-logo.png",
                    "license": "MIT",
                    "sha256": logo_hash,
                },
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": [],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": logo_hash,
                        "requiredFiles": [],
                    }],
                },
            }

            errors = validate_source_evidence(
                payload,
                require_urls=False,
                artifact_root=app_dir,
                require_delivery=True,
            )

        self.assertTrue(
            any("logoEvidence.source" in error for error in errors),
            errors,
        )

    def test_redistribution_evidence_rejects_escaping_paths(self) -> None:
        payload = {
            "redistributionEvidence": {
                "status": "verified",
                "requiredFiles": ["../LICENSE"],
                "assets": [
                    {
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": "a" * 64,
                        "requiredFiles": ["../LICENSE"],
                    }
                ],
            }
        }

        errors = validate_source_evidence(payload, require_urls=False)

        self.assertIn(
            "redistributionEvidence.requiredFiles[0] must be a safe package-relative path",
            errors,
        )
        self.assertIn(
            "redistributionEvidence.assets[0].requiredFiles[0] must be a safe package-relative path",
            errors,
        )

    def test_ordinary_candidate_is_not_ready_without_license_review(self) -> None:
        delivery = evaluate_baota_delivery_readiness({"appKey": "demo"})

        self.assertFalse(delivery["ready"])
        self.assertEqual(delivery["status"], "manual_review_required")
        self.assertEqual(
            {blocker["code"] for blocker in delivery["blockers"]},
            {"unverified-application-license", "unverified-redistribution"},
        )
        self.assertEqual(delivery["licenseReview"]["requiredFiles"], [])
        self.assertEqual(delivery["licenseReview"]["deliveredFiles"], [])

    def test_verified_redistribution_rejects_unverified_or_escaping_sources(self) -> None:
        for source, expected in (
            (
                "unverified:logo.png",
                "redistributionEvidence.assets[0].source must be verified when status is verified",
            ),
            (
                "bundled:../logo.png",
                "redistributionEvidence.assets[0].source must use a safe bundled repo-relative path",
            ),
        ):
            with self.subTest(source=source):
                payload = {
                    "redistributionEvidence": {
                        "status": "verified",
                        "requiredFiles": [],
                        "assets": [{
                            "path": "logo.png",
                            "source": source,
                            "license": "MIT",
                            "sha256": "a" * 64,
                            "requiredFiles": [],
                        }],
                    },
                }

                errors = validate_source_evidence(payload, require_urls=False)

                self.assertIn(expected, errors)

    def test_verified_redistribution_rejects_sources_with_boundary_whitespace(self) -> None:
        for source, expected in (
            (
                " unverified:logo.png ",
                "redistributionEvidence.assets[0].source must not contain surrounding whitespace",
            ),
            (
                " bundled:../logo.png ",
                "redistributionEvidence.assets[0].source must not contain surrounding whitespace",
            ),
        ):
            with self.subTest(source=source):
                payload = {
                    "redistributionEvidence": {
                        "status": "verified",
                        "requiredFiles": [],
                        "assets": [{
                            "path": "logo.png",
                            "source": source,
                            "license": "MIT",
                            "sha256": "a" * 64,
                            "requiredFiles": [],
                        }],
                    },
                }

                errors = validate_source_evidence(payload, require_urls=False)

                self.assertIn(expected, errors)

    def test_verified_delivery_reports_material_paths_and_asset_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            logo = app_dir / "logo.png"
            logo.write_bytes(b"verified-logo")
            notice = app_dir / "ASSET-LICENSES" / "logo.txt"
            notice.parent.mkdir()
            notice.write_text("license notice\n", encoding="utf-8")
            logo_hash = hashlib.sha256(logo.read_bytes()).hexdigest()
            notice_hash = hashlib.sha256(notice.read_bytes()).hexdigest()
            spec = {
                "appKey": "demo",
                "licenseEvidence": {
                    "spdx": "MIT",
                    "url": "https://example.com/LICENSE",
                },
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": ["ASSET-LICENSES/logo.txt"],
                    "materials": [{
                        "path": "ASSET-LICENSES/logo.txt",
                        "sha256": notice_hash,
                        "purpose": "logo license",
                    }],
                    "assets": [
                        {
                            "path": "logo.png",
                            "source": "https://example.com/logo.png",
                            "license": "MIT",
                            "sha256": logo_hash,
                            "requiredFiles": ["ASSET-LICENSES/logo.txt"],
                        }
                    ],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertTrue(delivery["ready"])
        self.assertEqual(delivery["status"], "ready")
        self.assertEqual(delivery["licenseReview"]["redistributionStatus"], "verified")
        self.assertEqual(
            delivery["licenseReview"]["requiredFiles"],
            ["ASSET-LICENSES/logo.txt"],
        )
        self.assertEqual(
            delivery["licenseReview"]["deliveredFiles"],
            ["ASSET-LICENSES/logo.txt"],
        )
        self.assertEqual(delivery["licenseReview"]["assets"][0]["sha256"], logo_hash)
        self.assertTrue(delivery["licenseReview"]["materials"][0]["hashMatches"])

    def test_missing_required_license_material_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            logo = app_dir / "logo.png"
            logo.write_bytes(b"verified-logo")
            spec = {
                "appKey": "demo",
                "licenseEvidence": {"spdx": "MIT"},
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": ["LICENSE"],
                    "materials": [{
                        "path": "LICENSE",
                        "sha256": hashlib.sha256(b"license notice\n").hexdigest(),
                    }],
                    "assets": [
                        {
                            "path": "logo.png",
                            "source": "https://example.com/logo.png",
                            "license": "MIT",
                            "sha256": hashlib.sha256(logo.read_bytes()).hexdigest(),
                            "requiredFiles": ["LICENSE"],
                        }
                    ],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertFalse(delivery["ready"])
        self.assertIn(
            "missing-redistribution-material",
            {blocker["code"] for blocker in delivery["blockers"]},
        )
        self.assertEqual(delivery["licenseReview"]["requiredFiles"], ["LICENSE"])
        self.assertEqual(delivery["licenseReview"]["deliveredFiles"], [])

    def test_symlinked_required_material_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp) / "app"
            app_dir.mkdir()
            logo = app_dir / "logo.png"
            logo.write_bytes(b"verified-logo")
            outside = pathlib.Path(tmp) / "outside-license"
            outside.write_text("license notice\n", encoding="utf-8")
            (app_dir / "LICENSE").symlink_to(outside)
            spec = {
                "licenseEvidence": {"spdx": "MIT"},
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": ["LICENSE"],
                    "materials": [{
                        "path": "LICENSE",
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": hashlib.sha256(logo.read_bytes()).hexdigest(),
                        "requiredFiles": ["LICENSE"],
                    }],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertFalse(delivery["ready"])
        self.assertIn(
            "missing-redistribution-material",
            {blocker["code"] for blocker in delivery["blockers"]},
        )
        self.assertEqual(delivery["licenseReview"]["deliveredFiles"], [])

    def test_mismatched_asset_hash_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            (app_dir / "logo.png").write_bytes(b"actual-logo")
            spec = {
                "licenseEvidence": {"spdx": "MIT"},
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": [],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": "a" * 64,
                        "requiredFiles": [],
                    }],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertFalse(delivery["ready"])
        self.assertIn(
            "invalid-redistribution-asset",
            {blocker["code"] for blocker in delivery["blockers"]},
        )
        self.assertFalse(delivery["licenseReview"]["assets"][0]["hashMatches"])

    def test_verified_ledger_must_track_delivered_logo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            (app_dir / "logo.png").write_bytes(b"logo")
            other = app_dir / "other.bin"
            other.write_bytes(b"other")
            spec = {
                "licenseEvidence": {"spdx": "MIT"},
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": [],
                    "materials": [],
                    "assets": [{
                        "path": "other.bin",
                        "source": "https://example.com/other.bin",
                        "license": "MIT",
                        "sha256": hashlib.sha256(other.read_bytes()).hexdigest(),
                        "requiredFiles": [],
                    }],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertFalse(delivery["ready"])
        self.assertIn(
            "untracked-redistribution-asset",
            {blocker["code"] for blocker in delivery["blockers"]},
        )

    def test_wrong_required_material_content_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            logo = app_dir / "logo.png"
            logo.write_bytes(b"logo")
            license_file = app_dir / "LICENSE"
            license_file.write_bytes(b"wrong terms")
            spec = {
                "licenseEvidence": {"spdx": "MIT"},
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": ["LICENSE"],
                    "materials": [{
                        "path": "LICENSE",
                        "sha256": hashlib.sha256(b"expected terms").hexdigest(),
                    }],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": hashlib.sha256(logo.read_bytes()).hexdigest(),
                        "requiredFiles": ["LICENSE"],
                    }],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertFalse(delivery["ready"])
        self.assertIn(
            "invalid-redistribution-material",
            {blocker["code"] for blocker in delivery["blockers"]},
        )
        self.assertFalse(delivery["licenseReview"]["materials"][0]["hashMatches"])

    def test_empty_required_material_blocks_readiness_even_when_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = pathlib.Path(tmp)
            logo = app_dir / "logo.png"
            logo.write_bytes(b"logo")
            (app_dir / "LICENSE").write_bytes(b"")
            spec = {
                "licenseEvidence": {"spdx": "MIT"},
                "redistributionEvidence": {
                    "status": "verified",
                    "requiredFiles": ["LICENSE"],
                    "materials": [{
                        "path": "LICENSE",
                        "sha256": hashlib.sha256(b"").hexdigest(),
                    }],
                    "assets": [{
                        "path": "logo.png",
                        "source": "https://example.com/logo.png",
                        "license": "MIT",
                        "sha256": hashlib.sha256(logo.read_bytes()).hexdigest(),
                        "requiredFiles": ["LICENSE"],
                    }],
                },
            }

            delivery = evaluate_baota_delivery_readiness(spec, app_dir=app_dir)

        self.assertFalse(delivery["ready"])
        self.assertIn(
            "invalid-redistribution-material",
            {blocker["code"] for blocker in delivery["blockers"]},
        )


if __name__ == "__main__":
    unittest.main()
