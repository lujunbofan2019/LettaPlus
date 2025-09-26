import json

def validate_skill_manifest(skill_json: str, schema_path: str) -> dict:
    """Validate a Skill Manifest (v2.0.0) and run static sanity checks.

    Steps:
      1) JSON Schema validation against the provided schema file.
      2) Static checks (e.g., unique tool names).

    Args:
      skill_json: String containing the skill manifest JSON to validate.
      schema_path: Filesystem path to the skill manifest JSON Schema file.

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

    # Parse instance
    try:
        inst = json.loads(skill_json)
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
