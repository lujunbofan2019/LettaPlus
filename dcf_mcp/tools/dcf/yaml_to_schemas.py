"""
Schema YAML to JSON Generator

Converts human-friendly YAML schema documentation to machine-readable JSON Schema
files for use by validation tools.

Note: JSON Schema is fundamentally a JSON format. The YAML files in skills_src/schemas/
serve as human-readable documentation with extensive comments. This generator extracts
the JSON Schema equivalent for tools that require JSON format.

Usage:
    from dcf_mcp.tools.dcf.yaml_to_schemas import yaml_to_schemas

    result = yaml_to_schemas(
        schemas_yaml_dir="skills_src/schemas",
        out_dir="generated/schemas"
    )
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_SCHEMAS_YAML_DIR = os.getenv("SCHEMAS_YAML_DIR", "/app/skills_src/schemas")
DEFAULT_SCHEMAS_JSON_DIR = os.getenv("SCHEMAS_JSON_DIR", "/app/generated/schemas")


def yaml_to_schemas(
    schemas_yaml_dir: str = None,
    out_dir: str = None
) -> Dict[str, Any]:
    """
    Convert YAML schema files to JSON Schema format.

    For each .schema.yaml file that contains a valid JSON Schema structure,
    generates a corresponding .schema.json file.

    Args:
        schemas_yaml_dir: Directory containing source .schema.yaml files.
                         Defaults to /app/skills_src/schemas
        out_dir: Output directory for .schema.json files.
                 Defaults to /app/generated/schemas

    Returns:
        {
            "ok": bool,
            "status": str,
            "error": str or None,
            "written_files": [str],
            "skipped_files": [str],
            "warnings": [str]
        }
    """
    result: Dict[str, Any] = {
        "ok": False,
        "status": None,
        "error": None,
        "written_files": [],
        "skipped_files": [],
        "warnings": []
    }

    yaml_dir = Path(schemas_yaml_dir or DEFAULT_SCHEMAS_YAML_DIR)
    json_dir = Path(out_dir or DEFAULT_SCHEMAS_JSON_DIR)

    # Check for PyYAML
    try:
        import yaml
    except ImportError:
        result["error"] = "PyYAML not installed. Install with: pip install pyyaml"
        result["status"] = "Failed: missing dependency"
        return result

    # Check source directory exists
    if not yaml_dir.exists():
        result["error"] = f"Schema source directory not found: {yaml_dir}"
        result["status"] = "Failed: source directory not found"
        return result

    # Ensure output directory exists
    try:
        json_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        result["error"] = f"Failed to create output directory: {e}"
        result["status"] = "Failed: directory creation error"
        return result

    # Find all .schema.yaml files
    yaml_files = list(yaml_dir.glob("*.schema.yaml"))
    if not yaml_files:
        result["ok"] = True
        result["status"] = "No .schema.yaml files found"
        return result

    for yaml_path in yaml_files:
        # Determine output filename
        # skill.schema.yaml -> skill.schema.json
        json_filename = yaml_path.stem + ".json"  # .stem removes .yaml, keeps .schema
        json_path = json_dir / json_filename

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            result["warnings"].append(f"Could not read {yaml_path.name}: {e}")
            result["skipped_files"].append(str(yaml_path))
            continue

        try:
            data = yaml.safe_load(content)
        except Exception as e:
            result["warnings"].append(f"Invalid YAML in {yaml_path.name}: {e}")
            result["skipped_files"].append(str(yaml_path))
            continue

        if not isinstance(data, dict):
            result["warnings"].append(f"{yaml_path.name} is not a valid schema (not a dict)")
            result["skipped_files"].append(str(yaml_path))
            continue

        # Check if it looks like a JSON Schema (has $schema or type or properties)
        is_json_schema = any(key in data for key in ["$schema", "type", "properties", "$id"])
        if not is_json_schema:
            result["warnings"].append(
                f"{yaml_path.name} does not appear to be a JSON Schema (missing $schema/type/properties)"
            )
            result["skipped_files"].append(str(yaml_path))
            continue

        # Write JSON Schema
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            result["written_files"].append(str(json_path))
        except Exception as e:
            result["warnings"].append(f"Failed to write {json_path.name}: {e}")
            result["skipped_files"].append(str(yaml_path))

    result["ok"] = len(result["written_files"]) > 0 or len(yaml_files) == 0
    result["status"] = f"Generated {len(result['written_files'])} schema(s) from {len(yaml_files)} source(s)"

    return result
