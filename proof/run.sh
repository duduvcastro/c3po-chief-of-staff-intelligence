#!/bin/bash
# Prova Linux descartável do binder rev8 (pacote 9f5fc99c…): extrai, sela antes/depois, roda o recorte pedido pelo Codex.
set -u
PY="$1"; TAG="$2"; OUT="$GITHUB_WORKSPACE/out/$TAG"; mkdir -p "$OUT"
echo "9f5fc99c44fa0e605398f6e6f93ad1ac1d7d3dddfbeab0f11e2dfd1fbc2e3a19  proof/BINDER_REV8_LINUX_CANDIDATE.tar.gz" | sha256sum -c - > "$OUT/archive_check.txt" || { echo ARCHIVE_HASH_MISMATCH; exit 1; }
X=$(mktemp -d); tar xzf proof/BINDER_REV8_LINUX_CANDIDATE.tar.gz -C "$X" || exit 1
( cd "$X" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$OUT/manifest_before.txt"
cd "$X/binder" || exit 1
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/utc_start.txt"
"$PY" -c 'import sys,platform,importlib.metadata as m;print(sys.version);print(platform.platform());[print(d.metadata["Name"],d.version) for d in sorted(m.distributions(),key=lambda d:d.metadata["Name"].lower())]' > "$OUT/versions.txt"
BIND_TEST_K8_CONFIG="$PWD/bind/k8_verifier/c3po/backend/app/config.py" "$PY" -B run_candidate_tests.py --portable-rev8 -k 'not bootstrap and (k8 or k9 or dated_amendment4)' > "$OUT/tests.log" 2>&1
RC=$?; echo "$RC" > "$OUT/exit.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/utc_end.txt"
( cd "$X" && find . -type f -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 | sort -z | xargs -0 sha256sum ) > "$OUT/manifest_after.txt"
grep -vE '__pycache__|\.pytest_cache' "$OUT/manifest_before.txt" > "$OUT/mb.txt"; diff "$OUT/mb.txt" "$OUT/manifest_after.txt" > "$OUT/manifest_diff.txt"; echo "manifest_diff_exit=$?" >> "$OUT/exit.txt"
tail -5 "$OUT/tests.log"; cat "$OUT/exit.txt"
exit $RC
