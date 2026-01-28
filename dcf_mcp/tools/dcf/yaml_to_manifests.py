"""
Generate Skill Manifests from YAML Files

This module processes YAML skill definitions and generates JSON manifests
compatible with the DCF skill loading system.

YAML files are expected to follow the skill/v1 schema defined in:
  skills_src/schemas/skill.schema.yaml
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

DEFAULT_MANIFEST_API_VERSION = "v2.0.0"
DEFAULT_CATALOG_FILENAME = "skills_catalog.json"

_VALID_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _sanitize_tool_name(name: str) -> str:
    """Return a legal MCP tool identifier, replacing illegal characters."""
    name = (name or "").strip()
    if _VALID_TOOL_NAME_RE.fullmatch(name):
        return name

    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        sanitized = "tool"
    return sanitized


def _safe_filename(s: str) -> str:
    """Convert an arbitrary manifestId into a safe, flat filename."""
    s = (s or "").replace("/", "_").replace("\\", "_").replace("@", "-")
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-_.")
    return s or "manifest"


def _ensure_under_dir(base: Path, p: Path) -> Path:
    """Ensure resolved path p is within resolved base directory."""
    base_res = base.resolve(strict=False)
    p_res = p.resolve(strict=False)
    try:
        p_res.relative_to(base_res)
    except ValueError:
        raise ValueError(f"Refusing to write outside of output dir: {p_res} (base {base_res})")
    return p_res


def _parse_tool_ref(ref: str) -> tuple[str, str]:
    """Parse a tool reference in 'serverId:toolName' format."""
    if ":" not in ref:
        raise ValueError(f"Invalid tool ref format '{ref}'; expected 'serverId:toolName'")
    parts = ref.split(":", 1)
    return parts[0].strip(), parts[1].strip()


def _load_tools_yaml(tools_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load tools.yaml and build an index of tool schemas.
    Returns: {(serverId, toolName): tool_spec}
    """
    if not tools_path.exists():
        return {}

    with tools_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    index: Dict[tuple, Dict[str, Any]] = {}
    servers = data.get("servers", {})

    for server_id, server_spec in servers.items():
        tools = server_spec.get("tools", {})
        for tool_name, tool_spec in tools.items():
            index[(server_id, tool_name)] = tool_spec

    return index


def yaml_to_manifests(
    skills_dir: str = "/app/skills_src/skills",
    tools_yaml_path: str = "/app/skills_src/tools.yaml",
    out_dir: str = "/app/generated/manifests",
    catalog_path: str = "/app/generated/catalogs/skills_catalog.json"
) -> Dict[str, Any]:
    """
    Generate Skill Manifests (v2.0.0) from YAML skill definition files.

    YAML Inputs:
      1) skills_dir - Directory containing *.skill.yaml files
         Each file defines one skill with structure:
           apiVersion: skill/v1
           kind: Skill
           metadata:
             manifestId: skill.research.web@0.1.0
             name: research.web
             version: 0.1.0
             description: ...
             tags: [...]
           spec:
             permissions:
               egress: internet
               secrets: [API_KEY]
             directives: |
               Multi-line directives...
             tools:
               - ref: serverId:toolName
                 required: true
             dataSources:
               - id: source_id
                 text: Content...

      2) tools_yaml_path - Path to tools.yaml containing tool schemas
         Used to enrich requiredTools with proper JSON schemas.

    Outputs:
      - One manifest JSON per skill at: {out_dir}/{manifestId}.json
      - A compact catalog at: catalog_path

    Returns:
      {
        "ok": bool,
        "exit_code": int,
        "status": str or None,
        "error": str or None,
        "written_files": [str],
        "manifests": [{manifestId, skillName, skillVersion, path}],
        "warnings": [str]
      }
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

    if yaml is None:
        out["error"] = "PyYAML not installed. Run: pip install pyyaml"
        return out

    try:
        skills_dir_p = Path(skills_dir)
        tools_yaml_p = Path(tools_yaml_path)
        out_dir_p = Path(out_dir)
        catalog_p = Path(catalog_path) if catalog_path else Path(DEFAULT_CATALOG_FILENAME)

        # Handle directory-like catalog path
        if catalog_path:
            if catalog_p.is_dir() or str(catalog_path).endswith("/") or catalog_p.suffix == "":
                catalog_p = catalog_p / DEFAULT_CATALOG_FILENAME

        if not skills_dir_p.exists():
            out["error"] = f"Skills directory not found: {skills_dir_p}"
            return out

        out_dir_p.mkdir(parents=True, exist_ok=True)
        catalog_p.parent.mkdir(parents=True, exist_ok=True)

        # Load tool schemas for enrichment
        tool_schemas = _load_tools_yaml(tools_yaml_p) if tools_yaml_p.exists() else {}

        # Find all skill YAML files
        skill_files = list(skills_dir_p.glob("*.skill.yaml"))
        if not skill_files:
            out["warnings"].append(f"No *.skill.yaml files found in {skills_dir_p}")

        catalog = {"skills": []}

        for skill_file in sorted(skill_files):
            try:
                with skill_file.open("r", encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f) or {}
            except Exception as e:
                out["warnings"].append(f"Failed to parse {skill_file.name}: {e}")
                continue

            # Validate structure
            api_version = skill_data.get("apiVersion", "")
            kind = skill_data.get("kind", "")
            if api_version != "skill/v1" or kind != "Skill":
                out["warnings"].append(
                    f"Skipping {skill_file.name}: invalid apiVersion/kind "
                    f"(got {api_version}/{kind}, expected skill/v1/Skill)"
                )
                continue

            metadata = skill_data.get("metadata", {})
            spec = skill_data.get("spec", {})

            manifest_id = metadata.get("manifestId", "").strip()
            skill_name = metadata.get("name", "").strip()
            skill_version = metadata.get("version", "").strip()

            if not manifest_id or not skill_name or not skill_version:
                out["warnings"].append(
                    f"Skipping {skill_file.name}: missing manifestId, name, or version"
                )
                continue

            description = metadata.get("description") or None
            tags = metadata.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            # Permissions
            permissions = spec.get("permissions", {})
            egress = permissions.get("egress", "none")
            if egress not in ("none", "intranet", "internet"):
                out["warnings"].append(
                    f"Invalid egress '{egress}' in {skill_file.name}; defaulting to 'none'"
                )
                egress = "none"
            secrets = permissions.get("secrets", [])
            if not isinstance(secrets, list):
                secrets = []

            # Directives
            directives = spec.get("directives", "").strip()

            # Process tools
            required_tools: List[Dict[str, Any]] = []
            for tool_entry in spec.get("tools", []):
                ref = tool_entry.get("ref", "").strip()
                if not ref:
                    continue

                try:
                    server_id, tool_name_raw = _parse_tool_ref(ref)
                except ValueError as e:
                    out["warnings"].append(f"Invalid tool ref in {skill_file.name}: {e}")
                    continue

                tool_name = _sanitize_tool_name(tool_name_raw)
                if tool_name != tool_name_raw:
                    out["warnings"].append(
                        f"Sanitized tool name '{tool_name_raw}' -> '{tool_name}' "
                        f"in {skill_file.name}"
                    )

                tool_desc = tool_entry.get("description", "") or f"Tool '{tool_name}' from server '{server_id}'"
                is_required = tool_entry.get("required", True)

                # Try to get schema from tools.yaml
                tool_spec = tool_schemas.get((server_id, tool_name)) or tool_schemas.get((server_id, tool_name_raw))
                if tool_spec:
                    params_schema = tool_spec.get("params", {"type": "object", "properties": {}})
                    tool_desc_from_spec = tool_spec.get("description", "")
                    schema_obj = {
                        "name": tool_name,
                        "description": tool_desc_from_spec or tool_desc,
                        "parameters": params_schema
                    }
                else:
                    schema_obj = {
                        "name": tool_name,
                        "description": tool_desc,
                        "parameters": {"type": "object", "properties": {}, "required": []}
                    }

                required_tools.append({
                    "toolName": tool_name,
                    "description": tool_desc,
                    "json_schema": schema_obj,
                    "definition": {
                        "type": "mcp_server",
                        "serverId": server_id,
                        "toolName": tool_name
                    },
                    "required": bool(is_required)
                })

            # Process data sources
            data_sources: List[Dict[str, Any]] = []
            for ds_entry in spec.get("dataSources", []):
                ds_id = ds_entry.get("id", "").strip()
                if not ds_id:
                    continue

                ds_obj: Dict[str, Any] = {
                    "dataSourceId": ds_id,
                    "description": ds_entry.get("description"),
                    "destination": ds_entry.get("destination", "archival_memory")
                }

                # Handle text content
                if "text" in ds_entry:
                    ds_obj["content"] = {
                        "type": "text_content",
                        "text": ds_entry["text"]
                    }
                elif "file" in ds_entry:
                    # Read file content relative to skill file
                    file_path = skill_file.parent / ds_entry["file"]
                    if file_path.exists():
                        ds_obj["content"] = {
                            "type": "text_content",
                            "text": file_path.read_text(encoding="utf-8")
                        }
                    else:
                        out["warnings"].append(
                            f"Data source file not found: {file_path} in {skill_file.name}"
                        )
                        continue

                data_sources.append(ds_obj)

            # Build manifest
            manifest = {
                "manifestApiVersion": DEFAULT_MANIFEST_API_VERSION,
                "manifestId": manifest_id,
                "skillPackageId": None,
                "skillName": skill_name,
                "skillVersion": skill_version,
                "description": description,
                "tags": tags,
                "permissions": {
                    "egress": egress,
                    "secrets": secrets
                },
                "skillDirectives": directives,
                "requiredTools": required_tools,
                "requiredDataSources": data_sources
            }

            # Write manifest
            safe_name = _safe_filename(manifest_id)
            if safe_name != manifest_id.replace("@", "-"):
                out["warnings"].append(
                    f"manifestId '{manifest_id}' contained unsafe characters; wrote as '{safe_name}.json'"
                )

            out_path = _ensure_under_dir(out_dir_p, out_dir_p / f"{safe_name}.json")
            with out_path.open("w", encoding="utf-8") as mf:
                json.dump(manifest, mf, indent=2, ensure_ascii=False)

            try:
                manifest_path_for_catalog = out_path.relative_to(Path.cwd()).as_posix()
            except ValueError:
                manifest_path_for_catalog = out_path.as_posix()

            out["written_files"].append(str(out_path))
            out["manifests"].append({
                "manifestId": manifest_id,
                "skillName": skill_name,
                "skillVersion": skill_version,
                "path": manifest_path_for_catalog
            })
            catalog["skills"].append({
                "manifestId": manifest_id,
                "skillName": skill_name,
                "skillVersion": skill_version,
                "path": manifest_path_for_catalog
            })

        # Write catalog
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
