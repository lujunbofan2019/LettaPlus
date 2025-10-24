# server.py
from mcp.server.fastmcp import FastMCP
from tools.dcf.get_skillset import get_skillset as _get_skillset
from tools.common.resolve_agent_name_to_id import resolve_agent_name_to_id as _resolve_agent_name_to_id

mcp = FastMCP(name="dcf-mcp-server")


@mcp.tool()
def resolve_agent_name_to_id(agent_name: str) -> dict:
    """
    Resolve an agent's name to its unique agent Id, often as a prerequisite for the agent to call other tools.

    Args:
        agent_name: The name of the agent to look up (case-sensitive).

    Returns:
        dict: {"agent_id": str | None, "error": str | None}
    """
    return _resolve_agent_name_to_id(agent_name=agent_name)


@mcp.tool()
def get_skillset(manifests_dir: str | None = None,
                 schema_path: str | None = None,
                 include_previews: bool = True,
                 preview_chars: int | None = None) -> dict:
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
    return _get_skillset(
        manifests_dir=manifests_dir,
        schema_path=schema_path,
        include_previews=include_previews,
        preview_chars=preview_chars,
    )


app = mcp.streamable_http_app()
