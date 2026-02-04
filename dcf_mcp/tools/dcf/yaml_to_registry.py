"""
Registry YAML to JSON Generator

Converts the human-friendly registry.yaml to machine-readable registry.json
for use by load_skill.py when resolving MCP server endpoints.

Usage:
    from dcf_mcp.tools.dcf.yaml_to_registry import yaml_to_registry

    result = yaml_to_registry(
        registry_yaml_path="skills_src/registry.yaml",
        out_path="generated/registry.json"
    )
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULT_REGISTRY_YAML = os.getenv("REGISTRY_YAML_PATH", "/app/skills_src/registry.yaml")
DEFAULT_REGISTRY_JSON = os.getenv("REGISTRY_JSON_PATH", "/app/generated/registry.json")


def yaml_to_registry(
    registry_yaml_path: str = None,
    out_path: str = None
) -> Dict[str, Any]:
    """
    Convert registry.yaml to registry.json.

    Args:
        registry_yaml_path: Path to source registry.yaml file.
                           Defaults to /app/skills_src/registry.yaml
        out_path: Output path for registry.json.
                  Defaults to /app/generated/registry.json

    Returns:
        {
            "ok": bool,
            "status": str,
            "error": str or None,
            "written_file": str or None,
            "server_count": int
        }
    """
    result: Dict[str, Any] = {
        "ok": False,
        "status": None,
        "error": None,
        "written_file": None,
        "server_count": 0
    }

    yaml_path = registry_yaml_path or DEFAULT_REGISTRY_YAML
    json_path = out_path or DEFAULT_REGISTRY_JSON

    # Check for PyYAML
    try:
        import yaml
    except ImportError:
        result["error"] = "PyYAML not installed. Install with: pip install pyyaml"
        result["status"] = "Failed: missing dependency"
        return result

    # Check source file exists
    if not os.path.exists(yaml_path):
        result["error"] = f"Registry YAML not found: {yaml_path}"
        result["status"] = "Failed: source not found"
        return result

    # Load YAML
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        result["error"] = f"Failed to parse YAML: {e}"
        result["status"] = "Failed: YAML parse error"
        return result

    if not isinstance(data, dict):
        result["error"] = "Registry YAML must be a dictionary"
        result["status"] = "Failed: invalid format"
        return result

    # Convert to the expected JSON format
    # The YAML format is:
    #   servers:
    #     server_id:
    #       transport: streamable_http
    #       endpoint: http://...
    #       path: /mcp
    #
    # The JSON format expected by load_skill.py is the same structure
    registry_json: Dict[str, Any] = {"servers": {}}

    servers = data.get("servers") or {}
    for server_id, config in servers.items():
        if isinstance(config, dict):
            registry_json["servers"][server_id] = {
                "transport": config.get("transport", "streamable_http"),
                "endpoint": config.get("endpoint", ""),
                "path": config.get("path", "/mcp")
            }
            # Preserve any additional fields
            for key in config:
                if key not in ("transport", "endpoint", "path"):
                    registry_json["servers"][server_id][key] = config[key]

    result["server_count"] = len(registry_json["servers"])

    # Ensure output directory exists
    out_dir = Path(json_path).parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        result["error"] = f"Failed to create output directory: {e}"
        result["status"] = "Failed: directory creation error"
        return result

    # Write JSON
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(registry_json, f, indent=2)
    except Exception as e:
        result["error"] = f"Failed to write JSON: {e}"
        result["status"] = "Failed: write error"
        return result

    result["ok"] = True
    result["written_file"] = json_path
    result["status"] = f"Generated registry.json with {result['server_count']} server(s)"

    return result
