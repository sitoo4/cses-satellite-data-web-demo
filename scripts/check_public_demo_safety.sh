#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

fail() {
  echo "SAFETY CHECK FAILED: $*" >&2
  exit 1
}

echo "Checking tracked raw science data files..."
tracked_raw="$(git ls-files | grep -Ei '\.(h5|hdf5|cdf|sav)$' || true)"
[[ -z "$tracked_raw" ]] || fail "raw data files are tracked: $tracked_raw"

echo "Checking demo_data raw science data files..."
demo_raw="$(find frontend/public/demo_data -type f \( -name '*.h5' -o -name '*.hdf5' -o -name '*.cdf' -o -name '*.sav' \) -print)"
[[ -z "$demo_raw" ]] || fail "raw data files found in demo_data: $demo_raw"

echo "Checking private paths and real H5 filenames..."
private_pattern="$(printf '%s%s%s%s%s%s' '/Volumes' '/Elements/HPM|' '/Users' '/foursoils|' 'CSES_01' '_HPM')"
private_hits="$(grep -R -n -E "$private_pattern" frontend/public/demo_data frontend/src README.md DEMO.md STATIC_DEMO_BUILD.md 2>/dev/null || true)"
[[ -z "$private_hits" ]] || fail "private paths or real filenames found:\n$private_hits"

echo "Checking demo_data display date sanitization..."
date_hits="$(grep -R -n -E '2023-|202304' frontend/public/demo_data 2>/dev/null || true)"
[[ -z "$date_hits" ]] || fail "unsanitized source dates found in demo_data:\n$date_hits"

echo "Checking public demo contains only CSES references..."
forbidden_pattern="$(printf '%s' 'clus' 'ter|' 'idl' 'python|' 'daily' '_full|' 'whis' 'per|' 'c1_cp|c[1-4]_cp|' 'om' 'ni')"
cses_only_hits="$(
  git grep -n -i -E "$forbidden_pattern" -- . \
    ':!frontend/package-lock.json' \
    ':!frontend/node_modules' \
    ':!frontend/dist' \
    ':!scripts/check_public_demo_safety.sh' 2>/dev/null || true
)"
[[ -z "$cses_only_hits" ]] || fail "non-CSES references found:\n$cses_only_hits"

echo "Checking static demo file sizes..."
python - <<'PY'
import json
from pathlib import Path

base = Path("frontend/public/demo_data")
limits = {
    "demo_manifest.json": 80_000,
    "demo_summary.json": 120_000,
    "magnetic_sanitized_downsampled.json": 250_000,
    "orbit_points_sanitized.json": 250_000,
    "demo_statistics.json": 180_000,
    "demo_statistics_summary.csv": 80_000,
}
for name, limit in limits.items():
    path = base / name
    if not path.exists():
        raise SystemExit(f"missing expected demo file: {name}")
    size = path.stat().st_size
    if size > limit:
        raise SystemExit(f"{name} is too large: {size} > {limit}")

magnetic = json.loads((base / "magnetic_sanitized_downsampled.json").read_text(encoding="utf-8"))
orbit = json.loads((base / "orbit_points_sanitized.json").read_text(encoding="utf-8"))
mag_points = magnetic.get("points", [])
orbit_points = orbit.get("points", [])
if not (1 <= len(mag_points) <= 600):
    raise SystemExit(f"unexpected magnetic point count: {len(mag_points)}")
if not (1 <= len(orbit_points) <= 400):
    raise SystemExit(f"unexpected orbit point count: {len(orbit_points)}")
for key in ("time_ms", "UTC_TIME", "B_FGM"):
    if key in json.dumps(magnetic, ensure_ascii=False) or key in json.dumps(orbit, ensure_ascii=False):
        raise SystemExit(f"raw-like key found in sanitized visualization JSON: {key}")
print(f"magnetic_points={len(mag_points)} orbit_points={len(orbit_points)}")
PY

echo "Public demo safety check passed."
