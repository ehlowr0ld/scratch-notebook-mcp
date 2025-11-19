#!/usr/bin/env bash
# Append or update specification mappings for a review run.
# Usage:
#   review-append-spec.sh --run_id <id> (--json '<payload>' | --file <path>)
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
Usage: review-append-spec.sh --run_id <id> (--json '<payload>' | --file <path>) [--feature-dir <path>]

Updates one or more specification sections (phases, user_stories, acceptance_criteria,
feature_modules). Entries replace existing identifiers with the same key.
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
  echo "ERROR: append payload required via --json or --file" >&2
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
  echo "ERROR: run directory missing (${RUN_DIR}). Run review-init.sh and review-import-spec.sh first." >&2
  exit 2
fi

SPEC_PATH="${RUN_DIR}/spec.json.enc"
if [[ ! -f "${SPEC_PATH}" ]]; then
  echo "ERROR: spec ledger missing (${SPEC_PATH}). Run review-import-spec.sh first." >&2
  exit 2
fi

existing_tmp="$(decrypt_artifact_to_tmp "${SPEC_PATH}")"
if [[ ! -s "${existing_tmp}" || "$(tr -d '[:space:]' < "${existing_tmp}")" == "{}" ]]; then
  rm -f "${existing_tmp}"
  echo "ERROR: cannot append before an initial import. Run review-import-spec.sh." >&2
  exit 2
fi
payload_tmp="$(mktemp)"
chmod 600 "${payload_tmp}"
printf '%s' "${JSON_PAYLOAD}" > "${payload_tmp}"

meta_tmp="$(mktemp)"
chmod 600 "${meta_tmp}"

append_tmp="$(mktemp)"
chmod 600 "${append_tmp}"

python3 - "${existing_tmp}" "${payload_tmp}" "${meta_tmp}" <<'PY' > "${append_tmp}"
import json
import sys
from pathlib import Path

existing_path = Path(sys.argv[1])
updates_path = Path(sys.argv[2])
meta_path = Path(sys.argv[3])

try:
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    sys.stderr.write(f"ERROR: stored specification payload is unreadable: {exc}\n")
    sys.exit(2)

try:
    updates = json.loads(updates_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    sys.stderr.write(f"ERROR: invalid JSON payload: {exc}\n")
    sys.exit(2)

if not isinstance(existing, dict):
    sys.stderr.write("ERROR: stored specification payload is corrupted (expected object).\n")
    sys.exit(2)

allowed_sections = {
    "phases",
    "user_stories",
    "acceptance_criteria",
    "feature_modules",
}

if not isinstance(updates, dict) or not updates:
    sys.stderr.write("ERROR: append payload must be a non-empty object.\n")
    sys.exit(2)

unsupported = [key for key in updates.keys() if key not in allowed_sections]
if unsupported:
    sys.stderr.write("ERROR: append payload contains unsupported keys: " + ", ".join(unsupported) + "\n")
    sys.exit(2)

replaced = {}
for section, value in updates.items():
    if not isinstance(value, dict) or not value:
        sys.stderr.write(f"ERROR: section '{section}' must be a non-empty object.\n")
        sys.exit(2)
    target = existing.setdefault(section, {})
    if not isinstance(target, dict):
        sys.stderr.write(f"ERROR: stored section '{section}' is corrupted (expected object).\n")
        sys.exit(2)
    for identifier, description in value.items():
        if not isinstance(identifier, str) or not identifier.strip():
            sys.stderr.write(f"ERROR: section '{section}' contains an invalid identifier '{identifier}'.\n")
            sys.exit(2)
        if not isinstance(description, str) or len(description.strip()) < 25:
            sys.stderr.write(
                f"ERROR: section '{section}' entry '{identifier}' must have a description ≥25 characters.\n"
            )
            sys.exit(2)
        identifier_norm = identifier.strip()
        if identifier_norm in target:
            replaced.setdefault(section, []).append(identifier_norm)
        target[identifier_norm] = description.strip()

canonical = json.dumps(existing, ensure_ascii=False, sort_keys=True, indent=2)
sys.stdout.write(canonical)
meta_path.write_text(json.dumps(replaced), encoding="utf-8")
PY

replace_with_encrypted_file "${append_tmp}" "${SPEC_PATH}"

replacements="$(<"${meta_tmp}")"
if [[ -n "${replacements}" && "${replacements}" != "{}" ]]; then
  python3 - <<'PY' <<<"${replacements}"
import json
import sys

replacements = json.loads(sys.stdin.read() or "{}")
if replacements:
    for section, identifiers in replacements.items():
        if identifiers:
            unique = sorted(set(identifiers))
            print(f"WARN: replaced {len(unique)} identifier(s) in section '{section}': " + ", ".join(unique))
PY
fi

rm -f "${existing_tmp}" "${payload_tmp}" "${append_tmp}" "${meta_tmp}"

echo "APPENDED specification data for run ${RUN_ID}"
