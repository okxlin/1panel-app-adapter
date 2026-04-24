#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def usage():
    print("usage: gen_env_sample.py <version-data.yml> <out-.env.sample>", file=sys.stderr)


if len(sys.argv) != 3:
    usage()
    sys.exit(2)

src = Path(sys.argv[1])
out = Path(sys.argv[2])
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


i = 0
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
            if k in {"envKey", "default"}:
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
                if k in {"envKey", "default"}:
                    cur[k] = unquote(v)

    i += 1

flush()

out_lines = []
for it in items:
    env = it.get("envKey", "").strip()
    dft = it.get("default", "")
    if env:
        out_lines.append(f"{env}={dft}")

out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
