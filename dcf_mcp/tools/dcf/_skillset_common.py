"""Shared utilities for skill catalog discovery tools."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_PREVIEW_CHARS = int(os.getenv("SKILL_PREVIEW_CHARS", "400"))


def init_result() -> Dict[str, Any]:
    """Return the base response structure shared by discovery tools."""
    return {
        "ok": False,
        "exit_code": 4,
        "available_skills": [],
        "warnings": [],
        "error": None,
    }


def resolve_preview_length(preview_chars: Optional[int]) -> int:
    """Compute the preview length while guarding against invalid inputs."""
    try:
        if preview_chars is None:
            raise ValueError
        return int(preview_chars)
    except Exception:
        return DEFAULT_PREVIEW_CHARS


def load_schema_validator(
    schema_path: Optional[str],
    warnings: List[str],
) -> Tuple[Optional["Draft202012Validator"], bool]:
    """Best-effort JSON schema loader.

    Returns (validator, schema_requested).  The latter is true when the caller
    asked for validation even if the validator could not be created (e.g. the
    dependency is missing).
    """
    if not schema_path:
        return None, False

    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:
        warnings.append("jsonschema not installed; skipping schema validation.")
        return None, True

    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema_doc = json.load(fh)
    except Exception as exc:
        warnings.append(f"Failed to load schema '{schema_path}': {exc}")
        return None, True

    try:
        validator = Draft202012Validator(schema_doc)
    except Exception as exc:
        warnings.append(f"Failed to initialise schema validator: {exc}")
        return None, True

    return validator, True


def _base_item(path: Path) -> Dict[str, Any]:
    return {
        "manifestId": None,
        # "skillPackageId": None,
        "skillName": None,
        "skillVersion": None,
        # "manifestApiVersion": None,
        # "aliases": [],
        "description": None,
        # "tags": [],
        # "permissions": {"egress": "none", "secrets": []},
        # "toolNames": [],
        # "toolCount": 0,
        # "dataSourceCount": 0,
        # "directives_preview": None,
        "path": str(path if path.is_absolute() else path.resolve()),
        "valid_schema": None,
        "errors": [],
        "warnings": [],
    }


def summarise_manifest(
    path: Path,
    include_previews: bool,
    preview_len: int,
    validator: Optional["Draft202012Validator"],
    schema_requested: bool,
    prefill: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Summarise a manifest file into catalog metadata."""
    item = _base_item(path)
    if prefill:
        for key, value in prefill.items():
            if key in item and value is not None:
                item[key] = value
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError as exc:
        item["errors"].append(f"FileError: {exc}")
        return item
    except json.JSONDecodeError as exc:  # type: ignore[attr-defined]
        item["errors"].append(f"JSONDecodeError: {exc}")
        return item
    except Exception as exc:
        item["errors"].append(f"ManifestLoadError: {exc}")
        return item

    if validator is not None:
        try:
            errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        except Exception as exc:
            item["valid_schema"] = False
            item["errors"].append(f"SchemaValidationError: {exc}")
        else:
            if errors:
                item["valid_schema"] = False
                for err in errors:
                    path_str = "/".join(map(str, err.path)) or "<root>"
                    item["errors"].append(f"{path_str}: {err.message}")
            else:
                item["valid_schema"] = True
    elif schema_requested:
        item["valid_schema"] = None

    # Extract key fields
    v = doc.get("manifestId")
    item["manifestId"] = v if isinstance(v, str) else item["manifestId"]
    v = doc.get("skillPackageId")
    item["skillPackageId"] = v if isinstance(v, str) else item["skillPackageId"]
    v = doc.get("skillName")
    item["skillName"] = v if isinstance(v, str) else item["skillName"]
    v = doc.get("skillVersion")
    item["skillVersion"] = v if isinstance(v, str) else item["skillVersion"]
    v = doc.get("manifestApiVersion")
    item["manifestApiVersion"] = v if isinstance(v, str) else item["manifestApiVersion"]
    v = doc.get("description")
    item["description"] = v if isinstance(v, str) else item["description"]

    tags = doc.get("tags") or []
    if isinstance(tags, list):
        item["tags"] = [t for t in tags if isinstance(t, str)]

    permissions = doc.get("permissions") or {}
    if isinstance(permissions, dict):
        egress = permissions.get("egress")
        if egress in ("none", "intranet", "internet"):
            item["permissions"]["egress"] = egress
        secrets = permissions.get("secrets")
        if isinstance(secrets, list):
            item["permissions"]["secrets"] = [s for s in secrets if isinstance(s, str)]

    tools = doc.get("requiredTools") or []
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict):
                name = tool.get("toolName")
                if isinstance(name, str) and name:
                    item["toolNames"].append(name)
        item["toolCount"] = len([tool for tool in tools if isinstance(tool, dict)])

    data_sources = doc.get("requiredDataSources") or []
    if isinstance(data_sources, list):
        item["dataSourceCount"] = len([ds for ds in data_sources if isinstance(ds, dict)])

    if include_previews:
        directives = doc.get("skillDirectives")
        if isinstance(directives, str) and directives:
            preview = directives.strip().replace("\n", " ").replace("\r", " ")
            if len(preview) > preview_len:
                preview = preview[:preview_len].rstrip() + "…"
            item["directives_preview"] = preview

    missing = []
    if not item["manifestId"]:
        missing.append("manifestId")
    if not item["skillName"]:
        missing.append("skillName")
    if not item["skillVersion"]:
        missing.append("skillVersion")
    if missing:
        item["errors"].append("Missing required fields: " + ", ".join(missing))

    name = (item["skillName"] or "").lower()
    version = item["skillVersion"] or ""
    package = item["skillPackageId"] or ""
    if name and version:
        item["aliases"].append(f"{name}@{version}")
        item["aliases"].append(f"skill://{name}@{version}")
    if package and version:
        item["aliases"].append(f"skill://{package}@{version}")
    if item["manifestId"]:
        item["aliases"].append(item["manifestId"])

    return item


def sort_available_skills(skills: Iterable[Dict[str, Any]]) -> None:
    """Sort the list of skills in-place for a stable UX."""
    try:
        skills.sort(  # type: ignore[attr-defined]
            key=lambda x: (
                (x.get("skillName") or "").lower(),
                x.get("skillVersion") or "",
                x.get("manifestId") or "",
            )
        )
    except Exception:
        pass