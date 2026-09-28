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
    service_index = 0
    prefix = '${CONTAINER_NAME}'
    reserved_names = {
        match.group(1).strip().strip('"').strip("'")
        for line in lines
        if (match := re.match(r'^\s{4}container_name:\s*(.*?)\s*$', line))
        and match.group(1).strip().strip('"').strip("'").startswith(prefix)
    }
    used_names = set()

    def unique_name(raw_name, service_name, primary_service):
        if raw_name.startswith(prefix) and raw_name not in used_names:
            candidate = raw_name
        else:
            candidate = prefix if primary_service else f'{prefix}-{service_name}'
            if candidate in used_names or candidate in reserved_names:
                base = f'{prefix}-{service_name}'
                candidate = base
                serial = 2
                while candidate in used_names or candidate in reserved_names:
                    candidate = f'{base}-{serial}'
                    serial += 1
        used_names.add(candidate)
        return candidate

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

        service_name = re.match(r'^\s{2}([A-Za-z0-9_.-]+):\s*$', line).group(1)
        primary_service = service_index == 0

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
            normalized = []
            for item in block:
                name_match = re.match(r'^\s*container_name:\s*(.*?)\s*$', item)
                if not name_match:
                    normalized.append(item)
                    continue
                raw_name = name_match.group(1).strip().strip('"').strip("'")
                name = unique_name(raw_name, service_name, primary_service)
                normalized.append(f'    container_name: {name}')
            block = normalized
        else:
            name = unique_name('', service_name, primary_service)
            block.insert(insert_after_image, f'    container_name: {name}')

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
        service_index += 1

    new_text = "\n".join(lines) + "\n"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: patch_compose_yml.py <compose.yml> [app_type]", file=sys.stderr)
        sys.exit(2)
    patch_compose(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "")
