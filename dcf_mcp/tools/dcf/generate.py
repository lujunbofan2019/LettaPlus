"""
Skill and Stub Configuration Generator

This module provides a single entry point for generating skill manifests
and stub MCP server configurations from YAML sources.

Usage:
    from dcf_mcp.tools.dcf.generate import generate_all

    # Generate everything
    result = generate_all()
"""

from pathlib import Path
from typing import Any, Dict, Optional

# Default paths
DEFAULT_SKILLS_SRC = "/app/skills_src"
DEFAULT_GENERATED = "/app/generated"


def generate_manifests(
    skills_src_dir: str = DEFAULT_SKILLS_SRC,
    out_dir: str = f"{DEFAULT_GENERATED}/manifests",
    catalog_path: str = f"{DEFAULT_GENERATED}/catalogs/skills_catalog.json"
) -> Dict[str, Any]:
    """
    Generate skill manifests from YAML skill definition files.

    Args:
        skills_src_dir: Directory containing source files
        out_dir: Output directory for manifests
        catalog_path: Path for skills catalog

    Returns:
        Generation result with ok, status, error, written_files, etc.
    """
    from .yaml_to_manifests import yaml_to_manifests
    return yaml_to_manifests(
        skills_dir=f"{skills_src_dir}/skills",
        tools_yaml_path=f"{skills_src_dir}/tools.yaml",
        out_dir=out_dir,
        catalog_path=catalog_path
    )


def generate_stub_config(
    skills_src_dir: str = DEFAULT_SKILLS_SRC,
    out_path: str = f"{DEFAULT_GENERATED}/stub/stub_config.json"
) -> Dict[str, Any]:
    """
    Generate stub MCP server configuration from tools.yaml.

    Args:
        skills_src_dir: Directory containing source files
        out_path: Output path for stub config

    Returns:
        Generation result with ok, status, error, written_file, etc.
    """
    from .yaml_to_stub_config import yaml_to_stub_config
    return yaml_to_stub_config(
        tools_yaml_path=f"{skills_src_dir}/tools.yaml",
        out_path=out_path
    )


def generate_registry(
    skills_src_dir: str = DEFAULT_SKILLS_SRC,
    out_path: str = f"{DEFAULT_GENERATED}/registry.json"
) -> Dict[str, Any]:
    """
    Generate MCP server registry JSON from registry.yaml.

    Args:
        skills_src_dir: Directory containing source files
        out_path: Output path for registry.json

    Returns:
        Generation result with ok, status, error, written_file, server_count.
    """
    from .yaml_to_registry import yaml_to_registry
    return yaml_to_registry(
        registry_yaml_path=f"{skills_src_dir}/registry.yaml",
        out_path=out_path
    )


def generate_schemas(
    skills_src_dir: str = DEFAULT_SKILLS_SRC,
    out_dir: str = f"{DEFAULT_GENERATED}/schemas"
) -> Dict[str, Any]:
    """
    Generate JSON Schema files from YAML schema sources.

    Args:
        skills_src_dir: Directory containing source files
        out_dir: Output directory for JSON schemas

    Returns:
        Generation result with ok, status, error, written_files, etc.
    """
    from .yaml_to_schemas import yaml_to_schemas
    return yaml_to_schemas(
        schemas_yaml_dir=f"{skills_src_dir}/schemas",
        out_dir=out_dir
    )


def generate_all(
    skills_src_dir: str = DEFAULT_SKILLS_SRC,
    generated_dir: str = DEFAULT_GENERATED
) -> Dict[str, Any]:
    """
    Generate all artifacts: skill manifests, stub config, registry, and schemas.

    Args:
        skills_src_dir: Directory containing source files
        generated_dir: Base directory for generated output

    Returns:
        Combined result:
        {
            "ok": bool,
            "manifests_result": {...},
            "stub_config_result": {...},
            "registry_result": {...},
            "schemas_result": {...},
            "summary": str
        }
    """
    result: Dict[str, Any] = {
        "ok": False,
        "manifests_result": None,
        "stub_config_result": None,
        "registry_result": None,
        "schemas_result": None,
        "summary": None
    }

    # Generate manifests
    manifests_result = generate_manifests(
        skills_src_dir=skills_src_dir,
        out_dir=f"{generated_dir}/manifests",
        catalog_path=f"{generated_dir}/catalogs/skills_catalog.json"
    )
    result["manifests_result"] = manifests_result

    # Generate stub config
    stub_result = generate_stub_config(
        skills_src_dir=skills_src_dir,
        out_path=f"{generated_dir}/stub/stub_config.json"
    )
    result["stub_config_result"] = stub_result

    # Generate registry
    registry_result = generate_registry(
        skills_src_dir=skills_src_dir,
        out_path=f"{generated_dir}/registry.json"
    )
    result["registry_result"] = registry_result

    # Generate schemas
    schemas_result = generate_schemas(
        skills_src_dir=skills_src_dir,
        out_dir=f"{generated_dir}/schemas"
    )
    result["schemas_result"] = schemas_result

    # Determine overall success
    manifests_ok = manifests_result.get("ok", False)
    stub_ok = stub_result.get("ok", False)
    registry_ok = registry_result.get("ok", False)
    schemas_ok = schemas_result.get("ok", False)
    result["ok"] = manifests_ok and stub_ok and registry_ok and schemas_ok

    # Build summary
    manifest_count = len(manifests_result.get("manifests", []))
    tool_count = stub_result.get("tool_count", 0)
    case_count = stub_result.get("case_count", 0)
    server_count = registry_result.get("server_count", 0)
    schema_count = len(schemas_result.get("written_files", []))

    parts = []
    if manifests_ok:
        parts.append(f"{manifest_count} skill manifest(s)")
    else:
        parts.append(f"manifests FAILED: {manifests_result.get('error', 'unknown')}")

    if stub_ok:
        parts.append(f"{tool_count} tool(s) with {case_count} case(s)")
    else:
        parts.append(f"stub config FAILED: {stub_result.get('error', 'unknown')}")

    if registry_ok:
        parts.append(f"{server_count} MCP server(s)")
    else:
        parts.append(f"registry FAILED: {registry_result.get('error', 'unknown')}")

    if schemas_ok:
        parts.append(f"{schema_count} schema(s)")
    else:
        parts.append(f"schemas FAILED: {schemas_result.get('error', 'unknown')}")

    result["summary"] = "Generated: " + ", ".join(parts)

    return result


# Convenience function for CLI usage
def main():
    """CLI entry point for generation."""
    import os
    import sys
    import json

    # Get paths from environment or use defaults
    skills_src = os.environ.get("SKILLS_SRC_DIR", DEFAULT_SKILLS_SRC)
    generated = os.environ.get("GENERATED_DIR", DEFAULT_GENERATED)

    result = generate_all(
        skills_src_dir=skills_src,
        generated_dir=generated
    )

    print(json.dumps(result, indent=2))

    if result["ok"]:
        print(f"\n✓ {result['summary']}")
        sys.exit(0)
    else:
        print(f"\n✗ {result['summary']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
