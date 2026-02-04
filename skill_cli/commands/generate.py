"""
Generate command implementation.

Generates JSON manifests from YAML skills and stub server configuration.
"""

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import (
    Colors,
    get_generated_dir,
    get_skills_dir,
    load_yaml_file,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)


def get_available_tools(tools_registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extract available tools from the registry.

    Returns a dict mapping "serverId:toolName" to tool definition.
    """
    tools = {}
    servers = tools_registry.get("servers", {})

    for server_id, server_data in servers.items():
        server_tools = server_data.get("tools", {})
        for tool_name, tool_def in server_tools.items():
            ref = f"{server_id}:{tool_name}"
            tools[ref] = {
                "serverId": server_id,
                "toolName": tool_name,
                **tool_def,
            }

    return tools


def transform_tool_ref(
    tool_ref: Dict[str, Any],
    available_tools: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Transform a YAML tool reference into JSON manifest format.

    YAML: { ref: "search:search_query", required: true }
    JSON: { definition: { type: "mcp_server", serverId: "search", toolName: "search_query" }, json_schema: {...} }
    """
    ref = tool_ref.get("ref", "")
    if not ref or ":" not in ref:
        return None

    server_id, tool_name = ref.split(":", 1)

    # Build definition
    result = {
        "definition": {
            "type": "mcp_server",
            "serverId": server_id,
            "toolName": tool_name,
        }
    }

    # Add json_schema if tool is in registry
    if ref in available_tools:
        tool_def = available_tools[ref]
        params = tool_def.get("params", {})
        if params:
            result["json_schema"] = params

    return result


def transform_data_source(ds: Dict[str, Any], skill_path: Path) -> Dict[str, Any]:
    """
    Transform a YAML data source into JSON manifest format.

    Handles both inline text and file references.
    """
    result = {}

    if ds.get("id"):
        result["id"] = ds["id"]

    if ds.get("description"):
        result["description"] = ds["description"]

    # Handle text content
    if "text" in ds:
        result["content"] = {
            "type": "text_content",
            "text": ds["text"],
        }
    elif "file" in ds:
        # Load file content
        file_path = skill_path.parent / ds["file"]
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                result["content"] = {
                    "type": "text_content",
                    "text": content,
                }
            except Exception as e:
                result["content"] = {
                    "type": "text_content",
                    "text": f"Error loading file: {e}",
                }
        else:
            result["content"] = {
                "type": "text_content",
                "text": f"File not found: {ds['file']}",
            }

    return result


def generate_manifest(
    skill_path: Path,
    available_tools: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate a JSON manifest from a YAML skill file.

    Transforms:
    - apiVersion/kind → manifestApiVersion
    - metadata.name → skillName
    - metadata.version → skillVersion
    - spec.directives → skillDirectives
    - spec.tools[].ref → tools[].definition + json_schema
    """
    data, error = load_yaml_file(skill_path)
    if error:
        return {"error": error}

    metadata = data.get("metadata", {})
    spec = data.get("spec", {})
    permissions = spec.get("permissions", {})

    manifest = {
        "$schema": "./skill_manifest_schema_v2.0.0.json",
        "manifestApiVersion": "v2.0.0",
        "manifestId": metadata.get("manifestId", ""),
        "skillName": metadata.get("name", ""),
        "skillVersion": metadata.get("version", ""),
        "description": metadata.get("description", ""),
        "tags": metadata.get("tags", []),
        "permissions": {
            "egress": permissions.get("egress", "none"),
            "secrets": permissions.get("secrets", []),
        },
        "skillDirectives": spec.get("directives", ""),
        "tools": [],
        "dataSources": [],
    }

    # Transform tools
    for tool_ref in spec.get("tools", []):
        transformed = transform_tool_ref(tool_ref, available_tools)
        if transformed:
            manifest["tools"].append(transformed)

    # Transform data sources
    for ds in spec.get("dataSources", []):
        transformed = transform_data_source(ds, skill_path)
        if transformed:
            manifest["dataSources"].append(transformed)

    return manifest


def generate_manifests(
    skills_dir: Path,
    generated_dir: Path,
    verbose: bool = False
) -> Dict[str, Any]:
    """Generate all skill manifests."""
    results = {
        "generated": [],
        "errors": [],
    }

    # Load tools registry
    tools_path = skills_dir / "tools.yaml"
    tools_registry, error = load_yaml_file(tools_path)
    if error:
        return {"error": f"Failed to load tools.yaml: {error}"}

    available_tools = get_available_tools(tools_registry)

    # Ensure output directory exists
    manifests_dir = generated_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    # Process each skill
    skills_path = skills_dir / "skills"
    if not skills_path.exists():
        return {"error": f"Skills directory not found: {skills_path}"}

    catalog = []

    for skill_path in sorted(skills_path.glob("*.skill.yaml")):
        manifest = generate_manifest(skill_path, available_tools)

        if "error" in manifest:
            results["errors"].append({
                "file": skill_path.name,
                "error": manifest["error"],
            })
            continue

        # Generate output filename
        manifest_id = manifest.get("manifestId", "").replace("@", "-")
        out_name = f"{manifest_id}.json"
        out_path = manifests_dir / out_name

        # Write manifest
        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            results["generated"].append({
                "skill": manifest.get("skillName"),
                "file": out_name,
            })

            # Add to catalog
            catalog.append({
                "manifestId": manifest.get("manifestId"),
                "skillName": manifest.get("skillName"),
                "skillVersion": manifest.get("skillVersion"),
                "description": manifest.get("description"),
                "tags": manifest.get("tags"),
                "file": out_name,
            })

            if verbose:
                print_success(f"Generated {out_name}")

        except Exception as e:
            results["errors"].append({
                "file": skill_path.name,
                "error": str(e),
            })

    # Write catalog
    catalogs_dir = generated_dir / "catalogs"
    catalogs_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = catalogs_dir / "skills_catalog.json"

    try:
        with catalog_path.open("w", encoding="utf-8") as f:
            json.dump({
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "skills": catalog,
            }, f, indent=2)

        results["catalog"] = str(catalog_path)
    except Exception as e:
        results["errors"].append({
            "file": "skills_catalog.json",
            "error": str(e),
        })

    return results


def generate_stub_config(
    skills_dir: Path,
    generated_dir: Path,
    verbose: bool = False
) -> Dict[str, Any]:
    """Generate stub MCP server configuration."""
    results = {
        "generated": None,
        "errors": [],
    }

    # Load tools registry
    tools_path = skills_dir / "tools.yaml"
    tools_registry, error = load_yaml_file(tools_path)
    if error:
        return {"error": f"Failed to load tools.yaml: {error}"}

    # Transform to stub config format
    stub_config = {
        "$schema": "stub_config_schema.json",
        "servers": {},
    }

    servers = tools_registry.get("servers", {})
    for server_id, server_data in servers.items():
        server_config = {
            "description": server_data.get("description", ""),
            "tools": {},
        }

        for tool_name, tool_def in server_data.get("tools", {}).items():
            tool_config = {
                "description": tool_def.get("description", ""),
                "inputSchema": tool_def.get("params", {}),
            }

            # Add defaults
            defaults = tool_def.get("defaults", {})
            if defaults:
                tool_config["defaults"] = defaults

            # Add cases
            cases = tool_def.get("cases", [])
            if cases:
                tool_config["cases"] = cases

            server_config["tools"][tool_name] = tool_config

        stub_config["servers"][server_id] = server_config

    # Ensure output directory exists
    stub_dir = generated_dir / "stub"
    stub_dir.mkdir(parents=True, exist_ok=True)

    out_path = stub_dir / "stub_config.json"

    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(stub_config, f, indent=2)

        results["generated"] = str(out_path)
        if verbose:
            print_success(f"Generated {out_path}")

    except Exception as e:
        results["errors"].append({
            "file": "stub_config.json",
            "error": str(e),
        })

    return results


def generate_registry(
    skills_dir: Path,
    generated_dir: Path,
    verbose: bool = False
) -> Dict[str, Any]:
    """Generate MCP server registry from registry.yaml."""
    results = {
        "generated": None,
        "errors": [],
        "server_count": 0,
    }

    # Load registry YAML
    registry_path = skills_dir / "registry.yaml"
    if not registry_path.exists():
        return {"error": f"registry.yaml not found at {registry_path}"}

    registry_data, error = load_yaml_file(registry_path)
    if error:
        return {"error": f"Failed to load registry.yaml: {error}"}

    if not isinstance(registry_data, dict):
        return {"error": "registry.yaml is not a valid YAML dictionary"}

    servers = registry_data.get("servers", {})
    results["server_count"] = len(servers)

    # Write registry.json
    out_path = generated_dir / "registry.json"
    generated_dir.mkdir(parents=True, exist_ok=True)

    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(registry_data, f, indent=2)

        results["generated"] = str(out_path)
        if verbose:
            print_success(f"Generated {out_path}")

    except Exception as e:
        results["errors"].append({
            "file": "registry.json",
            "error": str(e),
        })

    return results


def generate_schemas(
    skills_dir: Path,
    generated_dir: Path,
    verbose: bool = False
) -> Dict[str, Any]:
    """Generate JSON Schema files from YAML schema sources."""
    results = {
        "generated": [],
        "skipped": [],
        "errors": [],
    }

    # Check for schemas directory
    schemas_dir = skills_dir / "schemas"
    if not schemas_dir.exists():
        return {"error": f"Schemas directory not found: {schemas_dir}"}

    # Ensure output directory exists
    out_dir = generated_dir / "schemas"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Process each .schema.yaml file
    for yaml_path in sorted(schemas_dir.glob("*.schema.yaml")):
        # Load YAML
        data, error = load_yaml_file(yaml_path)
        if error:
            results["errors"].append({
                "file": yaml_path.name,
                "error": error,
            })
            continue

        if not isinstance(data, dict):
            results["skipped"].append({
                "file": yaml_path.name,
                "reason": "Not a valid dictionary",
            })
            continue

        # Check if it looks like a JSON Schema
        is_json_schema = any(key in data for key in ["$schema", "type", "properties", "$id"])
        if not is_json_schema:
            results["skipped"].append({
                "file": yaml_path.name,
                "reason": "Not a JSON Schema (missing $schema/type/properties)",
            })
            continue

        # Generate output filename: skill.authoring.schema.yaml -> skill.authoring.schema.json
        json_filename = yaml_path.stem + ".json"  # .stem removes .yaml
        out_path = out_dir / json_filename

        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            results["generated"].append({
                "source": yaml_path.name,
                "output": json_filename,
            })

            if verbose:
                print_success(f"Generated {out_path}")

        except Exception as e:
            results["errors"].append({
                "file": yaml_path.name,
                "error": str(e),
            })

    return results


def clean_generated(generated_dir: Path, verbose: bool = False) -> int:
    """Clean the generated directory."""
    if not generated_dir.exists():
        return 0

    count = 0
    for subdir in ["manifests", "catalogs", "stub", "schemas"]:
        path = generated_dir / subdir
        if path.exists():
            for f in path.glob("*"):
                if f.is_file():
                    f.unlink()
                    count += 1
                    if verbose:
                        print_info(f"Removed {f}")

    # Also clean registry.json at root level
    registry_path = generated_dir / "registry.json"
    if registry_path.exists():
        registry_path.unlink()
        count += 1
        if verbose:
            print_info(f"Removed {registry_path}")

    return count


def run_generate(args) -> int:
    """
    Run the generate command.

    Returns exit code (0 for success, non-zero for failure).
    """
    skills_dir = get_skills_dir(args)
    generated_dir = get_generated_dir(args)

    if not skills_dir.exists():
        print_error(f"Skills directory not found: {skills_dir}")
        return 1

    # Clean if requested
    if args.clean:
        count = clean_generated(generated_dir, args.verbose > 0)
        if not args.quiet:
            print_info(f"Cleaned {count} files from {generated_dir}")

    # Determine what to generate
    generate_manifests_flag = not args.stub_only
    generate_stub_flag = not args.manifests_only

    total_errors = 0

    if generate_manifests_flag:
        if not args.quiet:
            print_header("Generating skill manifests")

        result = generate_manifests(skills_dir, generated_dir, args.verbose > 0)

        if "error" in result:
            print_error(result["error"])
            return 1

        if result.get("errors"):
            for err in result["errors"]:
                print_error(f"{err['file']}: {err['error']}")
            total_errors += len(result["errors"])

        if not args.quiet:
            count = len(result.get("generated", []))
            print_success(f"Generated {count} manifests")
            if result.get("catalog"):
                print_info(f"Catalog: {result['catalog']}")

    if generate_stub_flag:
        if not args.quiet:
            print_header("Generating stub configuration")

        result = generate_stub_config(skills_dir, generated_dir, args.verbose > 0)

        if "error" in result:
            print_error(result["error"])
            return 1

        if result.get("errors"):
            for err in result["errors"]:
                print_error(f"{err['file']}: {err['error']}")
            total_errors += len(result["errors"])

        if not args.quiet and result.get("generated"):
            print_success(f"Generated {result['generated']}")

    # Generate registry (always, unless stub_only or manifests_only)
    if not args.stub_only and not args.manifests_only:
        if not args.quiet:
            print_header("Generating MCP registry")

        result = generate_registry(skills_dir, generated_dir, args.verbose > 0)

        if "error" in result:
            print_warning(result["error"])  # Non-fatal - registry.yaml may not exist
        elif result.get("errors"):
            for err in result["errors"]:
                print_error(f"{err['file']}: {err['error']}")
            total_errors += len(result["errors"])
        elif not args.quiet and result.get("generated"):
            print_success(f"Generated {result['generated']} ({result.get('server_count', 0)} servers)")

    # Generate schemas (always, unless stub_only or manifests_only)
    if not args.stub_only and not args.manifests_only:
        if not args.quiet:
            print_header("Generating JSON schemas")

        result = generate_schemas(skills_dir, generated_dir, args.verbose > 0)

        if "error" in result:
            print_warning(result["error"])  # Non-fatal - schemas may not exist
        elif result.get("errors"):
            for err in result["errors"]:
                print_error(f"{err['file']}: {err['error']}")
            total_errors += len(result["errors"])
        else:
            generated_count = len(result.get("generated", []))
            skipped_count = len(result.get("skipped", []))
            if not args.quiet:
                if generated_count > 0:
                    print_success(f"Generated {generated_count} schema(s)")
                if skipped_count > 0 and args.verbose > 0:
                    for skip in result["skipped"]:
                        print_info(f"Skipped {skip['file']}: {skip['reason']}")

    # Watch mode
    if args.watch:
        print_warning("Watch mode not yet implemented")
        # TODO: Implement file watching with watchdog or similar

    return 1 if total_errors > 0 else 0
