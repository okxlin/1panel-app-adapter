#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def usage():
    print(
        "usage: gen_env_sample.py <version-data.yml> <out-.env.sample> "
        "[docker-compose.yml] [container-name]",
        file=sys.stderr,
    )


if len(sys.argv) not in (3, 4, 5):
    usage()
    sys.exit(2)

src = Path(sys.argv[1])
out = Path(sys.argv[2])
compose_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
app_key = out.parent.parent.name
default_container_name = (
    f"{app_key}-compose-check"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", app_key or "")
    else "adapter-compose-check"
)
container_name = sys.argv[4] if len(sys.argv) > 4 else default_container_name
if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container_name) is None:
    print("FAIL: container-name must be a valid non-empty Docker container name", file=sys.stderr)
    sys.exit(2)
if not src.is_file():
    print(f"FAIL: not found: {src}", file=sys.stderr)
    sys.exit(1)

lines = src.read_text(encoding="utf-8", errors="ignore").splitlines()

in_ff = False
ff_indent = None
item_indent = None
cur = None
items = []


def flush():
    global cur
    if cur and cur.get("envKey"):
        items.append(cur)
    cur = None


def unquote(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


# Parse formFields including child sections
i = 0
in_child = False
child_indent = None
child_cur = None

while i < len(lines):
    line = lines[i]
    if not in_ff:
        m = re.match(r"^(\s*)formFields:\s*$", line)
        if m:
            in_ff = True
            ff_indent = len(m.group(1))
        i += 1
        continue

    if line.strip() and not line.lstrip().startswith("#"):
        indent = len(line) - len(line.lstrip(" \t"))
        if indent <= (ff_indent or 0) and not re.match(r"^\s*-\s*", line):
            flush()
            in_ff = False
            ff_indent = None
            item_indent = None
            in_child = False
            child_indent = None
            i += 1
            continue

    # Handle child section
    if in_child:
        m_child_item = re.match(r"^(\s*)-\s*(.*)$", line)
        if m_child_item:
            child_indent_cur = len(m_child_item.group(1))
            if child_indent_cur <= (child_indent or 0):
                # End of child section
                if child_cur and child_cur.get("envKey"):
                    items.append(child_cur)
                child_cur = None
                in_child = False
                child_indent = None
                # Don't increment i, re-process this line
                continue
            else:
                # New child item
                if child_cur and child_cur.get("envKey"):
                    items.append(child_cur)
                child_cur = {}
                rest = m_child_item.group(2).strip()
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if k in {"envKey", "default"}:
                        child_cur[k] = unquote(v)
                i += 1
                continue

        # Parse child key-value pairs
        if child_cur is not None:
            m_kv = re.match(r"^\s*([A-Za-z0-9_]+):\s*(.*)$", line)
            if m_kv:
                k = m_kv.group(1)
                v = m_kv.group(2).strip()
                if k in {"envKey", "default"}:
                    child_cur[k] = unquote(v)
        i += 1
        continue

    m_item = re.match(r"^(\s*)-\s*(.*)$", line)
    if m_item:
        flush()
        cur = {}
        item_indent = len(m_item.group(1))
        rest = m_item.group(2).strip()
        if ":" in rest:
            k, v = rest.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k in {"envKey", "default", "type"}:
                cur[k] = unquote(v)
        i += 1
        continue

    if cur is not None and item_indent is not None:
        indent = len(line) - len(line.lstrip(" \t"))
        if indent == item_indent + 2:
            m_kv = re.match(r"^\s*([A-Za-z0-9_]+):\s*(.*)$", line)
            if m_kv:
                k = m_kv.group(1)
                v = m_kv.group(2).strip()
                if k in {"envKey", "default", "type"}:
                    cur[k] = unquote(v)
                elif k == "child" and v == "":
                    # Enter child section
                    in_child = True
                    child_indent = indent + 2
                    child_cur = None

    i += 1

flush()
if child_cur and child_cur.get("envKey"):
    items.append(child_cur)

out_lines = [f"CONTAINER_NAME={container_name}"]

# Read compose variables if compose path provided
compose_vars = set()
if compose_path and compose_path.is_file():
    compose_text = compose_path.read_text(encoding='utf-8', errors='ignore')
    for raw in re.findall(r'\$\{([^}]+)\}', compose_text):
        key = raw.strip()
        key = re.split(r'[:?+\-]', key, maxsplit=1)[0].strip()
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            compose_vars.add(key)

for it in items:
    env = it.get("envKey", "").strip()
    dft = it.get("default", "")
    ftype = it.get("type", "").strip().lower()
    if env and env != "CONTAINER_NAME" and ftype not in {"apps"}:
        # If compose provided, only include variables used in compose
        if not compose_vars or env in compose_vars:
            out_lines.append(f"{env}={dft}")

out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
