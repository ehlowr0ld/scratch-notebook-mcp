#!/usr/bin/env bash
# Generate the streamlined review report from recorded JSON datasets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
# shellcheck source=review-crypto.sh
source "${SCRIPT_DIR}/review-crypto.sh"

RUN_ID=""
FEATURE_DIR_ARG=""
LAYOUT="vertical"
FORCE=false

usage() {
  cat <<'EOF' >&2
Usage: review-report-synthesize.sh --run_id <id> [--feature-dir <path>] [--layout vertical|tabular] [--force]

Rewrites report.md for the given run using the streamlined JSON datasets. The
generated report overwrites manual edits—fill in the MANUAL_* placeholders
after running this script.

Options:
  --force               Generate a partial report even if pending files remain.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run_id) RUN_ID="$2"; shift 2;;
    --feature-dir) FEATURE_DIR_ARG="$2"; shift 2;;
    --layout) LAYOUT="$2"; shift 2;;
    --force) FORCE=true; shift;;
    --help|-h) usage; exit 0;;
    *) echo "ERROR: unknown arg $1" >&2; usage; exit 2;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "ERROR: --run_id is required" >&2
  usage
  exit 2
fi

if [[ "${LAYOUT}" != "vertical" && "${LAYOUT}" != "tabular" ]]; then
  echo "ERROR: --layout must be 'vertical' or 'tabular'" >&2
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
  echo "ERROR: run directory not found (${RUN_DIR}). Run review-init.sh first." >&2
  exit 2
fi

META_PATH="${RUN_DIR}/meta.json.enc"
SPEC_PATH="${RUN_DIR}/spec.json.enc"
FILES_PATH="${RUN_DIR}/files.json.enc"
TEMPLATE_PATH="${SCRIPT_DIR}/../../templates/review-report-template.md"
TEMPLATE_CSS_PATH="${SCRIPT_DIR}/../../templates/review-report.css"
TEMPLATE_PDF_PATH="${SCRIPT_DIR}/../../templates/review-report-to-pdf.sh"
REPORT_PATH="${RUN_DIR}/report.md"

for required in "${META_PATH}" "${SPEC_PATH}" "${FILES_PATH}" "${TEMPLATE_PATH}"; do
  if [[ ! -f "${required}" ]]; then
    echo "ERROR: missing required file (${required})" >&2
    exit 2
  fi
done

if [[ -f "${TEMPLATE_CSS_PATH}" ]]; then
  cp "${TEMPLATE_CSS_PATH}" "${RUN_DIR}/report.css"
fi

if [[ -f "${TEMPLATE_PDF_PATH}" ]]; then
  cp "${TEMPLATE_PDF_PATH}" "${RUN_DIR}/report-to-pdf.sh"
  chmod +x "${RUN_DIR}/report-to-pdf.sh"
fi

meta_tmp="$(decrypt_artifact_to_tmp "${META_PATH}")"
spec_tmp="$(decrypt_artifact_to_tmp "${SPEC_PATH}")"
files_tmp="$(decrypt_artifact_to_tmp "${FILES_PATH}")"

cleanup() {
  rm -f "${meta_tmp}" "${spec_tmp}" "${files_tmp}" "${report_tmp}"
}
trap cleanup EXIT

report_tmp="$(mktemp)"

python3 - "${TEMPLATE_PATH}" "${meta_tmp}" "${spec_tmp}" "${files_tmp}" "${RUN_DIR}/.inspected" "${LAYOUT}" "${RUN_ID}" "${FORCE}" "${report_tmp}" <<'PY'
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter

template_path = Path(sys.argv[1])
meta_path = Path(sys.argv[2])
spec_path = Path(sys.argv[3])
files_path = Path(sys.argv[4])
inspected_dir = Path(sys.argv[5])
layout = sys.argv[6]
run_id = sys.argv[7]
force_flag = sys.argv[8].lower() == "true"
output_path = Path(sys.argv[9])

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

meta = load_json(meta_path, {})
spec = load_json(spec_path, {})
files = load_json(files_path, {})

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
review_records = {path: record for path, record in files.items() if is_reviewable(path)}
recorded_set = set(review_records.keys())
pending = [path for path in changed_files if path not in recorded_set]

required_spec_keys = {"name", "overview", "details", "feature_modules"}
missing_spec = [key for key in required_spec_keys if key not in spec]
if missing_spec:
    sys.stderr.write(
        "ERROR: specification payload is incomplete. "
        "Import and validate the specification before synthesizing the report.\n"
    )
    sys.exit(2)

if not isinstance(spec.get("feature_modules"), dict) or not spec["feature_modules"]:
    sys.stderr.write(
        "ERROR: specification payload lacks feature module mappings. "
        "Append or validate feature_modules before synthesizing the report.\n"
    )
    sys.exit(2)

if pending and not force_flag:
    sys.stderr.write(
        "ERROR: Pending files remain. Complete the review loop or rerun with --force to generate a partial report.\n"
    )
    sys.exit(2)

inspected = set()
if inspected_dir.exists():
    for sentinel in inspected_dir.glob("*"):
        try:
            lines = sentinel.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        if len(lines) >= 2:
            inspected.add(lines[1].strip())

def escape(text: str) -> str:
    if not isinstance(text, str):
        return text
    return text.replace("|", "&#124;").replace("\n", "<br>")

def format_coverage_line(record: dict) -> str:
    coverage = record.get("coverage") or {}
    candidate = coverage.get("candidate_count")
    considered = coverage.get("considered_count")
    threshold = coverage.get("threshold")
    status = coverage.get("status") or "Unknown"
    if not candidate or not considered or threshold is None:
        return "Coverage: data incomplete"
    ratio = considered / candidate if candidate else 0.0
    status_html = escape(status)
    return (
        f"Coverage: {considered}/{candidate} ({ratio:.0%}) · "
        f"threshold {threshold:.2f} → **{status_html}**"
    )

def overall_coverage_summary(records: dict[str, dict]) -> str:
    total_candidate = 0
    total_considered = 0
    meets = 0
    below = 0
    for record in records.values():
        coverage = record.get("coverage") or {}
        candidate = coverage.get("candidate_count") or 0
        considered = coverage.get("considered_count") or 0
        status = coverage.get("status")
        total_candidate += candidate
        total_considered += considered
        if status == "MeetsThreshold":
            meets += 1
        elif status == "BelowThreshold":
            below += 1
    if total_candidate == 0:
        return "Coverage data pending"
    ratio = total_considered / total_candidate
    parts = [
        f"{total_considered}/{total_candidate} overall ({ratio:.0%})",
        f"records meeting threshold: {meets}",
        f"below threshold: {below}",
    ]
    return " · ".join(parts)

def format_traceability_entries(record: dict) -> str:
    trace_links = record.get("trace_links") or []
    if not trace_links:
        return "—"
    entries = []
    for link in trace_links:
        link_id = escape(link.get("id") or "UNKNOWN")
        roles = ", ".join(link.get("roles", []))
        roles_html = escape(roles) if roles else "—"
        applicability = link.get("applicability") or {}
        score = applicability.get("score")
        specificity = escape(applicability.get("specificity") or "—")
        normative = escape(applicability.get("normative_strength") or "—")
        rationale = escape(applicability.get("rationale") or "—")
        evidence_items = []
        for ev in link.get("evidence", []):
            path = escape(ev.get("path") or "—")
            lines = escape(ev.get("lines") or "—")
            evidence_items.append(f"`{path}`:{lines}")
        evidence_html = "<br>".join(evidence_items) if evidence_items else "—"
        disposition = escape(link.get("disposition") or "Observed")
        if link.get("selected_as_primary"):
            label = f"**{disposition} Primary**"
        else:
            label = disposition
        applicability_bits = []
        if score is not None:
            applicability_bits.append(f"score {float(score):.2f}")
        applicability_bits.append(specificity)
        applicability_bits.append(normative)
        applicability_html = " · ".join(applicability_bits)
        entry_lines = [
            f"{label} – `{link_id}` ({roles_html})",
            applicability_html,
            rationale,
            f"Evidence: {evidence_html}",
        ]
        omitted = link.get("omitted_with_reason")
        if isinstance(omitted, str) and omitted.strip():
            entry_lines.append(f"Omitted with reason: {escape(omitted.strip())}")
        entries.append("<br>".join(entry_lines))
    return "<br><br>".join(entries)

def format_remediation_steps(remediation_map: list[dict]) -> str:
    rendered = []
    for idx, step in enumerate(remediation_map, start=1):
        step_text = escape(step.get("step") or "")
        satisfies = ", ".join(f"`{escape(identifier)}`" for identifier in step.get("satisfies", []))
        rendered.append(f"{idx}. {step_text} → {satisfies if satisfies else '—'}")
    return "<br>".join(rendered)

def severity_counts():
    counts = Counter()
    for record in review_records.values():
        for entry in record.get("findings", []):
            sev = (entry.get("severity") or "Note").strip()
            counts[sev] += 1
    # Ensure deterministic order and presence
    ordered = ["Critical", "High", "Medium", "Low", "Note"]
    return {k: counts.get(k, 0) for k in ordered}

def counts_inline():
    c = severity_counts()
    parts = [f"{k}: {c[k]}" for k in ["Critical", "High", "Medium", "Low", "Note"]]
    return " | ".join(parts)

def format_overview():
    diff_stats = meta.get("diff_stats") or "—"
    branch = meta.get("branch") or "UNKNOWN"
    base = meta.get("base") or "UNKNOWN"
    head = meta.get("head") or "UNKNOWN"
    recorded = len(recorded_set)
    pending_count = len(pending)
    table = [
        "| | |",
        "|:--|:------------|",
        f"| **Run ID** | `{run_id}` |",
        f"| **Branch** | `{escape(branch)}` |",
        f"| **Base Commit** | `{escape(base)}` |",
        f"| **Head Commit** | `{escape(head)}` |",
        f"| **Commit Range** | `{escape(base)}..{escape(head)}` |",
        f"| **Diff Stats** | {escape(diff_stats)} |",
        f"| **Recorded Files** | {recorded} |",
        f"| **Pending Files** | {pending_count} |",
        f"| **Findings by Severity** | {escape(counts_inline())} |",
    ]
    coverage_summary = overall_coverage_summary(review_records)
    table.append(f"| **Traceability Coverage** | {escape(coverage_summary)} |")
    if inspected:
        inspected_count = len(inspected & changed_set)
        table.append(f"| **Inspected Files** | {inspected_count} / {len(changed_files)} |")
    return "\n".join(table)

def build_mapping_section(title: str, mapping: dict[str, str]) -> str:
    header = ["| Identifier | Description |", "|:--|:------------|"]
    rows = header.copy()
    if mapping:
        for identifier in sorted(mapping.keys(), key=lambda s: s.casefold()):
            rows.append(f"| `{escape(identifier)}` | {escape(mapping[identifier])} |")
    else:
        rows.append("| — | — |")
    return "\n".join([f"#### {title}"] + rows)

def format_spec_section():
    name = escape(spec.get("name") or "—")
    overview = escape(spec.get("overview") or "—")
    details = escape(spec.get("details") or "—")
    phases = spec.get("phases") or {}
    user_stories = spec.get("user_stories") or {}
    acceptance = spec.get("acceptance_criteria") or {}
    modules = spec.get("feature_modules") or {}
    section_parts = [
        "| | |",
        "|:--|:------------|",
        f"| **Name** | {name} |",
        f"| **Overview** | {overview} |",
        f"| **Details** | {details} |",
        "",
        build_mapping_section("Phases", phases),
        "",
        build_mapping_section("User Stories", user_stories),
        "",
        build_mapping_section("Acceptance Criteria", acceptance),
        "",
        build_mapping_section("Feature Modules", modules),
    ]
    return "\n".join(section_parts)

def format_findings():
    rows = []
    for path, record in sorted(review_records.items()):
        for entry in record.get("findings", []):
            rows.append(
                (
                    path,
                    entry.get("severity") or "Note",
                    entry.get("finding") or "",
                    entry,
                )
            )
    if not rows:
        return "_No findings recorded._"
    header_counts = f"_Severity counts – {counts_inline()}_"
    table = [
        "",
        header_counts,
        "",
        "| File | Severity | Finding | Traceability | Remediation |",
        "|:----------|:------|:------------|:-------------|:------------|",
    ]
    for path, severity, finding, entry in rows:
        remediation_text = escape(entry.get("remediation") or "")
        remediation_map = entry.get("remediation_map") or []
        remediation_steps = format_remediation_steps(remediation_map) if remediation_map else "—"
        remediation_cell = remediation_text
        if remediation_steps and remediation_steps != "—":
            remediation_cell = f"{remediation_cell}<br><br>Steps:<br>{remediation_steps}"
        primary_ids = entry.get("primary_ids") or []
        secondary_ids = entry.get("secondary_ids") or []
        primary_html = ", ".join(f"`{escape(pid)}`" for pid in primary_ids) if primary_ids else "—"
        secondary_html = ", ".join(f"`{escape(sid)}`" for sid in secondary_ids) if secondary_ids else "—"
        trace_parts = [f"Primary: {primary_html}"]
        if secondary_ids:
            trace_parts.append(f"Secondary: {secondary_html}")
        trace_cell = "<br>".join(trace_parts)
        table.append(
            f"| `{escape(path)}` | {escape(severity)} | {escape(finding)} | {trace_cell} | {remediation_cell} |"
        )
    return "\n".join(table)

def format_pending():
    if not pending:
        return "_No pending files – all changes recorded._"
    lines = []
    for path in pending:
        status = "inspected" if path in inspected else "not inspected"
        lines.append(f"- `{escape(path)}` ({status})")
    return "\n".join(lines)

def format_file_reviews():
    if not review_records:
        return "_No file reviews recorded yet._"
    entries = []
    ordered_paths = sorted(review_records.keys())
    if layout == "tabular":
        table = [
            "| File | Role | Functional Summary | Traceability | Changes | Findings | Notes |",
            "|:-----|:-----|:-------------------|:-------------|:--------|:---------|:------|",
        ]
        for path in ordered_paths:
            record = review_records[path]
            change_entries = []
            for idx, item in enumerate(record.get("change_description", []), start=1):
                change_entries.append(f"**Change {idx}:** {escape(item)}")
            changes = "<br>".join(change_entries) or "—"
            coverage_html = format_coverage_line(record)
            trace_entries_html = format_traceability_entries(record)
            traceability_cell = coverage_html
            if trace_entries_html and trace_entries_html != "—":
                traceability_cell = f"{coverage_html}<br><br>{trace_entries_html}"
            findings = []
            for entry in record.get("findings", []):
                severity_html = escape(entry.get("severity") or "Note")
                finding_html = escape(entry.get("finding") or "")
                remediation_html = escape(entry.get("remediation") or "")
                primary_html = ", ".join(f"`{escape(pid)}`" for pid in entry.get("primary_ids", [])) or "—"
                secondary_html = ", ".join(f"`{escape(sid)}`" for sid in entry.get("secondary_ids", [])) or "—"
                steps_html = format_remediation_steps(entry.get("remediation_map") or [])
                block_lines = [
                    f"**{severity_html}** – {finding_html}",
                    f"Primary: {primary_html}",
                    f"Secondary: {secondary_html}",
                ]
                if remediation_html:
                    block_lines.append(f"Remediation: {remediation_html}")
                if steps_html:
                    block_lines.append(f"Steps:<br>{steps_html}")
                findings.append("<br>".join(block_lines))
            findings_text = "<br><br>".join(findings) if findings else "—"
            notes = escape(record.get("notes") or "—")
            table.append(
                f"| `{escape(path)}` | {escape(record.get('file_description') or '—')} | {escape(record.get('functional_summary') or '—')} | {traceability_cell} | {changes} | {findings_text} | {notes} |"
            )
        return "\n".join(table)

    for path in ordered_paths:
        record = review_records[path]
        lines = ["| | |", "|:--|:------------|"]
        lines.append(f"| **Filename** | `{escape(path)}` |")
        lines.append(f"| **File Description** | {escape(record.get('file_description') or '—')} |")
        lines.append(f"| **Functional Summary** | {escape(record.get('functional_summary') or '—')} |")
        coverage_html = format_coverage_line(record)
        lines.append(f"| **Coverage** | {coverage_html} |")
        trace_block = format_traceability_entries(record)
        lines.append(f"| **Trace Links** | {trace_block} |")
        for idx, change in enumerate(record.get("change_description", []), start=1):
            lines.append(f"| **Change {idx}** | {escape(change)} |")
        findings = record.get("findings", [])
        if findings:
            rendered = []
            for entry in findings:
                severity = escape(entry.get("severity") or "Note")
                finding = escape(entry.get("finding") or "")
                remediation = escape(entry.get("remediation") or "")
                primary_html = ", ".join(f"`{escape(pid)}`" for pid in entry.get("primary_ids", [])) or "—"
                secondary_html = ", ".join(f"`{escape(sid)}`" for sid in entry.get("secondary_ids", [])) or "—"
                steps_html = format_remediation_steps(entry.get("remediation_map") or [])
                rendered.append(f"**{severity}** – {finding}")
                rendered.append(f"&nbsp;&nbsp;Primary: {primary_html}")
                if entry.get("secondary_ids"):
                    rendered.append(f"&nbsp;&nbsp;Secondary: {secondary_html}")
                if remediation:
                    rendered.append(f"&nbsp;&nbsp;Remediation: {remediation}")
                if steps_html:
                    rendered.append(f"&nbsp;&nbsp;Steps:<br>{steps_html}")
            findings_text = "<br>".join(rendered)
        else:
            findings_text = "—"
        lines.append(f"| **Findings** | {findings_text} |")
        notes = escape(record.get("notes") or "—")
        lines.append(f"| **Notes** | {notes} |")
        recorded_at = record.get("recorded_at") or "—"
        lines.append(f"| **Recorded At** | {escape(recorded_at)} |")
        entries.append("\n".join(lines))
    return "\n\n---\n\n".join(entries)

template = template_path.read_text(encoding="utf-8")
feature_name = spec.get("name") or meta.get("branch") or run_id

report = template.replace("{{FEATURE_NAME}}", escape(feature_name))
report = report.replace("{{AUTO_OVERVIEW}}", format_overview())
report = report.replace("{{AUTO_SPEC_SECTION}}", format_spec_section())
report = report.replace("{{AUTO_FILE_REVIEWS}}", format_file_reviews())
report = report.replace("{{AUTO_FINDINGS}}", format_findings())
report = report.replace("{{AUTO_PENDING}}", format_pending())

if force_flag:
    report = (
        "> NOTE: Report generated with --force; the review loop may still be in progress.\n\n"
        + report
    )

output_path.write_text(report, encoding="utf-8")
PY

mv "${report_tmp}" "${REPORT_PATH}"

trap - EXIT
cleanup

echo "Report generated at ${REPORT_PATH}"
echo "Reminder: replace all MANUAL_* placeholders before publishing the report."
