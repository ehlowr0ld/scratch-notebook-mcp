#!/usr/bin/env bash
# Import canonical specification data for a review run.
# Usage:
#   review-import-spec.sh --run_id <id> (--json '<payload>' | --file <path>)
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
Usage: review-import-spec.sh --run_id <id> (--json '<payload>' | --file <path>) [--feature-dir <path>]

Imports the canonical specification payload for the supplied run. The payload
must satisfy the Spec Import JSON Schema (see documentation). Re-importing a
payload overwrites the previous data and resets validation status.
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
  echo "ERROR: specification payload required via --json or --file" >&2
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

SPEC_PATH="${RUN_DIR}/spec.json.enc"
if [[ ! -f "${SPEC_PATH}" ]]; then
  echo "ERROR: spec ledger missing (${SPEC_PATH}). Run review-init.sh first." >&2
  exit 2
fi

validated_tmp="$(mktemp)"
chmod 600 "${validated_tmp}"
export SPEC_IMPORT_PAYLOAD="${JSON_PAYLOAD}"
python3 - <<'PY' > "${validated_tmp}"
import json
import os
import sys

payload_raw = os.environ.get("SPEC_IMPORT_PAYLOAD", "")

try:
    payload = json.loads(payload_raw)
except json.JSONDecodeError as exc:
    sys.stderr.write(f"ERROR: invalid JSON payload: {exc}\n")
    sys.exit(2)

required_keys = [
    "name",
    "overview",
    "details",
    "phases",
    "user_stories",
    "acceptance_criteria",
    "feature_modules",
]

if not isinstance(payload, dict):
    sys.stderr.write("ERROR: payload must be a JSON object.\n")
    sys.exit(2)

extra_keys = [key for key in payload.keys() if key not in required_keys]
missing_keys = [key for key in required_keys if key not in payload]
if missing_keys:
    sys.stderr.write("ERROR: payload missing keys: " + ", ".join(missing_keys) + "\n")
    sys.exit(2)
if extra_keys:
    sys.stderr.write("ERROR: payload contains unsupported keys: " + ", ".join(extra_keys) + "\n")
    sys.exit(2)

def ensure_string(key: str, min_len: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        sys.stderr.write(f"ERROR: '{key}' must be a string.\n")
        sys.exit(2)
    if len(value.strip()) < min_len:
        sys.stderr.write(f"ERROR: '{key}' must be at least {min_len} characters.\n")
        sys.exit(2)
    return value.strip()

def ensure_mapping(key: str) -> dict:
    value = payload.get(key)
    if not isinstance(value, dict) or not value:
        sys.stderr.write(f"ERROR: '{key}' must be a non-empty object.\n")
        sys.exit(2)
    cleaned = {}
    for identifier, description in value.items():
        if not isinstance(identifier, str) or not identifier.strip():
            sys.stderr.write(f"ERROR: '{key}' contains an invalid identifier '{identifier}'.\n")
            sys.exit(2)
        if not isinstance(description, str) or len(description.strip()) < 25:
            sys.stderr.write(
                f"ERROR: '{key}' entry '{identifier}' must have a description ≥25 characters.\n"
            )
            sys.exit(2)
        cleaned[identifier.strip()] = description.strip()
    return cleaned

ensure_string("name", 3)
ensure_string("overview", 25)
ensure_string("details", 25)
for section in ("phases", "user_stories", "acceptance_criteria", "feature_modules"):
    ensure_mapping(section)

canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
sys.stdout.write(canonical)
PY

replace_with_encrypted_file "${validated_tmp}" "${SPEC_PATH}"
rm -f "${validated_tmp}"
rm -f "${RUN_DIR}/.spec_validated"

echo "IMPORTED specification payload for run ${RUN_ID}"
