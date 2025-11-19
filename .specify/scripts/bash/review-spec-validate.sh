#!/usr/bin/env bash
# Validate imported specification data for a review run.
# Usage:
#   review-spec-validate.sh --run_id <id> [--feature-dir <path>]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
# shellcheck source=review-crypto.sh
source "${SCRIPT_DIR}/review-crypto.sh"

RUN_ID=""
FEATURE_DIR_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run_id) RUN_ID="$2"; shift 2;;
    --feature-dir) FEATURE_DIR_ARG="$2"; shift 2;;
    --help|-h)
      cat <<'EOF'
Usage: review-spec-validate.sh --run_id <id> [--feature-dir <path>]

Validates that the imported specification payload satisfies minimum structure and
length requirements. Sets a sentinel file on success.
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

SPEC_PATH="${RUN_DIR}/spec.json.enc"
if [[ ! -f "${SPEC_PATH}" ]]; then
  echo "ERROR: spec ledger missing (${SPEC_PATH}). Run review-import-spec.sh first." >&2
  exit 2
fi

spec_tmp="$(decrypt_artifact_to_tmp "${SPEC_PATH}")"
spec_overview="${RUN_DIR}/spec-overview.md"

python3 - "${spec_tmp}" "${spec_overview}" <<'PY'
import json
import sys
from pathlib import Path
from textwrap import fill

spec_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
try:
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    sys.stderr.write(f"ERROR: unable to read specification payload: {exc}\n")
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
    sys.stderr.write("ERROR: specification payload is corrupted (expected object).\n")
    sys.exit(2)

missing = [key for key in required_keys if key not in payload]
if missing:
    sys.stderr.write("ERROR: specification payload missing keys: " + ", ".join(missing) + "\n")
    sys.exit(2)

def ensure_string(key: str, min_len: int) -> None:
    value = payload.get(key)
    if not isinstance(value, str):
        sys.stderr.write(f"ERROR: '{key}' must be a string.\n")
        sys.exit(2)
    if len(value.strip()) < min_len:
        sys.stderr.write(f"ERROR: '{key}' must be at least {min_len} characters.\n")
        sys.exit(2)

def ensure_mapping(key: str) -> None:
    section = payload.get(key)
    if not isinstance(section, dict) or not section:
        sys.stderr.write(f"ERROR: '{key}' must be a non-empty object.\n")
        sys.exit(2)
    for identifier, description in section.items():
        if not isinstance(identifier, str) or not identifier.strip():
            sys.stderr.write(f"ERROR: '{key}' contains an invalid identifier '{identifier}'.\n")
            sys.exit(2)
        if not isinstance(description, str) or len(description.strip()) < 25:
            sys.stderr.write(
                f"ERROR: '{key}' entry '{identifier}' must have a description ≥25 characters.\n"
            )
            sys.exit(2)

ensure_string("name", 3)
ensure_string("overview", 25)
ensure_string("details", 25)
for section in ("phases", "user_stories", "acceptance_criteria", "feature_modules"):
    ensure_mapping(section)

def compact(text: str) -> str:
    return " ".join(text.strip().split()) if isinstance(text, str) else ""

lines = [
    "# Specification Overview",
    "",
    f"- **Name:** {compact(payload['name'])}",
    f"- **Overview:** {compact(payload['overview'])}",
    f"- **Details:** {compact(payload['details'])}",
    "",
]

for section_key, title in (
    ("phases", "Phases"),
    ("user_stories", "User Stories"),
    ("acceptance_criteria", "Acceptance Criteria"),
    ("feature_modules", "Feature Modules"),
):
    items = payload.get(section_key, {})
    lines.append(f"## {title}")
    if items:
        for identifier in sorted(items.keys(), key=lambda s: s.casefold()):
            desc = compact(items[identifier])
            lines.append(f"- `{identifier}`: {desc}")
    else:
        lines.append("- _None recorded_")
    lines.append("")

try:
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
except OSError as exc:
    sys.stderr.write(f"ERROR: unable to write specification overview: {exc}\n")
    sys.exit(2)
PY

rm -f "${spec_tmp}"

printf '%s' "validated $(date -Is)" > "${RUN_DIR}/.spec_validated"

echo "VALIDATED specification payload for run ${RUN_ID}"
