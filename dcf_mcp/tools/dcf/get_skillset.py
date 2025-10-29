from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from ._skillset_common import (
    init_result,
    load_schema_validator,
    resolve_preview_length,
    sort_available_skills,
    summarise_manifest,
)

DCF_MANIFESTS_DIR = os.getenv("DCF_MANIFESTS_DIR", "/app/generated/manifests")


def get_skillset(
    manifests_dir: str | None = None,
    schema_path: str | None = None,
    include_previews: bool = True,
    preview_chars: int | None = None,
) -> Dict[str, Any]:
    """Discover Skill Manifests from a directory and summarize their metadata.

    This tool replicates the long-standing behaviour that planning agents rely on:
    scan a directory for ``*.json`` files, parse each one as a skill manifest, and
    produce a compact catalog that exposes the most relevant manifest metadata.
    Highlights:

    * Validation is optional—if ``schema_path`` is provided and ``jsonschema`` is
      importable, each manifest is checked against the supplied schema. Missing
      dependencies or load errors degrade gracefully by adding warnings instead of
      failing discovery.
    * Invalid manifests are isolated. Per-file errors are captured in the
      corresponding entry while the rest of the directory continues to be processed.
    * Aliases are generated for convenience (``name@version``, ``skill://`` URIs,
      and the raw ``manifestId`` when present) so planners have multiple lookup
      options.

    Args:
        manifests_dir: Optional override for the directory containing manifest
            files. Defaults to ``$DCF_MANIFESTS_DIR`` (``/app/generated/manifests``).
            The directory must exist and be readable.
        schema_path: Optional filesystem path to the manifest JSON Schema (for
            example ``dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json``). When
            provided and ``jsonschema`` is installed, each manifest is validated.
        include_previews: When ``True`` (default) the catalog includes a
            ``directives_preview`` string trimmed to ``preview_chars`` to help the
            agent choose a skill without loading it fully.
        preview_chars: Optional maximum length for ``directives_preview``. If
            ``None`` or invalid, the tool falls back to ``$SKILL_PREVIEW_CHARS``
            (default ``400``).

    Returns:
        dict: Structured response compatible with the historical implementation::

            {
              "ok": bool,
              "exit_code": int,           # 0 on success, 4 on error
              "available_skills": [
                {
                  "manifestId": str | None,
                  "skillPackageId": str | None,
                  "skillName": str | None,
                  "skillVersion": str | None,
                  "manifestApiVersion": str | None,
                  "aliases": list[str],
                  "description": str | None,
                  "tags": list[str],
                  "permissions": {"egress": str, "secrets": list[str]},
                  "toolNames": list[str],
                  "toolCount": int,
                  "dataSourceCount": int,
                  "directives_preview": str | None,
                  "path": str,                    # absolute filesystem path
                  "valid_schema": bool | None,
                  "errors": list[str],
                  "warnings": list[str],
                },
              ],
              "warnings": list[str],
              "error": str | None,
            }

    The function never raises: fatal issues are surfaced in the ``error`` field
    while per-manifest problems are recorded inside each catalog entry.
    """
    out = init_result()

    if manifests_dir is not None and not isinstance(manifests_dir, str):
        out["error"] = "TypeError: manifests_dir must be a string path or None"
        return out
    if schema_path is not None and not isinstance(schema_path, str):
        out["error"] = "TypeError: schema_path must be a string path or None"
        return out
    if not isinstance(include_previews, bool):
        out["error"] = "TypeError: include_previews must be a boolean"
        return out

    base_dir = manifests_dir or DCF_MANIFESTS_DIR
    preview_len = resolve_preview_length(preview_chars)

    try:
        directory = Path(base_dir)
        if not directory.is_dir():
            raise FileNotFoundError(
                f"Manifest directory '{base_dir}' not found or not a directory."
            )
    except Exception as exc:
        out["error"] = str(exc)
        return out

    validator, schema_requested = load_schema_validator(schema_path, out["warnings"])

    try:
        manifest_files = sorted(directory.glob("*.json"))
    except Exception as exc:
        out["error"] = f"Failed to scan directory: {exc}"
        return out

    for manifest_path in manifest_files:
        item = summarise_manifest(
            manifest_path,
            include_previews=include_previews,
            preview_len=preview_len,
            validator=validator,
            schema_requested=schema_requested,
        )
        out["available_skills"].append(item)

    sort_available_skills(out["available_skills"])
    out["ok"] = True
    out["exit_code"] = 0
    return out