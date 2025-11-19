#!/usr/bin/env bash
# Display a progress snapshot for the streamlined review workflow.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
# shellcheck source=review-crypto.sh
source "${SCRIPT_DIR}/review-crypto.sh"

RUN_ID=""
FEATURE_DIR_ARG=""
LIMIT=10

usage() {
  cat <<'EOF' >&2
Usage: review-status.sh --run_id <id> [--feature-dir <path>] [--limit <n>]

Summarizes the current review run: spec import/validation state, counts of
changed/recorded/pending files, inspection progress, and recent recordings.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run_id) RUN_ID="$2"; shift 2;;
    --feature-dir) FEATURE_DIR_ARG="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --help|-h) usage; exit 0;;
    *) echo "ERROR: unknown arg $1" >&2; usage; exit 2;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "ERROR: --run_id is required" >&2
  usage
  exit 2
fi

if ! [[ "${LIMIT}" =~ ^[0-9]+$ && "${LIMIT}" -ge 1 ]]; then
  echo "ERROR: --limit must be a positive integer" >&2
  exit 2
fi

eval "$(get_feature_paths)"
if [[ -n "${FEATURE_DIR_ARG}" ]]; then
  FEATURE_DIR="${FEATURE_DIR_ARG}"
fi
if [[ -z "${FEATURE_DIR}" || ! -d "${FEATURE_DIR}" ]]; then
  echo "ERROR: feature directory not found; supply --feature-dir" >&2
  exit 2
fi

FEATURE_DIR="$(cd "${FEATURE_DIR}" && pwd)"
RUN_DIR="${FEATURE_DIR}/.reviews/${RUN_ID}"

if [[ ! -d "${RUN_DIR}" ]]; then
  echo "ERROR: review run directory not found (${RUN_DIR}). Run review-init.sh first." >&2
  exit 2
fi

META_PATH="${RUN_DIR}/meta.json.enc"
SPEC_PATH="${RUN_DIR}/spec.json.enc"
FILES_PATH="${RUN_DIR}/files.json.enc"

for required in "${META_PATH}" "${SPEC_PATH}" "${FILES_PATH}"; do
  if [[ ! -f "${required}" ]]; then
    echo "ERROR: missing dataset ${required}. Run review-init.sh first." >&2
    exit 2
  fi
done

meta_tmp="$(decrypt_artifact_to_tmp "${META_PATH}")"
spec_tmp="$(decrypt_artifact_to_tmp "${SPEC_PATH}")"
files_tmp="$(decrypt_artifact_to_tmp "${FILES_PATH}")"

spec_validated="false"
if [[ -f "${RUN_DIR}/.spec_validated" ]]; then
  spec_validated="true"
fi

INSPECT_DIR="${RUN_DIR}/.inspected"
mkdir -p "${INSPECT_DIR}"

python3 - <<'PY' "${meta_tmp}" "${spec_tmp}" "${files_tmp}" "${INSPECT_DIR}" "${spec_validated}" "${LIMIT}" "${RUN_ID}"
import json
import sys
from datetime import datetime
from pathlib import Path

meta_path, spec_path, files_path, inspected_dir, spec_validated, limit_str, run_id = sys.argv[1:8]
limit = int(limit_str)

def load_json(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"ERROR: unable to parse {path}: {exc}\n")
        sys.exit(2)

meta = load_json(Path(sys.argv[1]), {})
spec = load_json(Path(sys.argv[2]), {})
files = load_json(Path(sys.argv[3]), {})

feature_slug = ""
feature_dir_meta = meta.get("feature_dir")
if isinstance(feature_dir_meta, str) and feature_dir_meta:
    feature_slug = Path(feature_dir_meta).name

def is_reviewable(path: str) -> bool:
    if not isinstance(path, str):
        return False
    if feature_slug:
        prefix = f"specs/{feature_slug}/"
        if path.startswith(prefix):
            return False
    return True

changed_files_all = [entry.get("path") for entry in meta.get("changed_files", []) if entry.get("path")]
changed_files = [path for path in changed_files_all if is_reviewable(path)]
changed_set = set(changed_files)
recorded_set = {path for path in files.keys() if is_reviewable(path)}
pending = [path for path in changed_files if path not in recorded_set]
extra_records = sorted(recorded_set - changed_set)

total_candidate = 0
total_considered = 0
meets_threshold = 0
below_threshold = 0
for path in recorded_set:
    record = files.get(path, {})
    coverage = record.get("coverage") if isinstance(record, dict) else None
    if not isinstance(coverage, dict):
        continue
    candidate = coverage.get("candidate_count") or 0
    considered = coverage.get("considered_count") or 0
    status = coverage.get("status")
    if candidate and considered:
        total_candidate += candidate
        total_considered += considered
    if status == "MeetsThreshold":
        meets_threshold += 1
    elif status == "BelowThreshold":
        below_threshold += 1

inspected = set()
inspected_root = Path(inspected_dir)
if inspected_root.exists():
    for sentinel in inspected_root.glob("*"):
        try:
            lines = sentinel.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        if len(lines) >= 2:
            inspected.add(lines[1].strip())

recent_recorded = sorted(
    (
        (
            path,
            files[path].get("recorded_at"),
            files[path].get("change_description", []),
        )
        for path in recorded_set
    ),
    key=lambda item: item[1] or "",
)  # chronological

spec_name = spec.get("name") if isinstance(spec, dict) else None
spec_status = "validated" if spec_validated.lower() == "true" else "NOT VALIDATED"

print(f"Run: {run_id}")
print(f"Spec status: {spec_status}" + (f" · name: {spec_name}" if spec_name else ""))
print(f"Changed files: {len(changed_files)}")
print(f"Recorded files: {len(recorded_set)}")
print(f"Pending files: {len(pending)}")
print(f"Inspected files: {len(inspected & changed_set)} / {len(changed_files)}")
if total_candidate:
    ratio = total_considered / total_candidate if total_candidate else 0.0
    print(
        "Traceability coverage: "
        f"{total_considered}/{total_candidate} ({ratio:.0%}) "
        f"| Meets: {meets_threshold} | Below: {below_threshold}"
    )

if pending:
    print("\nPending files (next {}):".format(min(limit, len(pending))))
    for path in pending[:limit]:
        marker = "" if path in inspected else " [not inspected]"
        print(f" - {path}{marker}")

if extra_records:
    print("\n⚠ Records exist for files outside the diff range:")
    for path in extra_records:
        print(f" - {path}")

if recent_recorded:
    tail = recent_recorded[-limit:]
    print("\nRecently recorded files (most recent last):")
    for path, recorded_at, changes in tail:
        human_time = recorded_at or "unknown"
        summary = "; ".join(changes) if changes else ""
        preview = summary.replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        suffix = f" :: {preview}" if preview else ""
        print(f" - {path} ({human_time}){suffix}")

if not changed_files:
    print("\nNote: No files detected between base/head commits in this run.")

print("\nTip: rerun review-status periodically to monitor pending files and confirm spec validation before synthesis.")
PY

rm -f "${meta_tmp}" "${spec_tmp}" "${files_tmp}"
