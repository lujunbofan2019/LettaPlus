# file: skill_discovery_tool.py
import os
import json
from pathlib import Path

# --- Constants ---
DCF_MANIFESTS_DIR = os.getenv("DCF_MANIFESTS_DIR", "/app/dcf_manifests/")
DEFAULT_PREVIEW_CHARS = int(os.getenv("SKILL_PREVIEW_CHARS", "400"))

def get_skillset(manifests_dir: str = None,
                 schema_path: str = None,
                 include_previews: bool = True,
                 preview_chars: int = None) -> dict:
    """Discover Skill Manifests from a directory and summarize their metadata.

    This tool scans a directory for JSON files, parses each as a Skill Manifest,
    optionally validates against a JSON Schema, and returns a lightweight catalog
    to assist planning agents with fast skill selection and referencing.
      - Schema validation requires `jsonschema`. If not installed, validation is skipped and a warning is returned.
      - The function is resilient to partially invalid JSON files; errors are captured per-manifest so discovery can proceed for the rest.
      - Aliases include: `name@version`, `skill://name@version`, `skill://packageId@version` (when present), and the raw `manifestId`.

    Args:
        manifests_dir (str, optional): Directory to scan. Defaults to env `DCF_MANIFESTS_DIR`.
            The directory must exist and be readable.
        schema_path (str, optional): Filesystem path to the Skill Manifest JSON Schema
            (e.g., `schemas/skill-manifest-v2.0.0.json`). If provided and `jsonschema`
            is installed, each manifest will be validated.
        include_previews (bool, optional): When True, include a short
            `directives_preview` for each skill to help the Planner choose without
            loading the full skill. Defaults to True.
        preview_chars (int, optional): Max characters for `directives_preview`.
            Defaults to env `SKILL_PREVIEW_CHARS` (400) when None.

    Returns:
        dict: Result object:
            {
              "ok": bool,
              "exit_code": int,     # 0 ok, 4 error
              "available_skills": [
                {
                  "manifestId": str or None,
                  "skillPackageId": str or None,
                  "skillName": str or None,
                  "skillVersion": str or None,
                  "manifestApiVersion": str or None,
                  "aliases": [str],
                  "description": str or None,
                  "tags": [str],
                  "permissions": {"egress": "none"|"intranet"|"internet", "secrets": [str]},
                  "toolNames": [str],
                  "toolCount": int,
                  "dataSourceCount": int,
                  "directives_preview": str or None,   # present when include_previews=True
                  "path": str,                          # absolute path to the manifest file
                  "valid_schema": bool or None,         # None if schema validation skipped
                  "errors": [str],                      # per-manifest errors (non-fatal overall)
                  "warnings": [str]                     # per-manifest warnings
                }
              ],
              "warnings": [str],       # global warnings
              "error": str or None     # fatal error string or None on success
            }
    """
    out = {
        "ok": False,
        "exit_code": 4,
        "available_skills": [],
        "warnings": [],
        "error": None
    }

    # Resolve inputs and basic checks
    base_dir = manifests_dir or DCF_MANIFESTS_DIR
    try:
        preview_len = int(preview_chars) if preview_chars is not None else DEFAULT_PREVIEW_CHARS
    except Exception:
        preview_len = DEFAULT_PREVIEW_CHARS

    if manifests_dir is not None and not isinstance(manifests_dir, str):
        out["error"] = "TypeError: manifests_dir must be a string path or None"
        return out
    if schema_path is not None and not isinstance(schema_path, str):
        out["error"] = "TypeError: schema_path must be a string path or None"
        return out
    if not isinstance(include_previews, bool):
        out["error"] = "TypeError: include_previews must be a boolean"
        return out

    # Verify directory
    try:
        p = Path(base_dir)
        if not p.is_dir():
            raise FileNotFoundError("Manifest directory '%s' not found or not a directory." % base_dir)
    except Exception as ex:
        out["error"] = str(ex)
        return out

    # Optional schema load
    do_schema = False
    validator = None
    if schema_path:
        try:
            from jsonschema import Draft202012Validator
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            validator = Draft202012Validator(schema)
            do_schema = True
        except ImportError:
            out["warnings"].append("jsonschema not installed; skipping schema validation.")
        except Exception as ex:
            out["warnings"].append("Failed to load schema '%s': %s" % (schema_path, ex))

    # Scan *.json
    try:
        files = sorted(p.glob("*.json"))
    except Exception as ex:
        out["error"] = "Failed to scan directory: %s" % ex
        return out

    for fp in files:
        item = {
            "manifestId": None,
            "skillPackageId": None,
            "skillName": None,
            "skillVersion": None,
            "manifestApiVersion": None,
            "aliases": [],
            "description": None,
            "tags": [],
            "permissions": {"egress": "none", "secrets": []},
            "toolNames": [],
            "toolCount": 0,
            "dataSourceCount": 0,
            "directives_preview": None,
            "path": str(fp.resolve()),
            "valid_schema": None,
            "errors": [],
            "warnings": []
        }

        # Parse JSON
        try:
            with open(fp, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as ex:
            item["errors"].append("JSONDecodeError: %s" % ex)
            out["available_skills"].append(item)
            continue

        # Schema validation if enabled
        if do_schema and validator is not None:
            try:
                errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
                if errs:
                    item["valid_schema"] = False
                    for e in errs:
                        path = "/".join(map(str, e.path)) or "<root>"
                        item["errors"].append("%s: %s" % (path, e.message))
                else:
                    item["valid_schema"] = True
            except Exception as ex:
                item["valid_schema"] = False
                item["errors"].append("SchemaValidationError: %s" % ex)

        # Minimal key extraction (inline, no helpers)
        v = doc.get("manifestId"); item["manifestId"] = v if isinstance(v, str) else None
        v = doc.get("skillPackageId"); item["skillPackageId"] = v if isinstance(v, str) else None
        v = doc.get("skillName"); item["skillName"] = v if isinstance(v, str) else None
        v = doc.get("skillVersion"); item["skillVersion"] = v if isinstance(v, str) else None
        v = doc.get("manifestApiVersion"); item["manifestApiVersion"] = v if isinstance(v, str) else None
        v = doc.get("description"); item["description"] = v if isinstance(v, str) else None

        tags = doc.get("tags") or []
        if isinstance(tags, list):
            item["tags"] = [t for t in tags if isinstance(t, str)]

        perms = doc.get("permissions") or {}
        if isinstance(perms, dict):
            eg = perms.get("egress")
            if eg in ("none", "intranet", "internet"):
                item["permissions"]["egress"] = eg
            secrets = perms.get("secrets")
            if isinstance(secrets, list):
                item["permissions"]["secrets"] = [s for s in secrets if isinstance(s, str)]

        tools = doc.get("requiredTools") or []
        if isinstance(tools, list):
            for t in tools:
                if isinstance(t, dict):
                    tn = t.get("toolName")
                    if isinstance(tn, str) and tn:
                        item["toolNames"].append(tn)
            item["toolCount"] = len([t for t in tools if isinstance(t, dict)])

        dsrc = doc.get("requiredDataSources") or []
        if isinstance(dsrc, list):
            item["dataSourceCount"] = len([d for d in dsrc if isinstance(d, dict)])

        if include_previews:
            directives = doc.get("skillDirectives")
            if isinstance(directives, str) and directives:
                preview = directives.strip().replace("\n", " ").replace("\r", " ")
                if len(preview) > preview_len:
                    preview = preview[:preview_len].rstrip() + "…"
                item["directives_preview"] = preview

        # Basic required checks
        missing = []
        if not item["manifestId"]: missing.append("manifestId")
        if not item["skillName"]: missing.append("skillName")
        if not item["skillVersion"]: missing.append("skillVersion")
        if missing:
            item["errors"].append("Missing required fields: %s" % ", ".join(missing))

        # Aliases (inline, no helpers)
        name = (item["skillName"] or "").lower()
        ver = item["skillVersion"] or ""
        pkg = item["skillPackageId"] or ""
        if name and ver:
            item["aliases"].append("%s@%s" % (name, ver))
            item["aliases"].append("skill://%s@%s" % (name, ver))
        if pkg and ver:
            item["aliases"].append("skill://%s@%s" % (pkg, ver))
        if item["manifestId"]:
            item["aliases"].append(item["manifestId"])

        out["available_skills"].append(item)

    # Sort for stable UX (inline lambda, no helper)
    out["available_skills"].sort(
        key=lambda x: ((x.get("skillName") or "").lower(),
                       (x.get("skillVersion") or ""),
                       (x.get("manifestId") or "")))
    out["ok"] = True
    out["exit_code"] = 0
    return out
