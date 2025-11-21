#!/usr/bin/env bash
# Initialize a streamlined review workspace for a given run identifier.
# Usage:
#   review-init.sh --run_id <id> [--feature-dir <path>] [--base <sha>] [--head <sha>] [--branch <name>] [--force]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
# shellcheck source=review-crypto.sh
source "${SCRIPT_DIR}/review-crypto.sh"

require_binary git
require_binary openssl

RUN_ID=""
FEATURE_DIR_ARG=""
BASE=""
HEAD=""
BRANCH=""
FORCE=false

ensure_encryption_key() {
  local repo_root key_path key_dir
  repo_root="$(get_repo_root)"
  key_path="${SPECKIT_REVIEW_KEY_FILE:-${repo_root}/.specify/secret/review-key}"
  key_dir="$(dirname "${key_path}")"
  mkdir -p "${key_dir}"
  if [[ ! -f "${key_path}" ]]; then
    local old_umask
    old_umask="$(umask)"
    umask 077
    openssl rand -hex 32 > "${key_path}"
    chmod 600 "${key_path}"
    umask "${old_umask}"
    echo "INFO: generated review encryption key at ${key_path}" >&2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run_id) RUN_ID="$2"; shift 2;;
    --feature-dir) FEATURE_DIR_ARG="$2"; shift 2;;
    --base) BASE="$2"; shift 2;;
    --head) HEAD="$2"; shift 2;;
    --branch) BRANCH="$2"; shift 2;;
    --force) FORCE=true; shift;;
    --help|-h)
      cat <<'EOF'
Usage: review-init.sh --run_id <id> [--feature-dir <path>] [--base <sha>] [--head <sha>] [--branch <name>] [--force]

Initializes the review workspace for the supplied run identifier. Creates
encrypted metadata/spec/review ledgers and prepares the run directory.
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

ensure_encryption_key

if [[ -n "${FEATURE_DIR_ARG}" ]]; then
  FEATURE_DIR="${FEATURE_DIR_ARG}"
fi

if [[ -z "${FEATURE_DIR}" ]]; then
  echo "ERROR: unable to determine feature directory; supply --feature-dir" >&2
  exit 2
fi

if [[ ! -d "${FEATURE_DIR}" ]]; then
  echo "ERROR: feature directory not found: ${FEATURE_DIR}" >&2
  exit 2
fi

FEATURE_DIR="$(cd "${FEATURE_DIR}" && pwd)"

resolve_commit() {
  local ref="$1"
  # Allow the Git empty tree SHA for full-history reviews
  if [[ "${ref}" == "4b825dc642cb6eb9a060e54bf8d69288fbee4904" ]]; then
    echo "${ref}"
    return 0
  fi

  if ! git rev-parse --verify "${ref}^{commit}" >/dev/null 2>&1; then
    echo "ERROR: unable to resolve commit for '${ref}'" >&2
    exit 2
  fi
  git rev-parse "${ref}^{commit}"
}

if [[ -z "${BRANCH}" ]]; then
  if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  else
    BRANCH="${CURRENT_BRANCH}"
  fi
fi

local_head="$(resolve_commit HEAD)"
if [[ -z "${HEAD}" ]]; then
  HEAD="${local_head}"
else
  HEAD="$(resolve_commit "${HEAD}")"
fi

if [[ -z "${BASE}" ]]; then
  if git rev-parse --verify "origin/${BRANCH}" >/dev/null 2>&1; then
    BASE="$(resolve_commit "origin/${BRANCH}")"
  else
    BASE="$(git merge-base "${HEAD}" "origin/${BRANCH}" 2>/dev/null || git rev-parse "${HEAD}^" 2>/dev/null || printf '%s' "${HEAD}")"
  fi
else
  BASE="$(resolve_commit "${BASE}")"
fi

BASE="$(resolve_commit "${BASE}")"

RUN_ROOT="${FEATURE_DIR}/.reviews"
RUN_DIR="${RUN_ROOT}/${RUN_ID}"

if [[ -d "${RUN_DIR}" ]]; then
  if [[ "${FORCE}" != true ]]; then
    echo "ERROR: run ${RUN_ID} already exists; rerun with --force to overwrite" >&2
    exit 2
  fi
  rm -rf "${RUN_DIR}"
fi

mkdir -p "${RUN_DIR}"
mkdir -p "${RUN_DIR}/.inspected"

collect_changed_files() {
  python3 - "$@" <<'PY'
import json
import subprocess
import sys

base, head = sys.argv[1:3]
try:
    raw = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        stderr=subprocess.DEVNULL,
        text=True,
    )
except subprocess.CalledProcessError:
    raw = ""

paths = [line.strip() for line in raw.splitlines() if line.strip()]

def hunk_count(path: str) -> int:
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--no-color", "--unified=0", f"{base}..{head}", "--", path],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        return 0
    return sum(1 for line in diff.splitlines() if line.startswith("@@"))

records = [
    {
        "path": path,
        "hunk_count": hunk_count(path),
    }
    for path in paths
]

print(json.dumps(records, ensure_ascii=False))
PY
}

changed_files_json="$(collect_changed_files "${BASE}" "${HEAD}")"
DIFF_STATS="$(git diff --shortstat "${BASE}..${HEAD}" || true)"

meta_tmp="$(mktemp)"
chmod 600 "${meta_tmp}"
RUN_ID_ENV="${RUN_ID}"
FEATURE_DIR_ENV="${FEATURE_DIR}"
BRANCH_ENV="${BRANCH}"
BASE_ENV="${BASE}"
HEAD_ENV="${HEAD}"
export RUN_ID_ENV FEATURE_DIR_ENV BRANCH_ENV BASE_ENV HEAD_ENV
export DIFF_STATS_ENV="${DIFF_STATS}"
export CHANGED_FILES_ENV="${changed_files_json}"
python3 - "${meta_tmp}" <<'PY'
import json
import os
import sys
from datetime import datetime

tmp_path = sys.argv[1]
meta = {
    "run_id": os.environ["RUN_ID_ENV"],
    "feature_dir": os.environ["FEATURE_DIR_ENV"],
    "branch": os.environ["BRANCH_ENV"],
    "base": os.environ["BASE_ENV"],
    "head": os.environ["HEAD_ENV"],
    "diff_stats": os.environ.get("DIFF_STATS_ENV", ""),
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "changed_files": json.loads(os.environ["CHANGED_FILES_ENV"]),
}
meta["changed_files_count"] = len(meta["changed_files"])

with open(tmp_path, "w", encoding="utf-8") as handle:
    json.dump(meta, handle, ensure_ascii=False, indent=2)
PY

replace_with_encrypted_file "${meta_tmp}" "${RUN_DIR}/meta.json.enc"
rm -f "${meta_tmp}"

write_encrypted_json '{}' "${RUN_DIR}/spec.json.enc"
write_encrypted_json '{}' "${RUN_DIR}/files.json.enc"
rm -f "${RUN_DIR}/.spec_validated"

printf 'RUN_DIR=%s\n' "${RUN_DIR}"
printf 'REPORT=%s/report.md\n' "${RUN_DIR}"
echo "FILE_ROSTER:"
python3 - "${changed_files_json}" <<'PY'
import json
import sys

records = json.loads(sys.argv[1])
if not records:
    print("- (no changes detected)")
else:
    for record in records:
        path = record.get("path")
        hunks = record.get("hunk_count", 0)
        print(f"- {path} (hunks={hunks})")
PY
