#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def patch_compose(path: Path, app_type: str = ""):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if text and not text.endswith("\n"):
        text += "\n"

    raw_lines = text.splitlines()
    lines = [line for line in raw_lines if not re.match(r"^version:\s*.*$", line)]

    for idx, line in enumerate(lines):
        m = re.match(r'^(\s*image:\s*)(.+?)\s*$', line)
        if m:
            value = m.group(2).strip()
            if not (value.startswith('"') and value.endswith('"')):
                cleaned = value.strip('"')
                lines[idx] = f'{m.group(1)}"{cleaned}"'

    in_services = False
    for idx, line in enumerate(lines):
        if re.match(r'^services:\s*$', line):
            in_services = True
            continue
        if in_services and line and not line.startswith(' '):
            in_services = False
        if not in_services:
            continue
        m = re.match(r'^(\s*)-\s*"?(\d+):(\d+)"?\s*$', line)
        if m:
            indent = m.group(1)
            container_port = m.group(3)
            lines[idx] = f'{indent}- "${{PANEL_APP_PORT_HTTP}}:{container_port}"'

    in_services = False
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if re.match(r'^services:\s*$', line):
            in_services = True
            idx += 1
            continue
        if in_services and line and not line.startswith(' '):
            in_services = False
        if not in_services:
            idx += 1
            continue
        if not re.match(r'^\s{2}[A-Za-z0-9_.-]+:\s*$', line):
            idx += 1
            continue

        block_start = idx + 1
        block_end = len(lines)
        for probe_idx in range(block_start, len(lines)):
            probe = lines[probe_idx]
            if re.match(r'^\s{2}[A-Za-z0-9_.-]+:\s*$', probe):
                block_end = probe_idx
                break
            if probe and not probe.startswith(' '):
                block_end = probe_idx
                break

        block = lines[block_start:block_end]
        has_container_name = any(re.match(r'^\s{4}container_name:\s*', item) for item in block)
        has_labels_block = any(re.match(r'^\s{4}labels:\s*$', item) for item in block)
        has_created_by = any(re.match(r'^\s{6}createdBy:\s*.*$', item) for item in block)

        insert_after_image = 0
        for block_idx, item in enumerate(block):
            if re.match(r'^\s{4}image:\s*', item):
                insert_after_image = block_idx + 1
                break

        if has_container_name:
            block = [re.sub(r'^\s*container_name:\s*.*$', '    container_name: ${CONTAINER_NAME}', item) for item in block]
        else:
            block.insert(insert_after_image, '    container_name: ${CONTAINER_NAME}')

        has_healthcheck = any(re.match(r'^\s{4}healthcheck:\s*$', item) for item in block)
        normalized_type = (app_type or "").strip().lower()
        has_http_ports = any(re.match(r'^\s*-\s*"?\$\{PANEL_APP_PORT_HTTP\}:(\d+)"?\s*$', item) or re.match(r'^\s*-\s*"?(\d+):(\d+)"?\s*$', item) for item in block)
        if not has_healthcheck and normalized_type == "website" and has_http_ports:
            container_port = "80"
            for item in block:
                m_port = re.match(r'^\s*-\s*"?\$\{PANEL_APP_PORT_HTTP\}:(\d+)"?\s*$', item)
                if m_port:
                    container_port = m_port.group(1)
                    break
                m_port = re.match(r'^\s*-\s*"?(\d+):(\d+)"?\s*$', item)
                if m_port:
                    container_port = m_port.group(2)
                    break
            insert_healthcheck_at = len(block)
            for block_idx, item in enumerate(block):
                if re.match(r'^\s{4}labels:\s*$', item) or re.match(r'^\s{4}restart:\s*', item):
                    insert_healthcheck_at = block_idx
                    break
            block.insert(insert_healthcheck_at, '    healthcheck:')
            block.insert(insert_healthcheck_at + 1, f'      test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1:{container_port} || exit 1"]')
            block.insert(insert_healthcheck_at + 2, '      interval: 30s')
            block.insert(insert_healthcheck_at + 3, '      timeout: 10s')
            block.insert(insert_healthcheck_at + 4, '      retries: 3')

        if not has_created_by:
            insert_labels_at = len(block)
            for block_idx, item in enumerate(block):
                if re.match(r'^\s{4}restart:\s*', item):
                    insert_labels_at = block_idx
                    break
            if has_labels_block:
                label_idx = next(i for i, item in enumerate(block) if re.match(r'^\s{4}labels:\s*$', item))
                block.insert(label_idx + 1, '      createdBy: "Apps"')
            else:
                block.insert(insert_labels_at, '    labels:')
                block.insert(insert_labels_at + 1, '      createdBy: "Apps"')

        lines[block_start:block_end] = block
        idx = block_start + len(block)

    new_text = "\n".join(lines) + "\n"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: patch_compose_yml.py <compose.yml> [app_type]", file=sys.stderr)
        sys.exit(2)
    patch_compose(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "")
