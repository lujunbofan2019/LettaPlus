from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ._skillset_common import (
    init_result,
    load_schema_validator,
    resolve_preview_length,
    sort_available_skills,
    summarise_manifest,
)

DCF_SKILLS_CATALOG = os.getenv(
    "DCF_SKILLS_CATALOG", "generated/catalogs/skills_catalog.json"
)


def _normalise_path(entry_path: str, catalog_dir: Path) -> Path:
    cleaned = entry_path.strip()
    if cleaned.startswith("file://"):
        cleaned = cleaned[7:]
    path = Path(cleaned)
    if not path.is_absolute():
        path = (catalog_dir / path).resolve()
    return path


def get_skillset_from_catalog(
    catalog_path: Optional[str] = None,
    schema_path: Optional[str] = None,
    include_previews: bool = True,
    preview_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Discover Skill Manifests using a pre-built catalog file."""
    out = init_result()

    if catalog_path is not None and not isinstance(catalog_path, str):
        out["error"] = "TypeError: catalog_path must be a string path or None"
        return out
    if schema_path is not None and not isinstance(schema_path, str):
        out["error"] = "TypeError: schema_path must be a string path or None"
        return out
    if not isinstance(include_previews, bool):
        out["error"] = "TypeError: include_previews must be a boolean"
        return out

    preview_len = resolve_preview_length(preview_chars)
    catalog_location = catalog_path or DCF_SKILLS_CATALOG

    try:
        catalog_file = Path(catalog_location)
        with open(catalog_file, "r", encoding="utf-8") as fh:
            catalog_doc = json.load(fh)
    except FileNotFoundError:
        out["error"] = f"Catalog file '{catalog_location}' not found"
        return out
    except Exception as exc:
        out["error"] = f"Failed to read catalog '{catalog_location}': {exc}"
        return out

    skills = catalog_doc.get("skills")
    if not isinstance(skills, list):
        out["error"] = "Catalog missing 'skills' array"
        return out

    validator, schema_requested = load_schema_validator(schema_path, out["warnings"])
    catalog_dir = catalog_file.parent

    for entry in skills:
        if not isinstance(entry, dict):
            out["warnings"].append("Catalog entry is not an object; skipped")
            continue

        entry_path = entry.get("path")
        if not isinstance(entry_path, str) or not entry_path.strip():
            out["warnings"].append("Catalog entry missing 'path'; skipped")
            continue

        manifest_path = _normalise_path(entry_path, catalog_dir)
        prefill = {
            key: entry.get(key)
            for key in (
                "manifestId",
                "skillPackageId",
                "skillName",
                "skillVersion",
                "manifestApiVersion",
                "description",
            )
        }

        item = summarise_manifest(
            manifest_path,
            include_previews=include_previews,
            preview_len=preview_len,
            validator=validator,
            schema_requested=schema_requested,
            prefill=prefill,
        )
        out["available_skills"].append(item)

    sort_available_skills(out["available_skills"])
    out["ok"] = True
    out["exit_code"] = 0
    return out
