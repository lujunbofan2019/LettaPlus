from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _load_manifest_text(skill_manifest: str, out: Dict[str, Any]) -> str | None:
    candidate = (skill_manifest or "").strip()
    if not candidate:
        out["warnings"].append("InputError: skill_manifest is empty")
        out["exit_code"] = 4
        return None

    if candidate.startswith("{") or candidate.startswith("["):
        return skill_manifest

    if candidate.startswith("file://"):
        path = Path(candidate[7:])
    else:
        path = Path(candidate)

    try:
        return path.expanduser().read_text(encoding="utf-8")
    except Exception as ex:  # pragma: no cover - defensive, mirrors load_skill
        out["warnings"].append(f"ManifestLoadError: failed to read '{path}': {ex}")
        out["exit_code"] = 4
        return None


def validate_skill_manifest(skill_json: str, schema_path: str) -> Dict[str, Any]:
    """Validate a Skill Manifest (v2.0.0) and run static sanity checks.

    Steps:
      1) Determine the manifest source: treat ``skill_json`` as either the literal
         JSON string *or* a filesystem/``file://`` path to a manifest file and
         load it accordingly.
      2) JSON Schema validation against the provided schema file.
      3) Static checks (e.g., unique tool names).

    Args:
      skill_json: Raw JSON manifest content **or** path/``file://`` URI pointing
        to the manifest on disk. Relative paths are resolved against the working
        directory, matching :func:`load_skill` semantics.
      schema_path: Filesystem path to the skill manifest JSON Schema file used
        for validation.

    Returns:
      {
        "ok": bool,
        "exit_code": int,          # 0 OK, 1 schema errors, 2 static errors, 4 other errors
        "schema_errors": [str],
        "static_errors": [str],
        "warnings": [str]
      }
    """
    out = {"ok": False, "exit_code": 4, "schema_errors": [], "static_errors": [], "warnings": []}

    # Lazy import so the module can be loaded without jsonschema installed
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except Exception as ex:
        out["warnings"].append(f"DependencyError: jsonschema not available: {ex}")
        out["exit_code"] = 4
        return out

    manifest_text = _load_manifest_text(skill_json, out)
    if manifest_text is None:
        return out

    # Parse instance
    try:
        inst = json.loads(manifest_text)
    except Exception as ex:
        out["warnings"].append(f"JSONDecodeError: {ex}")
        out["exit_code"] = 4
        return out

    # Load schema
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as ex:
        out["warnings"].append(f"SchemaLoadError: {ex}")
        out["exit_code"] = 4
        return out

    # Schema validation
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(inst), key=lambda e: list(e.path))
        if errors:
            for e in errors:
                path = "/".join(map(str, e.path)) or "<root>"
                out["schema_errors"].append(f"{path}: {e.message}")
            out["exit_code"] = 1
            return out
    except Exception as ex:
        out["warnings"].append(f"SchemaValidationError: {ex}")
        out["exit_code"] = 4
        return out

    # Static checks
    try:
        # Unique toolName (case-insensitive) across requiredTools
        names_index = {}
        tools = inst.get("requiredTools") or []
        if not isinstance(tools, list):
            out["static_errors"].append("requiredTools must be an array when present.")
        else:
            for i, tr in enumerate(tools):
                if not isinstance(tr, dict):
                    out["static_errors"].append(f"requiredTools[{i}] must be an object")
                    continue
                name_val = tr.get("toolName")
                name = name_val.strip() if isinstance(name_val, str) else ""
                if not name:
                    out["static_errors"].append(f"requiredTools[{i}].toolName must be a non-empty string")
                    continue
                key = name.lower()
                if key in names_index:
                    out["static_errors"].append(
                        f"Duplicate toolName (case-insensitive): '{name}' at indexes {names_index[key]} and {i}"
                    )
                else:
                    names_index[key] = i

        # Permissions sanity
        perms = inst.get("permissions") or {}
        if not isinstance(perms, dict):
            out["static_errors"].append("permissions must be an object when present")
        else:
            if "secrets" in perms and not isinstance(perms["secrets"], list):
                out["static_errors"].append("permissions.secrets must be an array of strings")

        if out["static_errors"]:
            out["exit_code"] = 2
            return out

        out["ok"] = True
        out["exit_code"] = 0
        return out

    except Exception as ex:
        out["warnings"].append(f"StaticCheckError: {ex}")
        out["exit_code"] = 4
        return out
