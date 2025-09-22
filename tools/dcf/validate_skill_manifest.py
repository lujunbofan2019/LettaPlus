import json
from jsonschema import Draft202012Validator

def validate_skill_manifest(skill_json, schema_path):
    """Validate a Skill Manifest (v2.0.0) and run static sanity checks.

      1) JSON Schema validation against the provided schema file.
      2) Static checks not easily expressed in JSON Schema (e.g., unique tool names).

    Args:
      skill_json: String containing the skill manifest JSON to validate.
      schema_path: Filesystem path to the skill manifest JSON Schema file.

    Returns:
      Dict with the following structure:
        {
          "ok": bool,
          "exit_code": int,              # 0 OK, 1 schema validation errors, 2 static validation errors, 4 other errors
          "schema_errors": [str],
          "static_errors": [str],
          "warnings": [str]
        }
    """
    out = {"ok": False, "exit_code": 4, "schema_errors": [], "static_errors": [], "warnings": []}

    # Parse instance
    try:
        inst = json.loads(skill_json)
    except Exception as ex:
        out["warnings"].append("JSONDecodeError: %s" % ex)
        out["exit_code"] = 4
        return out

    # Load schema
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as ex:
        out["warnings"].append("SchemaLoadError: %s" % ex)
        out["exit_code"] = 4
        return out

    # Schema validation
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(inst), key=lambda e: list(e.path))
        if errors:
            for e in errors:
                path = "/".join(map(str, e.path)) or "<root>"
                out["schema_errors"].append("%s: %s" % (path, e.message))
            out["exit_code"] = 1
            return out
    except Exception as ex:
        out["warnings"].append("SchemaValidationError: %s" % ex)
        out["exit_code"] = 4
        return out

    # Static checks
    try:
        # Unique toolName (case-insensitive) across requiredTools
        names = {}
        for i, tr in enumerate(inst.get("requiredTools") or []):
            name = (tr.get("toolName") or "").strip()
            if not name:
                out["static_errors"].append("requiredTools[%d].toolName must be a non-empty string" % i)
                continue
            key = name.lower()
            if key in names:
                out["static_errors"].append("Duplicate toolName (case-insensitive): '%s' at indexes %d and %d" % (name, names[key], i))
            else:
                names[key] = i

        # Permissions sanity
        perms = inst.get("permissions") or {}
        if "secrets" in perms and not isinstance(perms["secrets"], list):
            out["static_errors"].append("permissions.secrets must be an array of strings")

        if out["static_errors"]:
            out["exit_code"] = 2
            return out

        out["ok"] = True
        out["exit_code"] = 0
        return out
    except Exception as ex:
        out["warnings"].append("StaticCheckError: %s" % ex)
        out["exit_code"] = 4
        return out