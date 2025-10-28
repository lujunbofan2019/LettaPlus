import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_MANIFEST_API_VERSION = "v2.0.0"
DEFAULT_CATALOG_FILENAME = "skills_catalog.json"


def csv_to_manifests(skills_csv_path: str = "skills_src/skills.csv",
                     refs_csv_path: str = "skills_src/skill_tool_refs.csv",
                     out_dir: str = "generated/manifests",
                     catalog_path: str = "generated/catalogs/skills_catalog.json") -> Dict[str, Any]:
    """
    Generate Skill Manifests (v2.0.0) from local CSV files, suitable for rapid skill prototyping.

    CSV inputs (no external dependencies):
      1) skills_csv_path (default: skills_src/skills.csv)
         Columns:
           - manifestId (required)
           - skillName (required)
           - skillVersion (required)
           - description
           - tags                 (comma-separated list, NOT JSON)
           - permissions.egress   (none|intranet|internet)
           - permissions.secrets  (JSON array, e.g. ["API_KEY"])
           - skillDirectives
           - dataSources.json     (JSON array of requiredDataSources)

      2) refs_csv_path (default: skills_src/skill_tool_refs.csv)
         Maps skills to logical MCP tools (no concrete endpoints here - those are resolved at load-time):
           - manifestId (required)
           - serverId   (logical MCP server id, required)
           - toolName   (required)
           - required   ("true"/"false"; default true)
           - notes      (free text; ignored by generator, kept only for authoring)

    Outputs:
      - One manifest JSON per skill at: {out_dir}/{manifestId}.json
      - A compact catalog at: catalog_path
        {
          "skills": [
            {"manifestId": "...", "skillName": "...", "skillVersion": "...", "path": "..."},
            ...
          ]
        }

    Return:
      {
        "ok": bool,
        "exit_code": int,           # 0 ok, 4 error
        "status": str or None,
        "error": str or None,
        "written_files": [str],     # all paths written
        "manifests": [              # summary of each manifest created
          {
            "manifestId": str,
            "skillName": str,
            "skillVersion": str,
            "path": str
          }
        ],
        "warnings": [str]
      }

    Notes:
      - The generated requiredTools entries use {"definition": {"type": "mcp_server", "serverId": "<id>", "toolName": "<name>"}}.
        At runtime, your skill loader's resolver maps serverId -> transport/endpoint (stub vs real).
      - This tool is side-effect free outside the target output paths; it will create missing directories.
    """
    out: Dict[str, Any] = {
        "ok": False,
        "exit_code": 4,
        "status": None,
        "error": None,
        "written_files": [],
        "manifests": [],
        "warnings": []
    }

    # --- helpers -------------------------------------------------------------
    def _safe_filename(s: str) -> str:
        """
        Convert an arbitrary manifestId into a safe, flat filename.
        - Replaces path separators with underscores.
        - Keeps only [A-Za-z0-9._-]; collapses other runs to '-'.
        - Strips leading/trailing dots/underscores/dashes.
        """
        s = (s or "").replace("/", "_").replace("\\", "_")
        s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-_.")
        return s or "manifest"

    def _ensure_under_dir(base: Path, p: Path) -> Path:
        """
        Ensure resolved path p is within resolved base directory.
        Raises ValueError if the path escapes.
        """
        base_res = base.resolve()
        p_res = p.resolve()
        try:
            p_res.relative_to(base_res)
        except ValueError:
            raise ValueError(f"Refusing to write outside of output dir: {p_res} (base {base_res})")
        return p_res
    # -------------------------------------------------------------------------

    try:
        skills_csv = Path(skills_csv_path)
        refs_csv = Path(refs_csv_path)
        out_dir_p = Path(out_dir).resolve()
        catalog_p = Path(catalog_path) if catalog_path else Path(DEFAULT_CATALOG_FILENAME)

        # Allow callers to pass a directory-like catalog path (e.g. "generated/catalogs/" or ".")
        if catalog_path:
            if catalog_p.is_dir() or str(catalog_path).endswith("/") or catalog_p.suffix == "":
                catalog_p = (catalog_p / DEFAULT_CATALOG_FILENAME)
        else:
            catalog_p = Path(DEFAULT_CATALOG_FILENAME)

        if not skills_csv.exists():
            out["error"] = f"skills CSV not found: {skills_csv}"
            return out
        if not refs_csv.exists():
            # Not fatal: allow skills with no tool refs; warn.
            out["warnings"].append(
                f"refs CSV not found: {refs_csv} (continuing; skills will have no requiredTools)"
            )

        out_dir_p.mkdir(parents=True, exist_ok=True)
        catalog_p.parent.mkdir(parents=True, exist_ok=True)

        # Helpers (inlined)
        def parse_json_cell(cell: Optional[str], default: Any) -> Any:
            text = (cell or "").strip()
            if not text:
                return default
            try:
                return json.loads(text)
            except Exception:
                return default

        def parse_tags_cell(cell: Optional[str]) -> List[str]:
            raw = (cell or "").strip()
            if not raw:
                return []
            return [t.strip() for t in raw.split(",") if t.strip()]

        def ensure_manifest_api_version(row: Dict[str, Any]) -> str:
            raw = (row.get("manifestApiVersion") or "").strip()
            return raw or DEFAULT_MANIFEST_API_VERSION

        def ensure_skill_package_id(row: Dict[str, Any]) -> Optional[str]:
            raw = (row.get("skillPackageId") or row.get("packageId") or "").strip()
            return raw or None

        # Load refs index
        refs_index: Dict[str, List[Dict[str, Any]]] = {}
        if refs_csv.exists():
            with refs_csv.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    mid = (row.get("manifestId") or "").strip()
                    if not mid:
                        continue
                    refs_index.setdefault(mid, []).append({
                        "serverId": (row.get("serverId") or "").strip(),
                        "toolName": (row.get("toolName") or "").strip(),
                        "required": ((row.get("required") or "true").strip().lower() == "true"),
                        "description": (row.get("notes") or row.get("description") or "").strip(),
                        "schema": parse_json_cell(row.get("json_schema"), None)
                    })

        # Process skills
        catalog = {"skills": []}

        with skills_csv.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                manifest_id = (row.get("manifestId") or "").strip()
                name = (row.get("skillName") or "").strip()
                ver = (row.get("skillVersion") or "").strip()
                if not manifest_id or not name or not ver:
                    out["warnings"].append(f"Skipping row missing manifestId/skillName/skillVersion: {row}")
                    continue

                desc = (row.get("description") or "").strip() or None
                tags = parse_tags_cell(row.get("tags"))
                egress = (row.get("permissions.egress") or "none").strip()
                if egress not in ("none", "intranet", "internet"):
                    out["warnings"].append(f"permissions.egress invalid for {manifest_id}; defaulting to 'none'")
                    egress = "none"
                secrets = parse_json_cell(row.get("permissions.secrets"), [])
                directives = (row.get("skillDirectives") or "").strip()
                data_sources = parse_json_cell(row.get("dataSources.json"), [])

                # requiredTools from refs
                required_tools: List[Dict[str, Any]] = []
                for ref in refs_index.get(manifest_id, []):
                    sid = ref.get("serverId") or ""
                    tname = ref.get("toolName") or ""
                    if not sid or not tname:
                        continue
                    desc_text = ref.get("description") or f"Tool '{tname}' from server '{sid}'"
                    schema_obj = ref.get("schema")
                    if not isinstance(schema_obj, dict):
                        schema_obj = {
                            "name": tname,
                            "description": desc_text,
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "required": []
                            }
                        }
                    required_tools.append({
                        "toolName": tname,
                        "description": desc_text,
                        "json_schema": schema_obj,
                        "definition": {
                            "type": "mcp_server",
                            "serverId": sid,
                            "toolName": tname
                        },
                        "required": bool(ref.get("required"))
                    })

                manifest = {
                    "manifestApiVersion": ensure_manifest_api_version(row),
                    "manifestId": manifest_id,
                    "skillPackageId": ensure_skill_package_id(row),
                    "skillName": name,
                    "skillVersion": ver,
                    "description": desc,
                    "tags": tags,
                    "permissions": {
                        "egress": egress,
                        "secrets": secrets if isinstance(secrets, list) else []
                    },
                    "skillDirectives": directives,
                    "requiredTools": required_tools,
                    "requiredDataSources": data_sources if isinstance(data_sources, list) else []
                }

                # --- critical fix: sanitize filename and pin within out_dir ---
                safe_name = _safe_filename(manifest_id)
                if safe_name != manifest_id:
                    out["warnings"].append(
                        f"manifestId '{manifest_id}' contained path/unsafe characters; wrote as '{safe_name}.json'."
                    )

                out_path = _ensure_under_dir(out_dir_p, (out_dir_p / f"{safe_name}.json"))
                with out_path.open("w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, indent=2, ensure_ascii=False)

                out["written_files"].append(str(out_path))
                out["manifests"].append({
                    "manifestId": manifest_id,
                    "skillName": name,
                    "skillVersion": ver,
                    "path": str(out_path)
                })
                catalog["skills"].append({
                    "manifestId": manifest_id,
                    "skillName": name,
                    "skillVersion": ver,
                    "path": str(out_path)
                })

        with catalog_p.open("w", encoding="utf-8") as cf:
            json.dump(catalog, cf, indent=2, ensure_ascii=False)
        out["written_files"].append(str(catalog_p))

        out["ok"] = True
        out["exit_code"] = 0
        out["status"] = f"Wrote {len(out['manifests'])} skill manifests and catalog."
        return out

    except Exception as e:
        out["error"] = f"{e.__class__.__name__}: {e}"
        return out
