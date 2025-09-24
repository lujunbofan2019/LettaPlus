# file: skill_discovery_tool.py
import os
import json
from pathlib import Path

# --- Constants ---
DCF_MANIFESTS_DIR = os.getenv("DCF_MANIFESTS_DIR", "/app/dcf_manifests/")
DEFAULT_PREVIEW_CHARS = int(os.getenv("SKILL_PREVIEW_CHARS", "400"))

def get_skillset(manifests_dir=None, schema_path=None, include_previews=True, preview_chars=None):
    """Discover Skill Manifests from a directory and summarize their metadata.

    This tool scans a directory for JSON files, parses each as a Skill Manifest, optionally validates against a JSON Schema,
    and returns a lightweight catalog for agent planning and retrieval.

    Args:
      manifests_dir: Optional directory path to scan. Defaults to env DCF_MANIFESTS_DIR. The directory must exist and be readable.
      schema_path: Optional filesystem path to the Skill Manifest JSON Schema.
      include_previews: If True, include a short 'directives_preview' for each skill to help the Planner pick the right skill without loading it yet.
      preview_chars: Optional int to control the preview length.

    Returns:
      dict: {
        "ok": bool,
        "exit_code": int,     # 0 ok, 4 error
        "available_skills": [ # catalog entries, sorted by skillName then version
          {
            "manifestId": str,
            "skillPackageId": str or None,
            "skillName": str,
            "skillVersion": str,
            "aliases": [str],  # e.g., name@ver, skill://name@ver, skill://packageId@ver, manifestId
            "description": str or None,
            "tags": [str],
            "permissions": {
              "egress": "none"|"intranet"|"internet",
              "secrets": [str]
            },
            "toolNames": [str],
            "toolCount": int,
            "dataSourceCount": int,
            "directives_preview": str or None,  # present only when include_previews=True
            "path": str,        # absolute path to the manifest file
            "valid_schema": bool or None,  # None when schema_path not provided
            "errors": [str],    # per-manifest errors (non-fatal to the whole run)
            "warnings": [str]   # per-manifest warnings
          }
        ],
        "warnings": [str],      # global warnings
        "error": str or None    # fatal error string or None on success
      }
    """ % (DCF_MANIFESTS_DIR, DEFAULT_PREVIEW_CHARS)

    out = {
        "ok": False,
        "exit_code": 4,
        "available_skills": [],
        "warnings": [],
        "error": None
    }

    # Resolve inputs
    base_dir = manifests_dir or DCF_MANIFESTS_DIR
    preview_len = int(preview_chars) if preview_chars is not None else DEFAULT_PREVIEW_CHARS

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

        # Minimal key extraction (robust, even if schema invalid)
        def _str(v):
            return v if isinstance(v, str) else None

        item["manifestId"] = _str(doc.get("manifestId"))
        item["skillPackageId"] = _str(doc.get("skillPackageId"))
        item["skillName"] = _str(doc.get("skillName"))
        item["skillVersion"] = _str(doc.get("skillVersion"))
        item["description"] = _str(doc.get("description"))
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
                    tname = t.get("toolName")
                    if isinstance(tname, str) and tname:
                        item["toolNames"].append(tname)
            item["toolCount"] = len(tools)

        dsrc = doc.get("requiredDataSources") or []
        if isinstance(dsrc, list):
            item["dataSourceCount"] = len(dsrc)

        if include_previews:
            directives = doc.get("skillDirectives")
            if isinstance(directives, str) and directives:
                preview = directives.strip().replace("\n", " ").replace("\r", " ")
                if len(preview) > preview_len:
                    preview = preview[:preview_len].rstrip() + "…"
                item["directives_preview"] = preview

        # Basic required checks (manifestId, skillName, skillVersion)
        missing = []
        for k in ("manifestId", "skillName", "skillVersion"):
            if not item[k]:
                missing.append(k)
        if missing:
            item["errors"].append("Missing required fields: %s" % ", ".join(missing))

        # Aliases: name@ver, skill://name@ver, packageId@ver, manifestId
        name = item["skillName"] or ""
        ver = item["skillVersion"] or ""
        pkg = item["skillPackageId"] or ""
        if name and ver:
            item["aliases"].append("%s@%s" % (name.lower(), ver))
            item["aliases"].append("skill://%s@%s" % (name.lower(), ver))
        if pkg and ver:
            item["aliases"].append("skill://%s@%s" % (pkg, ver))
        if item["manifestId"]:
            item["aliases"].append(item["manifestId"])

        out["available_skills"].append(item)

    # Sort for stable UX
    def _sort_key(x):
        return ((x.get("skillName") or "").lower(), (x.get("skillVersion") or ""))
    out["available_skills"].sort(key=_sort_key)

    out["ok"] = True
    out["exit_code"] = 0
    return out
