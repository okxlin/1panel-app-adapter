#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-}"
[[ -n "$IMAGE" ]] || { echo "usage: detect_architectures.sh <image>" >&2; exit 2; }
TMP_MANIFEST="$(mktemp /tmp/manifest.XXXXXX.json 2>/dev/null || mktemp 2>/dev/null || true)"
[[ -n "$TMP_MANIFEST" ]] || { echo "amd64"; exit 0; }
trap 'rm -f "$TMP_MANIFEST"' EXIT

if command -v docker >/dev/null 2>&1; then
  if docker manifest inspect "$IMAGE" >"$TMP_MANIFEST" 2>/dev/null; then
    if command -v python3 >/dev/null 2>&1; then
      python3 - "$TMP_MANIFEST" <<'PY'
import json
import sys
m=json.load(open(sys.argv[1],'r',encoding='utf-8',errors='ignore'))
arches=set()
if isinstance(m,dict):
  if 'manifests' in m and isinstance(m['manifests'],list):
    for it in m['manifests']:
      plat=(it or {}).get('platform') or {}
      arch=plat.get('architecture')
      variant=plat.get('variant')
      if arch:
        if arch=='arm' and variant:
          arches.add(variant)
        else:
          arches.add(arch)
  else:
    arch=m.get('architecture')
    if arch:
      arches.add(arch)

mapped=[]
for a in sorted(arches):
  if a in ('amd64','x86_64'): mapped.append('amd64')
  elif a in ('arm64','aarch64'): mapped.append('arm64')
  elif a in ('ppc64le',): mapped.append('ppc64le')
  elif a in ('riscv64',): mapped.append('riscv64')
  elif a in ('loong64',): mapped.append('loong64')
  elif a in ('s390x',): mapped.append('s390x')
  elif a in ('armv6','v6'): mapped.append('armv6')
  elif a in ('armv7','v7'): mapped.append('armv7')

out=[]
for x in mapped:
  if x not in out:
    out.append(x)
print("\n".join(out))
PY
      exit 0
    fi
  fi
fi

echo "amd64"
