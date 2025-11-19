#!/usr/bin/env python3
"""Validate and merge review-file payloads for SpecKit runs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ALLOWED_SEVERITIES = {"Critical", "High", "Medium", "Low", "Note"}
ALLOWED_ROLES = {"ViolationCriterion", "RemediationConstraint", "Informational"}
ALLOWED_SPECIFICITY = {"Line", "Block", "Function", "Component", "System"}
ALLOWED_NORMATIVE = {"MUST", "SHOULD", "MAY"}
ALLOWED_DISPOSITIONS = {"Violated", "Satisfied", "Observed"}
TRACE_LINE_PATTERN = re.compile(r"^[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*$")


class ValidationError(RuntimeError):
    """Raised when payload validation fails."""


def fail(message: str) -> None:
    """Emit an error to stderr and exit with status 2."""

    sys.stderr.write(f"ERROR: {message}\n")
    raise ValidationError(message)


def load_json(path: Path, *, description: str, default: object) -> object:
    if not path.exists() or path.stat().st_size == 0:
        return default
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"unable to parse {description}: {exc}")
    return default  # Unreachable, satisfy type checkers


def ensure_min_length(value: object, length: int, message: str) -> str:
    if not isinstance(value, str):
        fail(f"{message} must be a string.")
    stripped = value.strip()
    if len(stripped) < length:
        fail(f"{message} must be at least {length} characters.")
    return stripped


def ensure_change_array(value: object) -> List[str]:
    if not isinstance(value, list) or not value:
        fail("change_description must be a non-empty array.")
    return [ensure_min_length(item, 50, f"change_description[{idx}]") for idx, item in enumerate(value, 1)]


def ensure_functional_summary(value: object) -> str:
    return ensure_min_length(value, 50, "functional_summary")


def ensure_trace_links(entries: object) -> Tuple[List[Dict], Dict[str, str], List[str], Dict[str, str]]:
    if not isinstance(entries, list) or not entries:
        fail("trace_links must be a non-empty array.")

    seen_ids: Dict[str, str] = {}
    processed: List[Dict] = []
    casefold_map: Dict[str, str] = {}
    violated_primary_ids: List[str] = []
    disposition_lookup: Dict[str, str] = {}
    has_violated = False

    for idx, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            fail(f"trace_links[{idx}] must be an object.")

        raw_id = ensure_min_length(entry.get("id", ""), 3, f"trace_links[{idx}].id")
        folded = raw_id.casefold()
        if folded in seen_ids:
            fail(
                "trace_links contains duplicate identifier "
                f"'{raw_id}' (case-insensitive match with '{seen_ids[folded]}')."
            )
        seen_ids[folded] = raw_id
        casefold_map[folded] = raw_id

        roles = entry.get("roles")
        if not isinstance(roles, list) or not roles:
            fail(f"trace_links[{idx}].roles must be a non-empty array.")
        role_set = set()
        for role in roles:
            if role not in ALLOWED_ROLES:
                fail(f"trace_links[{idx}].roles contains invalid value '{role}'.")
            if role in role_set:
                fail(f"trace_links[{idx}].roles must not contain duplicates (saw '{role}').")
            role_set.add(role)

        applicability = entry.get("applicability")
        if not isinstance(applicability, dict):
            fail(f"trace_links[{idx}].applicability must be an object.")
        score = applicability.get("score")
        if not isinstance(score, (int, float)) or not (0 <= score <= 1):
            fail(f"trace_links[{idx}].applicability.score must be between 0 and 1.")
        specificity = applicability.get("specificity")
        if specificity not in ALLOWED_SPECIFICITY:
            fail(
                "trace_links[{idx}].applicability.specificity must be one of "
                f"{sorted(ALLOWED_SPECIFICITY)}.".format(idx=idx)
            )
        normative = applicability.get("normative_strength")
        if normative not in ALLOWED_NORMATIVE:
            fail(
                "trace_links[{idx}].applicability.normative_strength must be one of "
                f"{sorted(ALLOWED_NORMATIVE)}.".format(idx=idx)
            )
        rationale = ensure_min_length(
            applicability.get("rationale", ""), 25, f"trace_links[{idx}].applicability.rationale"
        )

        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            fail(f"trace_links[{idx}].evidence must be a non-empty array.")
        normalized_evidence: List[Dict[str, str]] = []
        for ev_idx, ev in enumerate(evidence, 1):
            if not isinstance(ev, dict):
                fail(f"trace_links[{idx}].evidence[{ev_idx}] must be an object.")
            path = ensure_min_length(ev.get("path", ""), 1, f"trace_links[{idx}].evidence[{ev_idx}].path")
            lines = ensure_min_length(ev.get("lines", ""), 1, f"trace_links[{idx}].evidence[{ev_idx}].lines")
            if not TRACE_LINE_PATTERN.match(lines):
                fail(
                    "trace_links[{idx}].evidence[{ev_idx}].lines '{lines}' does not match expected "
                    "numeric range pattern.".format(idx=idx, ev_idx=ev_idx, lines=lines)
                )
            normalized_evidence.append({"path": path, "lines": lines})

        disposition_raw = entry.get("disposition")
        if not isinstance(disposition_raw, str):
            fail(f"trace_links[{idx}].disposition must be a string.")
        disposition = disposition_raw.strip()
        if disposition not in ALLOWED_DISPOSITIONS:
            fail(
                "trace_links[{idx}].disposition must be one of {allowed}.".format(
                    idx=idx, allowed=sorted(ALLOWED_DISPOSITIONS)
                )
            )
        disposition_lookup[folded] = disposition
        if disposition == "Violated":
            has_violated = True

        selected_as_primary = bool(entry.get("selected_as_primary", False))
        if selected_as_primary and disposition != "Violated":
            fail(
                "trace_links[{idx}].selected_as_primary can only be true when disposition is 'Violated'.".format(
                    idx=idx
                )
            )
        omitted_with_reason = entry.get("omitted_with_reason")
        if omitted_with_reason is not None:
            ensure_min_length(omitted_with_reason, 25, f"trace_links[{idx}].omitted_with_reason")

        processed_entry = {
            "id": raw_id,
            "roles": sorted(role_set),
            "applicability": {
                "score": float(score),
                "specificity": specificity,
                "normative_strength": normative,
                "rationale": rationale,
            },
            "evidence": normalized_evidence,
            "selected_as_primary": selected_as_primary,
            "disposition": disposition,
        }
        if isinstance(omitted_with_reason, str):
            processed_entry["omitted_with_reason"] = omitted_with_reason.strip()
        processed.append(processed_entry)
        if selected_as_primary:
            violated_primary_ids.append(raw_id)

    if has_violated and not violated_primary_ids:
        fail("At least one Violated trace must be marked selected_as_primary.")

    return processed, casefold_map, violated_primary_ids, disposition_lookup


def ensure_coverage(value: object, expected_considered: int) -> Dict[str, object]:
    if not isinstance(value, dict):
        fail("coverage must be an object.")
    candidate_count = value.get("candidate_count")
    considered_count = value.get("considered_count")
    threshold = value.get("threshold")
    status = value.get("status")
    if not isinstance(candidate_count, int) or candidate_count < 1:
        fail("coverage.candidate_count must be an integer ≥ 1.")
    if not isinstance(considered_count, int) or considered_count < 1:
        fail("coverage.considered_count must be an integer ≥ 1.")
    if considered_count != expected_considered:
        fail("coverage.considered_count must match the number of trace_links entries.")
    if considered_count > candidate_count:
        fail("coverage.considered_count cannot exceed coverage.candidate_count.")
    if not isinstance(threshold, (int, float)) or not (0 <= threshold <= 1):
        fail("coverage.threshold must be between 0 and 1.")
    if status not in {"MeetsThreshold", "BelowThreshold"}:
        fail("coverage.status must be either 'MeetsThreshold' or 'BelowThreshold'.")
    ratio = considered_count / candidate_count if candidate_count else 0
    if status == "MeetsThreshold" and ratio + 1e-9 < threshold:
        fail(
            "coverage.status is 'MeetsThreshold' but considered/candidate is below the threshold."
        )
    if status == "BelowThreshold" and ratio >= threshold:
        fail(
            "coverage.status is 'BelowThreshold' but considered/candidate meets the threshold."
        )
    return {
        "candidate_count": candidate_count,
        "considered_count": considered_count,
        "threshold": float(threshold),
        "status": status,
    }


def ensure_findings(
    items: object,
    trace_lookup: Dict[str, str],
    disposition_lookup: Dict[str, str],
    notes_text: str,
) -> Tuple[List[Dict], Iterable[str]]:
    if not isinstance(items, list):
        fail("findings must be an array.")

    normalized: List[Dict] = []
    primary_hits: List[str] = []

    for idx, entry in enumerate(items, 1):
        if not isinstance(entry, dict):
            fail(f"findings[{idx}] must be an object.")

        finding = ensure_min_length(entry.get("finding", ""), 25, f"findings[{idx}].finding")
        remediation = ensure_min_length(entry.get("remediation", ""), 25, f"findings[{idx}].remediation")
        severity = entry.get("severity")
        if severity not in ALLOWED_SEVERITIES:
            fail(
                "findings[{idx}].severity must be one of {allowed}.".format(
                    idx=idx, allowed=sorted(ALLOWED_SEVERITIES)
                )
            )

        primary_ids = entry.get("primary_ids")
        if not isinstance(primary_ids, list) or not primary_ids:
            fail(f"findings[{idx}].primary_ids must be a non-empty array.")
        normalized_primary: List[str] = []
        for pid in primary_ids:
            if not isinstance(pid, str) or not pid.strip():
                fail(f"findings[{idx}].primary_ids must contain strings.")
            folded = pid.strip().casefold()
            if folded not in trace_lookup:
                fail(
                    f"findings[{idx}].primary_ids includes '{pid}' which is not listed in trace_links."
                )
            canonical = trace_lookup[folded]
            disposition = disposition_lookup.get(folded)
            if disposition != "Violated":
                fail(
                    "findings[{idx}].primary_ids includes '{pid}' whose disposition is '{disp}', "
                    "but only Violated traces can be primary.".format(
                        idx=idx, pid=pid, disp=disposition or "unknown"
                    )
                )
            normalized_primary.append(canonical)
            primary_hits.append(canonical)

        secondary_ids = entry.get("secondary_ids", [])
        normalized_secondary: List[str] = []
        if secondary_ids:
            if not isinstance(secondary_ids, list):
                fail(f"findings[{idx}].secondary_ids must be an array when provided.")
            for sid in secondary_ids:
                if not isinstance(sid, str) or not sid.strip():
                    fail(f"findings[{idx}].secondary_ids must contain strings.")
                folded = sid.strip().casefold()
                if folded not in trace_lookup:
                    fail(
                        f"findings[{idx}].secondary_ids includes '{sid}' which is not listed in trace_links."
                    )
                normalized_secondary.append(trace_lookup[folded])

        remediation_map = entry.get("remediation_map")
        if not isinstance(remediation_map, list) or not remediation_map:
            fail(f"findings[{idx}].remediation_map must be a non-empty array of steps.")

        satisfies_union: set[str] = set()
        normalized_steps: List[Dict[str, object]] = []
        for step_idx, step in enumerate(remediation_map, 1):
            if not isinstance(step, dict):
                fail(f"findings[{idx}].remediation_map[{step_idx}] must be an object.")
            step_text = ensure_min_length(
                step.get("step", ""), 10, f"findings[{idx}].remediation_map[{step_idx}].step"
            )
            satisfies = step.get("satisfies")
            if not isinstance(satisfies, list) or not satisfies:
                fail(
                    f"findings[{idx}].remediation_map[{step_idx}].satisfies must be a non-empty array."
                )
            normalized_ids: List[str] = []
            seen_local: set[str] = set()
            for sid in satisfies:
                if not isinstance(sid, str) or not sid.strip():
                    fail(
                        f"findings[{idx}].remediation_map[{step_idx}].satisfies must contain strings."
                    )
                folded = sid.strip().casefold()
                if folded not in trace_lookup:
                    fail(
                        "findings[{idx}].remediation_map[{step_idx}].satisfies includes '{sid}' "
                        "which is not listed in trace_links.".format(idx=idx, step_idx=step_idx, sid=sid)
                    )
                canonical = trace_lookup[folded]
                if canonical in seen_local:
                    fail(
                        "findings[{idx}].remediation_map[{step_idx}].satisfies contains duplicate id "
                        f"'{canonical}'."
                    )
                seen_local.add(canonical)
                normalized_ids.append(canonical)
                satisfies_union.add(canonical)
            normalized_steps.append({"step": step_text, "satisfies": normalized_ids})

        primary_missing = [pid for pid in normalized_primary if pid not in satisfies_union]
        if primary_missing:
            fail(
                "findings[{idx}] remediation_map does not satisfy primary ids: {ids}.".format(
                    idx=idx, ids=", ".join(primary_missing)
                )
            )
        if normalized_secondary:
            secondary_missing = [sid for sid in normalized_secondary if sid not in satisfies_union]
            if secondary_missing and (not notes_text or len(notes_text) < 25):
                fail(
                    "findings[{idx}] remediation_map is missing secondary ids {ids} without adequate "
                    "justification in notes.".format(idx=idx, ids=", ".join(secondary_missing))
                )

        normalized.append(
            {
                "finding": finding,
                "severity": severity,
                "remediation": remediation,
                "primary_ids": normalized_primary,
                "secondary_ids": normalized_secondary,
                "remediation_map": normalized_steps,
            }
        )

    return normalized, primary_hits


def process_payload(meta_path: Path, existing_path: Path, payload_path: Path) -> Tuple[List[str], Dict[str, object]]:
    meta = load_json(meta_path, description="meta dataset", default={})
    changed_files = {
        entry.get("path")
        for entry in meta.get("changed_files", [])
        if isinstance(entry, dict) and entry.get("path")
    }

    if existing_path.exists() and existing_path.stat().st_size > 0:
        existing = load_json(existing_path, description="existing files dataset", default={})
    else:
        existing = {}

    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON payload: {exc}")
    if not isinstance(payload, dict) or not payload:
        fail("payload must be a non-empty JSON object mapping file paths to records.")

    updated = dict(existing)
    recorded_paths: List[str] = []
    timestamp = datetime.utcnow().isoformat() + "Z"

    for raw_path, record in payload.items():
        if not isinstance(raw_path, str) or not raw_path.strip():
            fail("file paths must be non-empty strings.")
        normalized_path = raw_path.strip()
        if changed_files and normalized_path not in changed_files:
            fail(f"'{normalized_path}' is not part of the recorded change list.")
        if not isinstance(record, dict):
            fail(f"record for '{normalized_path}' must be an object.")

        file_description = ensure_min_length(
            record.get("file_description", ""), 25, f"record['{normalized_path}'].file_description"
        )
        functional_summary = ensure_functional_summary(record.get("functional_summary", ""))
        change_description = ensure_change_array(record.get("change_description"))
        notes = record.get("notes", "")
        if notes and not isinstance(notes, str):
            fail(f"notes for '{normalized_path}' must be a string when provided.")
        notes_text = notes.strip() if isinstance(notes, str) else ""

        trace_links_raw = record.get("trace_links")
        trace_links, trace_lookup, violated_primary_required, disposition_lookup = ensure_trace_links(
            trace_links_raw
        )
        coverage = ensure_coverage(record.get("coverage"), len(trace_links))
        findings_raw = record.get("findings", [])
        findings, primary_hits = ensure_findings(
            findings_raw, trace_lookup, disposition_lookup, notes_text
        )

        if coverage["status"] == "BelowThreshold" and len(notes_text) < 25:
            fail(
                "coverage.status is BelowThreshold; provide justification of at least 25 characters in notes."
            )

        missing_primary = sorted({pid for pid in violated_primary_required if pid not in primary_hits})
        if missing_primary:
            fail(
                "findings are missing Violated primary ids declared in trace_links: {ids}.".format(
                    ids=", ".join(missing_primary)
                )
            )

        updated[normalized_path] = {
            "file_description": file_description,
            "functional_summary": functional_summary,
            "change_description": change_description,
            "trace_links": trace_links,
            "coverage": coverage,
            "findings": findings,
            "notes": notes_text,
            "recorded_at": timestamp,
        }
        recorded_paths.append(normalized_path)

    return recorded_paths, updated


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Process review file payload")
    parser.add_argument("--meta", required=True, type=Path, help="Path to decrypted meta JSON")
    parser.add_argument("--existing", required=True, type=Path, help="Path to decrypted files JSON")
    parser.add_argument("--payload", required=True, type=Path, help="Path to incoming payload JSON")
    parser.add_argument("--meta-out", required=True, type=Path, help="Where to write recorded path list JSON")
    parser.add_argument("--output", required=True, type=Path, help="Where to write updated files JSON")
    args = parser.parse_args()

    try:
        recorded_paths, updated = process_payload(args.meta, args.existing, args.payload)
    except ValidationError:
        sys.exit(2)

    args.meta_out.write_text(json.dumps(recorded_paths), encoding="utf-8")
    args.output.write_text(json.dumps(updated, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_cli()
