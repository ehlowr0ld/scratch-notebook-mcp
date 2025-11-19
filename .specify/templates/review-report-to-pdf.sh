#!/usr/bin/env bash
# Generate report.pdf from report.md using pandoc + wkhtmltopdf.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPORT_MD="${SCRIPT_DIR}/report.md"
REPORT_CSS="${SCRIPT_DIR}/report.css"
REPORT_PDF="${SCRIPT_DIR}/report.pdf"

if [[ ! -f "${REPORT_MD}" ]]; then
  echo "ERROR: report.md not found at ${REPORT_MD}" >&2
  exit 2
fi

if [[ ! -f "${REPORT_CSS}" ]]; then
  echo "ERROR: report.css not found at ${REPORT_CSS}" >&2
  exit 2
fi

if ! command -v pandoc >/dev/null 2>&1; then
  echo "ERROR: pandoc is required but not found in PATH" >&2
  exit 2
fi

if ! command -v wkhtmltopdf >/dev/null 2>&1; then
  echo "ERROR: wkhtmltopdf is required but not found in PATH" >&2
  exit 2
fi

pandoc "${REPORT_MD}" \
  --from markdown+pipe_tables+gfm_auto_identifiers \
  --to html5 \
  --css "${REPORT_CSS}" \
  --pdf-engine=wkhtmltopdf \
  --metadata pagetitle="Review Report" \
  --pdf-engine-opt=--page-size \
  --pdf-engine-opt=A4 \
  --pdf-engine-opt=--disable-smart-shrinking \
  --pdf-engine-opt=--margin-top \
  --pdf-engine-opt=1cm \
  --pdf-engine-opt=--margin-bottom \
  --pdf-engine-opt=1cm \
  --pdf-engine-opt=--margin-left \
  --pdf-engine-opt=1cm \
  --pdf-engine-opt=--margin-right \
  --pdf-engine-opt=1cm \
  --standalone \
  -o "${REPORT_PDF}"

echo "Wrote ${REPORT_PDF}"
