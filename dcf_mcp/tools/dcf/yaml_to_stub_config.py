"""
Generate Stub MCP Server Configuration from YAML

This module processes the tools.yaml file and generates a stub_config.json
file that the stub MCP server can use for deterministic testing.

YAML files are expected to follow the tools/v1 schema defined in:
  skills_src/schemas/tools.schema.yaml
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

DEFAULT_STUB_CONFIG_FILENAME = "stub_config.json"

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


def yaml_to_stub_config(
    tools_yaml_path: str = "/app/skills_src/tools.yaml",
    out_path: str = "/app/generated/stub/stub_config.json"
) -> Dict[str, Any]:
    """
    Generate a deterministic stub MCP server configuration from tools.yaml.

    YAML Input (tools.yaml):
      apiVersion: tools/v1
      kind: ToolsRegistry
      servers:
        search:
          description: Search tools
          tools:
            search_query:
              version: 0.1.0
              description: Web search
              params: { type: object, properties: { q: { type: string } } }
              result: { ... }
              defaults:
                response: { hits: [] }
                latencyMs: 150
                rateLimit: { rps: 2 }
              cases:
                - id: case_python
                  match: { strategy: exact, path: q, value: python }
                  response: { hits: [...] }

    Output:
      Single JSON file at out_path with shape compatible with stub_mcp_server.py:
      {
        "servers": {
          "<serverId>": {
            "tools": {
              "<toolName>": {
                "version": "...",
                "description": "...",
                "paramsSchema": {...},
                "resultSchema": {...},
                "defaultResponse": {...},
                "rateLimit": {"rps": int},
                "latencyMs": {"default": int},
                "cases": [...]
              }
            }
          }
        }
      }

    Returns:
      {
        "ok": bool,
        "exit_code": int,
        "status": str or None,
        "error": str or None,
        "written_file": str or None,
        "tool_count": int,
        "case_count": int,
        "warnings": [str]
      }
    """
    out: Dict[str, Any] = {
        "ok": False,
        "exit_code": 4,
        "status": None,
        "error": None,
        "written_file": None,
        "tool_count": 0,
        "case_count": 0,
        "warnings": []
    }

    if yaml is None:
        out["error"] = "PyYAML not installed. Run: pip install pyyaml"
        return out

    try:
        tools_yaml_p = Path(tools_yaml_path)
        out_p = Path(out_path)

        # Handle directory-like output path
        if out_path:
            if out_p.is_dir() or str(out_path).endswith(("/", "\\")) or out_p.suffix == "":
                out_p = out_p / DEFAULT_STUB_CONFIG_FILENAME
        else:
            out_p = Path(DEFAULT_STUB_CONFIG_FILENAME)

        out_p.parent.mkdir(parents=True, exist_ok=True)

        if not tools_yaml_p.exists():
            out["error"] = f"tools.yaml not found: {tools_yaml_p}"
            return out

        # Load YAML
        with tools_yaml_p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Validate structure
        api_version = data.get("apiVersion", "")
        kind = data.get("kind", "")
        if api_version != "tools/v1" or kind != "ToolsRegistry":
            out["error"] = (
                f"Invalid tools.yaml: expected apiVersion=tools/v1, kind=ToolsRegistry; "
                f"got apiVersion={api_version}, kind={kind}"
            )
            return out

        servers: Dict[str, Any] = {}
        tool_count = 0
        case_count = 0

        yaml_servers = data.get("servers", {})
        for server_id, server_spec in yaml_servers.items():
            server_entry: Dict[str, Any] = {"tools": {}}
            servers[server_id] = server_entry

            yaml_tools = server_spec.get("tools", {})
            for tool_name_raw, tool_spec in yaml_tools.items():
                tool_name = _sanitize_tool_name(tool_name_raw)
                if tool_name != tool_name_raw:
                    out["warnings"].append(
                        f"Sanitized tool name '{tool_name_raw}' -> '{tool_name}' "
                        f"for server '{server_id}'"
                    )

                if tool_name in server_entry["tools"]:
                    out["error"] = (
                        f"Tool name collision for server '{server_id}': "
                        f"'{tool_name_raw}' conflicts with existing tool '{tool_name}'"
                    )
                    return out

                # Extract tool configuration
                defaults = tool_spec.get("defaults", {})
                default_response = defaults.get("response", {})
                default_latency = defaults.get("latencyMs", 100)
                rate_limit = defaults.get("rateLimit", {})
                rps = rate_limit.get("rps", 0) if isinstance(rate_limit, dict) else 0

                entry = {
                    "version": tool_spec.get("version", "0.1.0"),
                    "description": tool_spec.get("description", ""),
                    "paramsSchema": tool_spec.get("params", {"type": "object", "properties": {}}),
                    "resultSchema": tool_spec.get("result", {}),
                    "defaultResponse": default_response,
                    "rateLimit": {"rps": rps},
                    "latencyMs": {"default": default_latency},
                    "cases": [],
                    "meta": {"originalToolName": tool_name_raw}
                }

                # Process test cases
                for case_entry in tool_spec.get("cases", []):
                    case_id = case_entry.get("id", "")
                    match_spec = case_entry.get("match", {})

                    # Convert match specification
                    strategy = match_spec.get("strategy", "exact")
                    path = match_spec.get("path", "")
                    value = match_spec.get("value", "")

                    # Handle 'always' strategy
                    if strategy == "always":
                        expr = ""
                        match_value = ""
                    else:
                        # Convert path to JSONPath-like expression for compatibility
                        expr = f"$.{path}" if path and not path.startswith("$") else path
                        match_value = value

                    # Handle latency override
                    latency_override = case_entry.get("latencyMsOverride")

                    # Handle error mode and flaky rate
                    error_mode = case_entry.get("errorMode")
                    flaky_rate = case_entry.get("flakyRate")

                    # Handle weight
                    weight = case_entry.get("weight")

                    case_obj = {
                        "caseId": case_id,
                        "match": {
                            "strategy": strategy,
                            "expr": expr,
                            "value": str(match_value) if match_value is not None else ""
                        },
                        "response": case_entry.get("response", {}),
                        "responseTemplate": case_entry.get("responseTemplate"),
                        "latencyMsOverride": latency_override,
                        "errorMode": error_mode,
                        "flakyRate": flaky_rate,
                        "weight": weight
                    }

                    entry["cases"].append(case_obj)
                    case_count += 1

                server_entry["tools"][tool_name] = entry
                tool_count += 1

        config = {"servers": servers}

        # Write atomically
        tmp_path = out_p.with_suffix(out_p.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(out_p)

        out["written_file"] = str(out_p)
        out["tool_count"] = tool_count
        out["case_count"] = case_count
        out["ok"] = True
        out["exit_code"] = 0
        out["status"] = f"Wrote stub config for {tool_count} tool(s) and {case_count} case(s)."
        return out

    except Exception as e:
        out["error"] = f"{e.__class__.__name__}: {e}"
        return out
