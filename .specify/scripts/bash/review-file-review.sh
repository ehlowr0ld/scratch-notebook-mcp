#!/usr/bin/env bash
# Record per-file review data using a JSON batch payload.
# Usage:
#   review-file-review.sh --run_id <id> (--json '<payload>' | --file <path>)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
# shellcheck source=review-crypto.sh
source "${SCRIPT_DIR}/review-crypto.sh"

RUN_ID=""
FEATURE_DIR_ARG=""
JSON_PAYLOAD=""
JSON_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run_id) RUN_ID="$2"; shift 2;;
    --feature-dir) FEATURE_DIR_ARG="$2"; shift 2;;
    --json) JSON_PAYLOAD="$2"; shift 2;;
    --file) JSON_FILE="$2"; shift 2;;
    --help|-h)
      cat <<'EOF'
Usage: review-file-review.sh --run_id <id> (--json '<payload>' | --file <path>) [--feature-dir <path>]

Writes file review records for the specified run. The payload must follow the
File Review Batch schema (see spec). Re-sending a file replaces its record.
EOF
      exit 0;;
    *) echo "ERROR: unknown arg $1" >&2; exit 2;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "ERROR: --run_id is required" >&2
  exit 2
fi

if [[ -n "${JSON_PAYLOAD}" && -n "${JSON_FILE}" ]]; then
  echo "ERROR: supply either --json or --file, not both" >&2
  exit 2
fi

if [[ -z "${JSON_PAYLOAD}" && -z "${JSON_FILE}" ]]; then
  echo "ERROR: review payload required via --json or --file" >&2
  exit 2
fi

if [[ -n "${JSON_FILE}" ]]; then
  if [[ ! -f "${JSON_FILE}" ]]; then
    echo "ERROR: JSON file not found: ${JSON_FILE}" >&2
    exit 2
  fi
  JSON_PAYLOAD="$(<"${JSON_FILE}")"
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

if [[ ! -f "${RUN_DIR}/.spec_validated" ]]; then
  echo "ERROR: specification has not been validated. Run review-spec-validate.sh first." >&2
  exit 2
fi

META_PATH="${RUN_DIR}/meta.json.enc"
FILES_PATH="${RUN_DIR}/files.json.enc"
if [[ ! -f "${META_PATH}" || ! -f "${FILES_PATH}" ]]; then
  echo "ERROR: review run is missing meta or files dataset. Run review-init.sh first." >&2
  exit 2
fi

meta_tmp="$(decrypt_artifact_to_tmp "${META_PATH}")"
files_tmp="$(decrypt_artifact_to_tmp "${FILES_PATH}")"

payload_tmp="$(mktemp)"
chmod 600 "${payload_tmp}"
printf '%s' "${JSON_PAYLOAD}" > "${payload_tmp}"

output_tmp="$(mktemp)"
chmod 600 "${output_tmp}"

meta_out="$(mktemp)"
chmod 600 "${meta_out}"

cleanup() {
  rm -f "${meta_tmp}" "${files_tmp}" "${payload_tmp}" "${output_tmp}" "${meta_out}"
}
trap cleanup EXIT

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

python3 "${SCRIPT_DIR}/../python/review_file_review.py" \
  --meta "${meta_tmp}" \
  --existing "${files_tmp}" \
  --payload "${payload_tmp}" \
  --meta-out "${meta_out}" \
  --output "${output_tmp}"

# Verify diff inspection sentinel exists for each recorded file
recorded_list=$(python3 -c '
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else "[]"
paths = json.loads(text or "[]")
print("\n".join(paths))
' "${meta_out}")

if [[ -n "${recorded_list}" ]]; then
  while IFS= read -r recorded; do
    [[ -z "${recorded}" ]] && continue
    readarray -t FP < <(fingerprint_path "${recorded}")
    slug="${FP[1]:-}"
    if [[ -z "${slug}" || ! -f "${INSPECT_DIR}/${slug}" ]]; then
      echo "ERROR: file '${recorded}' has not been inspected yet. Run review-file-inspect.sh first." >&2
      exit 2
    fi
  done <<< "${recorded_list}"
fi

replace_with_encrypted_file "${output_tmp}" "${FILES_PATH}"

record_summary="$(<"${meta_out}")"
python3 -c '
import json
import sys
paths = json.loads(sys.stdin.read() or "[]")
if paths:
    print("RECORDED:")
    for path in paths:
        print(f" - {path}")
else:
    print("WARN: payload contained no records")
' <<<"${record_summary}"
trap - EXIT
cleanup
