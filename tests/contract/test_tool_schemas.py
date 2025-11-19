from __future__ import annotations

from scratch_notebook.server import scratch_create, scratch_list


def test_scratch_create_metadata_schema_exposes_canonical_fields() -> None:
    metadata_schema = scratch_create.parameters["properties"]["metadata"]
    variants = metadata_schema.get("anyOf", [])
    object_schema = next((variant for variant in variants if variant.get("type") == "object"), {})
    assert object_schema, "scratch_create metadata schema must include object variant"

    metadata_props = object_schema.get("properties", {})
    required = {"title", "description", "summary"}
    missing = required.difference(metadata_props)
    assert not missing, f"metadata canonical fields missing from schema: {sorted(missing)}"


def test_scratch_list_output_schema_exposes_lean_metadata() -> None:
    schema = scratch_list.output_schema or {}
    metadata_props = (
        schema.get("properties", {})
        .get("scratchpads", {})
        .get("items", {})
        .get("properties", {})
    )
    assert metadata_props, "scratch_list schema must describe per-entry properties"
    assert metadata_props.get("title"), "scratch_list must expose title"
    assert metadata_props.get("description"), "scratch_list must expose description"
    assert "summary" not in metadata_props, "scratch_list must omit summary to stay lean"
    assert "metadata" not in metadata_props, "scratch_list must not embed arbitrary metadata"


def test_scratch_create_description_instructs_namespace_reuse() -> None:
    description = scratch_create.description
    assert "scratch_namespace_list" in description
    lower_desc = description.lower()
    assert "reuse an existing prefix" in lower_desc
    assert "default tenant" in lower_desc or "multiple assistants" in lower_desc
