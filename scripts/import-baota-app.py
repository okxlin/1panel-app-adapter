#!/usr/bin/env python3

import argparse
import json
import os
import pathlib
import sys
import traceback


EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_VALIDATION_FAILURE = 2


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Import Baota Docker Store apps to 1Panel format / "
            "将宝塔 Docker 商店应用转换为 1Panel 格式"
        )
    )
    parser.add_argument("--input", required=True, help="Path to single app dir or apphub dir / 单应用目录或应用仓库目录路径")
    parser.add_argument("--out-dir", default="./1panel-apps", help="Directory for output 1Panel apps / 1Panel 应用输出目录")
    parser.add_argument("--version", default="latest", help="Target version, e.g. latest or 3.42.0 / 目标版本，如 latest 或 3.42.0")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--batch", action="store_true", help="Batch import subdirectories under input / 批量导入输入目录下的应用子目录")
    mode_group.add_argument("--emit-appspec", help="Only generate AppSpec JSON to this path / 仅生成 AppSpec JSON 到该路径")
    parser.add_argument("--validate", action="store_true", help="Run basic validation after import / 导入后执行基础校验")
    parser.add_argument("--strict-store-validate", action="store_true", help="Run strict store validation / 执行严格商店校验")
    parser.add_argument("--require-validate", action="store_true", help="Exit non-zero if validation fails / 校验失败时返回非零退出码")
    parser.add_argument("--include-disabled", action="store_true", help="Import apps with appstatus=0 / 导入 appstatus=0 的应用")
    parser.add_argument("--report", help="Write JSON import report to this path / 将 JSON 导入报告写入该路径")
    return parser.parse_args()


def load_library():
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from baota_import_lib import BaotaParser, BaotaToAppSpecMapper, ComposeTransformer, ImportRunner
    except ImportError as exc:
        text = str(exc).lower()
        if getattr(exc, "name", None) == "yaml" or "pyyaml" in text or "yaml" in text:
            print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
            raise SystemExit(EXIT_FAILURE)
        raise
    return ImportRunner, BaotaParser, BaotaToAppSpecMapper, ComposeTransformer


def ensure_input_dir(path_value):
    path = pathlib.Path(path_value)
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(path_value)
    return path


def write_json(path_value, data):
    path = pathlib.Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def validation_failed(result):
    if not isinstance(result, dict):
        return False
    nested = result.get("validation")
    if isinstance(nested, dict):
        if isinstance(nested.get("failed"), bool):
            return nested["failed"]
        if nested.get("errors"):
            return True
    if isinstance(result.get("validation_failed"), bool):
        return result["validation_failed"]
    return False


def handle_exception(exc):
    if isinstance(exc, FileNotFoundError):
        print(f"Error: Input directory not found: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    traceback.print_exc(file=sys.stderr)
    return EXIT_FAILURE


def summarize_single(input_dir, result, success):
    return {"mode": "single", "input": str(input_dir), "success": success, "result": result}


def result_name(item):
    if isinstance(item, dict):
        for key in ("app", "name", "slug", "app_name"):
            value = item.get(key)
            if value:
                return str(value)
    return None


def result_error(item):
    if isinstance(item, dict):
        for key in ("error", "code", "message"):
            value = item.get(key)
            if value:
                return str(value)
        errors = item.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("message") or first.get("code") or "unknown error")
            return str(first)
    return None


def normalize_batch_items(raw_result, candidates, out_dir, version):
    app_names = [path.name for path in candidates]
    candidate_names = set(app_names)
    items = []

    if isinstance(raw_result, dict):
        for key in ("results", "items", "apps"):
            value = raw_result.get(key)
            if isinstance(value, list):
                items = value
                break

    if not items:
        return [
            {"name": name, "status": "unknown", "message": None, "target": str(out_dir / name), "version": version}
            for name in app_names
        ]

    normalized = []
    seen = set()
    for item in items:
        name = result_name(item)
        if not name:
            continue
        seen.add(name)
        skipped = bool(item.get("skipped", False)) if isinstance(item, dict) else False
        success = bool(item.get("success", item.get("ok", False))) if isinstance(item, dict) else False
        if skipped:
            status = "skipped"
        elif success:
            status = "ok"
        else:
            status = "failed"
        normalized.append(
            {
                "name": name,
                "status": status,
                "message": None if (success or skipped) else result_error(item),
                "target": str(out_dir / name) if not skipped else None,
                "version": version,
                "reason": item.get("reason") if isinstance(item, dict) and skipped else None,
            }
        )

    for name in sorted(candidate_names - seen):
        normalized.append({"name": name, "status": "unknown", "message": None, "target": str(out_dir / name), "version": version})
    return normalized


def exit_for_result(require_validate, result, failed_count):
    if require_validate and validation_failed(result):
        return EXIT_VALIDATION_FAILURE
    if failed_count > 0:
        return EXIT_FAILURE
    return EXIT_SUCCESS


def run_single_import(args):
    ImportRunner, _, _, _ = load_library()
    input_dir = ensure_input_dir(args.input)
    out_dir = pathlib.Path(args.out_dir)
    app_name = input_dir.name

    try:
        runner = ImportRunner()
        result = runner.import_one(
            str(input_dir),
            str(out_dir),
            args.version,
            args.include_disabled,
            args.validate,
            args.strict_store_validate,
            args.require_validate,
        )
    except Exception as exc:
        print(f"Importing {app_name} ({args.version})... FAILED: {exc}")
        if args.report:
            write_json(args.report, summarize_single(input_dir, {"error": str(exc), "error_type": type(exc).__name__}, False))
            print(f"Report: {args.report}")
        return handle_exception(exc)

    if result.get("skipped"):
        print(f"Importing {app_name} ({args.version})... SKIPPED: {result.get('reason', 'unknown')}")
        if args.report:
            write_json(args.report, summarize_single(input_dir, result, True))
            print(f"Report: {args.report}")
        return exit_for_result(args.require_validate, result, 0)

    if not result.get("success"):
        message = result_error(result) or "unknown error"
        print(f"Importing {app_name} ({args.version})... FAILED: {message}")
        if args.report:
            write_json(args.report, summarize_single(input_dir, result, False))
            print(f"Report: {args.report}")
        return EXIT_FAILURE

    print(f"Importing {app_name} ({args.version})... OK → {out_dir / app_name}")
    if args.report:
        write_json(args.report, summarize_single(input_dir, result, True))
        print(f"Report: {args.report}")
    return exit_for_result(args.require_validate, result, 0)


def discover_batch_candidates(input_dir):
    return sorted(path for path in input_dir.iterdir() if path.is_dir() and (path / "app.json").exists())


def run_batch_import(args):
    ImportRunner, _, _, _ = load_library()
    input_dir = ensure_input_dir(args.input)
    out_dir = pathlib.Path(args.out_dir)
    candidates = discover_batch_candidates(input_dir)
    if not candidates:
        print(f"No app directories found under: {input_dir}", file=sys.stderr)
        if args.report:
            write_json(args.report, {"mode": "batch", "input": str(input_dir), "apps": [], "success_count": 0, "failed_count": 1})
            print(f"Report: {args.report}")
        return EXIT_FAILURE

    try:
        runner = ImportRunner()
        raw_result = runner.import_batch(
            str(input_dir),
            str(out_dir),
            args.version,
            args.include_disabled,
            args.validate,
            args.strict_store_validate,
            args.require_validate,
        )
    except Exception as exc:
        for app_dir in candidates:
            print(f"Importing {app_dir.name} ({args.version})... FAILED: {exc}")
        payload = {
            "mode": "batch",
            "input": str(input_dir),
            "apps": [path.name for path in candidates],
            "success_count": 0,
            "failed_count": len(candidates),
            "result": {"error": str(exc), "error_type": type(exc).__name__},
        }
        if args.report:
            write_json(args.report, payload)
            print(f"Report: {args.report}")
        return handle_exception(exc)

    items = normalize_batch_items(raw_result, candidates, out_dir, args.version)
    success_count = 0
    failed_count = 0

    for item in items:
        if item["status"] == "ok":
            success_count += 1
            print(f"Importing {item['name']} ({item['version']})... OK → {item['target']}")
        elif item["status"] == "skipped":
            print(f"Importing {item['name']} ({item['version']})... SKIPPED: {item.get('reason', 'unknown')}")
        elif item["status"] == "failed":
            failed_count += 1
            print(f"Importing {item['name']} ({item['version']})... FAILED: {item['message'] or 'unknown error'}")
        else:
            failed_count += 1
            print(f"Importing {item['name']} ({item['version']})... FAILED: unknown import status")

    if isinstance(raw_result, dict):
        if "success_count" in raw_result:
            success_count = int(raw_result["success_count"])
        elif "success" in raw_result and isinstance(raw_result["success"], int):
            success_count = int(raw_result["success"])
        if "failed_count" in raw_result:
            failed_count = int(raw_result["failed_count"])
        elif "failed" in raw_result and isinstance(raw_result["failed"], int):
            failed_count = int(raw_result["failed"])

    print(f"Summary: {success_count} success, {failed_count} failed")
    if args.report:
        write_json(
            args.report,
            {
                "mode": "batch",
                "input": str(input_dir),
                "apps": [path.name for path in candidates],
                "success_count": success_count,
                "failed_count": failed_count,
                "validation_failed": validation_failed(raw_result),
                "items": items,
                "result": raw_result,
            },
        )
        print(f"Report: {args.report}")
    return exit_for_result(args.require_validate, raw_result, failed_count)


def run_emit_appspec(args):
    _, BaotaParser, BaotaToAppSpecMapper, ComposeTransformer = load_library()
    input_dir = ensure_input_dir(args.input)
    parser = BaotaParser()
    mapper = BaotaToAppSpecMapper()
    transformer = ComposeTransformer()
    app_json = parser.parse_app_json(str(input_dir))
    versions = parser.list_versions(str(input_dir))
    selected_version = parser.select_version(versions, args.version)
    compose_data = transformer.transform(str(input_dir), selected_version)
    appspec = mapper.build_appspec(app_json, selected_version, compose_data, str(input_dir))
    write_json(args.emit_appspec, appspec)
    print(f"AppSpec written: {args.emit_appspec}")
    return EXIT_SUCCESS


def main():
    args = parse_args()
    try:
        if args.emit_appspec:
            return run_emit_appspec(args)
        if args.batch:
            return run_batch_import(args)
        return run_single_import(args)
    except FileNotFoundError as exc:
        print(f"Error: Input directory not found: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except ImportError as exc:
        text = str(exc).lower()
        if getattr(exc, "name", None) == "yaml" or "pyyaml" in text or "yaml" in text:
            print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
            return EXIT_FAILURE
        traceback.print_exc(file=sys.stderr)
        return EXIT_FAILURE
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
