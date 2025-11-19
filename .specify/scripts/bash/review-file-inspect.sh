#!/usr/bin/env bash
# Display diffs for one or more files in the current review run.
# Usage:
#   review-file-inspect.sh --run_id <id> [--path <file> ...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
# shellcheck source=review-crypto.sh
source "${SCRIPT_DIR}/review-crypto.sh"

RUN_ID=""
FEATURE_DIR_ARG=""
declare -a SELECTED_PATHS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run_id) RUN_ID="$2"; shift 2;;
    --feature-dir) FEATURE_DIR_ARG="$2"; shift 2;;
    --path) SELECTED_PATHS+=("$2"); shift 2;;
    --help|-h)
      cat <<'EOF'
Usage: review-file-inspect.sh --run_id <id> [--path <file> ...] [--feature-dir <path>]

Shows unified diffs for the chosen files (default: all files in the run).
Records an inspection sentinel so review-file-review.sh can enforce
“inspect before record”.
EOF
      exit 0;;
    *) echo "ERROR: unknown arg $1" >&2; exit 2;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "ERROR: --run_id is required" >&2
  exit 2
fi

eval "$(get_feature_paths)"
REPO_ROOT="${REPO_ROOT:-$(get_repo_root)}"
cd "${REPO_ROOT}"

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
  echo "ERROR: run directory missing (${RUN_DIR}). Run review-init.sh first." >&2
  exit 2
fi

META_PATH="${RUN_DIR}/meta.json.enc"
if [[ ! -f "${META_PATH}" ]]; then
  echo "ERROR: meta.json.enc missing. Run review-init.sh first." >&2
  exit 2
fi

meta_tmp="$(decrypt_artifact_to_tmp "${META_PATH}")"
trap 'rm -f "${meta_tmp}"' EXIT

readarray -t META_VALUES < <(python3 - "${meta_tmp}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    meta = json.load(handle)

base = meta.get("base") or ""
head = meta.get("head") or ""
files = [entry.get("path") for entry in meta.get("changed_files", []) if entry.get("path")]

print(base)
print(head)
print(json.dumps(files))
PY
)

BASE_COMMIT="${META_VALUES[0]}"
HEAD_COMMIT="${META_VALUES[1]}"
CHANGED_FILES_JSON="${META_VALUES[2]}"

if [[ -z "${BASE_COMMIT}" || -z "${HEAD_COMMIT}" ]]; then
  echo "ERROR: meta is missing base/head commit information." >&2
  exit 2
fi

if [[ ${#SELECTED_PATHS[@]} -eq 0 ]]; then
  mapfile -t SELECTED_PATHS < <(python3 -c 'import json,sys; print("\n".join(json.loads(sys.argv[1])))' "${CHANGED_FILES_JSON}")
fi

if [[ ${#SELECTED_PATHS[@]} -eq 0 ]]; then
  echo "WARN: no files to inspect (change list empty)" >&2
  exit 0
fi

INSPECT_DIR="${RUN_DIR}/.inspected"
mkdir -p "${INSPECT_DIR}"

fingerprint_path() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

raw = sys.argv[1]
norm = pathlib.PurePosixPath(raw).as_posix()
if norm.startswith("./"):
    norm = norm[2:]
print(norm)
print(hashlib.sha256(norm.encode("utf-8")).hexdigest())
PY
}

for path in "${SELECTED_PATHS[@]}"; do
  echo "===== ${path} ====="
  if ! git diff --no-color "${BASE_COMMIT}..${HEAD_COMMIT}" -- "${path}"; then
    echo "(no diff or file missing in range)" >&2
    continue
  fi
  readarray -t FP < <(fingerprint_path "${path}")
  normalized_path="${FP[0]:-}"
  slug="${FP[1]:-}"
  if [[ -n "${slug}" ]]; then
    {
      date -Iseconds
      printf '%s\n' "${normalized_path:-${path}}"
    } > "${INSPECT_DIR}/${slug}"
  fi
  echo
done


