"""
Generate command implementation.

Generates JSON manifests from YAML skills and stub server configuration.

This module delegates to dcf_mcp generators for the actual generation logic,
providing a CLI wrapper with user-friendly output formatting.
"""

from pathlib import Path
from typing import Any, Dict

from ..utils import (
    get_generated_dir,
    get_skills_dir,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)


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
    # Import dcf_mcp generators lazily to avoid import errors when dcf_mcp is not available
    try:
        from dcf_mcp.tools.dcf.generate import (
            generate_manifests as dcf_generate_manifests,
            generate_stub_config as dcf_generate_stub_config,
            generate_registry as dcf_generate_registry,
            generate_schemas as dcf_generate_schemas,
        )
    except ImportError as e:
        print_error(f"Failed to import dcf_mcp generators: {e}")
        print_info("Make sure dcf_mcp is installed or add it to your PYTHONPATH")
        return 1

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

        result = dcf_generate_manifests(
            skills_src_dir=str(skills_dir),
            out_dir=str(generated_dir / "manifests"),
            catalog_path=str(generated_dir / "catalogs" / "skills_catalog.json")
        )

        if not result.get("ok"):
            if result.get("error"):
                print_error(result["error"])
            return 1

        if result.get("warnings"):
            for warn in result["warnings"]:
                print_warning(warn)

        if not args.quiet:
            manifest_count = len(result.get("manifests", []))
            print_success(f"Generated {manifest_count} manifests")
            if args.verbose > 0:
                for m in result.get("manifests", []):
                    print_info(f"  {m['skillName']} -> {m['path']}")

    if generate_stub_flag:
        if not args.quiet:
            print_header("Generating stub configuration")

        result = dcf_generate_stub_config(
            skills_src_dir=str(skills_dir),
            out_path=str(generated_dir / "stub" / "stub_config.json")
        )

        if not result.get("ok"):
            if result.get("error"):
                print_error(result["error"])
            return 1

        if result.get("warnings"):
            for warn in result["warnings"]:
                print_warning(warn)

        if not args.quiet:
            tool_count = result.get("tool_count", 0)
            case_count = result.get("case_count", 0)
            print_success(f"Generated stub config: {tool_count} tools, {case_count} cases")

    # Generate registry (always, unless stub_only or manifests_only)
    if not args.stub_only and not args.manifests_only:
        if not args.quiet:
            print_header("Generating MCP registry")

        result = dcf_generate_registry(
            skills_src_dir=str(skills_dir),
            out_path=str(generated_dir / "registry.json")
        )

        if not result.get("ok"):
            if result.get("error"):
                print_warning(result["error"])  # Non-fatal - registry.yaml may not exist
        else:
            if not args.quiet:
                server_count = result.get("server_count", 0)
                print_success(f"Generated registry.json ({server_count} servers)")

    # Generate schemas (always, unless stub_only or manifests_only)
    if not args.stub_only and not args.manifests_only:
        if not args.quiet:
            print_header("Generating JSON schemas")

        result = dcf_generate_schemas(
            skills_src_dir=str(skills_dir),
            out_dir=str(generated_dir / "schemas")
        )

        if not result.get("ok"):
            if result.get("error"):
                print_warning(result["error"])  # Non-fatal - schemas may not exist
        else:
            if result.get("warnings"):
                for warn in result["warnings"]:
                    if args.verbose > 0:
                        print_info(warn)

            generated_count = len(result.get("written_files", []))
            if not args.quiet and generated_count > 0:
                print_success(f"Generated {generated_count} schema(s)")

    # Watch mode
    if args.watch:
        print_warning("Watch mode not yet implemented")
        # TODO: Implement file watching with watchdog or similar

    return 1 if total_errors > 0 else 0
