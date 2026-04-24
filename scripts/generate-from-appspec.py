#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_TOP_FIELDS = [
    "appKey",
    "title",
    "version",
    "image",
    "port",
    "targetPort",
    "type",
    "sourceEvidence",
]

REQUIRED_SOURCE_EVIDENCE = ["repository", "dockerDocs", "composeFile"]
DEFAULT_OUT_DIR = "/home/node/.openclaw/workspace/artifacts/1panel-apps"


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate app artifacts from minimal appspec JSON")
    parser.add_argument("--spec", required=True, help="Path to appspec JSON")
    parser.add_argument("--out-dir", help="Override output directory")
    parser.add_argument("--validate", action="store_true", help="Run strict-store validation after generation")
    parser.add_argument("--require-validate", action="store_true", help="Fail if --validate is not enabled")
    parser.add_argument("--report", help="Write run report JSON to this file path")
    args = parser.parse_args()

    if args.require_validate and not args.validate:
        _fail("--require-validate requires --validate")

    spec_path = Path(args.spec).resolve()
    if not spec_path.is_file():
        _fail(f"spec file not found: {spec_path}")

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"invalid JSON spec: {exc}")

    for key in REQUIRED_TOP_FIELDS:
        if key not in spec:
            _fail(f"spec missing required field: {key}")

    source_evidence = spec.get("sourceEvidence")
    if not isinstance(source_evidence, dict):
        _fail("sourceEvidence must be an object")
    for key in REQUIRED_SOURCE_EVIDENCE:
        value = source_evidence.get(key)
        if not isinstance(value, str) or not value.strip():
            _fail(f"sourceEvidence.{key} must be a non-empty string")
        if not re.match(r"^https://[^\s]+$", value.strip()):
            _fail(f"sourceEvidence.{key} must be an https URL")

    script_dir = Path(__file__).resolve().parent
    scaffold = script_dir / "scaffold-v2.sh"
    if not scaffold.is_file():
        _fail(f"scaffold script not found: {scaffold}")

    out_dir = args.out_dir or spec.get("outDir") or spec.get("outputDir")
    effective_out_dir = out_dir or DEFAULT_OUT_DIR
    tz_value = spec.get("timezone", "Asia/Shanghai")
    if not isinstance(tz_value, str) or not tz_value.strip():
        _fail("timezone must be a non-empty string when provided")

    cmd = [
        "bash",
        str(scaffold),
        "--app-key",
        str(spec["appKey"]),
        "--title",
        str(spec["title"]),
        "--image",
        str(spec["image"]),
        "--version",
        str(spec["version"]),
        "--port",
        str(spec["port"]),
        "--target-port",
        str(spec["targetPort"]),
        "--type",
        str(spec["type"]),
        "--source-repository",
        str(source_evidence["repository"]),
        "--source-docker-docs",
        str(source_evidence["dockerDocs"]),
        "--source-compose-file",
        str(source_evidence["composeFile"]),
    ]

    cmd.extend(["--out-dir", str(effective_out_dir)])
    if spec.get("tag"):
        cmd.extend(["--tag", str(spec["tag"])])
    if _as_bool(spec.get("withPanelDeps", False)):
        cmd.append("--with-panel-deps")
    if tz_value:
        cmd.extend(["--timezone", tz_value.strip()])

    volumes = spec.get("volumes")
    if isinstance(volumes, list) and volumes:
        cmd.extend(["--volumes", ",".join(str(v) for v in volumes)])

    target_root = Path(effective_out_dir)
    app_dir = target_root / str(spec["appKey"])

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spec": str(spec_path),
        "appKey": str(spec["appKey"]),
        "version": str(spec["version"]),
        "sourceEvidence": {
            "repository": str(source_evidence.get("repository", "")),
            "dockerDocs": str(source_evidence.get("dockerDocs", "")),
            "composeFile": str(source_evidence.get("composeFile", "")),
        },
        "outputDir": str(target_root),
        "appDir": str(app_dir),
        "validateRequested": bool(args.validate),
        "requireValidate": bool(args.require_validate),
        "validatedAt": "",
        "validateSummary": {
            "fail": None,
            "warn": None,
            "info": None,
        },
        "qualityGate": "not_run",
        "status": "failed",
        "step": "init",
        "error": "",
    }

    try:
        report["step"] = "generate"
        subprocess.run(cmd, check=True)

        if args.validate:
            validate = script_dir / "validate-v2.sh"
            if not validate.is_file():
                raise FileNotFoundError(f"validate script not found: {validate}")
            validate_cmd = [
                "bash",
                str(validate),
                "--dir",
                str(app_dir),
                "--strict-store",
            ]
            report["step"] = "validate"
            validate_proc = subprocess.run(validate_cmd, check=True, capture_output=True, text=True)
            if validate_proc.stdout:
                print(validate_proc.stdout, end="")
            if validate_proc.stderr:
                print(validate_proc.stderr, end="", file=sys.stderr)

            summary_line = ""
            for line in validate_proc.stdout.splitlines():
                if line.startswith("SUMMARY:"):
                    summary_line = line

            if summary_line:
                m = re.search(r"fail=(\d+)\s+warn=(\d+)\s+info=(\d+)", summary_line)
                if m:
                    report["validateSummary"] = {
                        "fail": int(m.group(1)),
                        "warn": int(m.group(2)),
                        "info": int(m.group(3)),
                    }
            report["validatedAt"] = datetime.now(timezone.utc).isoformat()
            report["qualityGate"] = "passed"

        report["status"] = "ok"
        report["step"] = "done"
    except subprocess.CalledProcessError as exc:
        report["error"] = f"command failed with exit code {exc.returncode}: {exc.cmd}"
        if getattr(exc, "stdout", None):
            print(exc.stdout, end="")
        if getattr(exc, "stderr", None):
            print(exc.stderr, end="", file=sys.stderr)
        if report.get("step") == "validate" and getattr(exc, "stdout", None):
            summary_line = ""
            for line in exc.stdout.splitlines():
                if line.startswith("SUMMARY:"):
                    summary_line = line
            if summary_line:
                m = re.search(r"fail=(\d+)\s+warn=(\d+)\s+info=(\d+)", summary_line)
                if m:
                    report["validateSummary"] = {
                        "fail": int(m.group(1)),
                        "warn": int(m.group(2)),
                        "info": int(m.group(3)),
                    }
            report["qualityGate"] = "failed"
        if args.report:
            report_path = Path(args.report).resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    except Exception as exc:
        report["error"] = str(exc)
        if args.report:
            report_path = Path(args.report).resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise

    if args.report:
        report_path = Path(args.report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
