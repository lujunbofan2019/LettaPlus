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
    """Discover Skill Manifests from a directory and summarise their metadata."""
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
