"""
Validate command implementation.

Validates skill YAML files against the JSON schema and checks tool references.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..integration import validate_skill_integrations
from ..utils import (
    Colors,
    get_skills_dir,
    load_yaml_file,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)


# Try to import jsonschema for validation
try:
    import jsonschema
    from jsonschema import Draft202012Validator, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


class ValidationResult:
    """Holds validation results for a skill."""

    def __init__(self, skill_name: str, file_path: Path):
        self.skill_name = skill_name
        self.file_path = file_path
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.integration_results: List[Tuple[str, bool, str]] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, message: str):
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_integration_result(self, resource: str, success: bool, message: str):
        self.integration_results.append((resource, success, message))
        if not success:
            self.add_error(f"Integration '{resource}': {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill_name,
            "file": str(self.file_path),
            "valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "integrations": [
                {"resource": r, "valid": s, "message": m}
                for r, s, m in self.integration_results
            ] if self.integration_results else None,
        }


def load_json_schema(skills_dir: Path) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the JSON schema for skill validation."""
    schema_path = skills_dir / "schemas" / "skill.schema.json"

    if not schema_path.exists():
        return None, f"Schema not found: {schema_path}"

    try:
        with schema_path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
        return schema, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in schema: {e}"
    except Exception as e:
        return None, f"Error loading schema: {e}"


def load_tools_registry(skills_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load the tools registry from tools.yaml."""
    tools_path = skills_dir / "tools.yaml"
    if not tools_path.exists():
        return None, f"tools.yaml not found at {tools_path}"

    return load_yaml_file(tools_path)


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
            tools[ref] = tool_def

    return tools


def validate_with_jsonschema(data: Dict, schema: Dict, result: ValidationResult):
    """Validate data against JSON schema and add errors to result."""
    if not HAS_JSONSCHEMA:
        result.add_warning("jsonschema not installed - skipping schema validation")
        return

    try:
        validator = Draft202012Validator(schema)
        for error in validator.iter_errors(data):
            # Format the error path
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
            result.add_error(f"{path}: {error.message}")
    except Exception as e:
        result.add_error(f"Schema validation error: {e}")


def validate_manifest_id_consistency(data: Dict, result: ValidationResult):
    """Check that manifestId matches name and version."""
    metadata = data.get("metadata", {})
    manifest_id = metadata.get("manifestId", "")
    name = metadata.get("name", "")
    version = metadata.get("version", "")

    expected = f"skill.{name}@{version}"
    if manifest_id and manifest_id != expected:
        result.add_error(f"manifestId '{manifest_id}' should be '{expected}'")


def validate_tool_refs(data: Dict, available_tools: Dict[str, Any], result: ValidationResult):
    """Check that tool refs exist in the registry."""
    spec = data.get("spec", {})
    tools = spec.get("tools", [])

    for tool in tools:
        ref = tool.get("ref", "")
        if ref and ref not in available_tools:
            result.add_warning(f"Tool '{ref}' not found in tools.yaml")


def validate_data_sources(data: Dict, skill_path: Path, result: ValidationResult):
    """Validate data sources have content."""
    spec = data.get("spec", {})
    data_sources = spec.get("dataSources", [])

    for ds in data_sources:
        ds_id = ds.get("id", "unknown")
        has_text = "text" in ds
        has_file = "file" in ds

        if not has_text and not has_file:
            result.add_error(f"dataSource '{ds_id}' must have either 'text' or 'file'")
        elif has_text and has_file:
            result.add_error(f"dataSource '{ds_id}' cannot have both 'text' and 'file'")
        elif has_file:
            # Check file exists
            file_path = skill_path.parent / ds["file"]
            if not file_path.exists():
                result.add_warning(f"dataSource '{ds_id}' file not found: {ds['file']}")


def validate_skill(
    skill_path: Path,
    schema: Optional[Dict],
    tools_registry: Optional[Dict[str, Any]] = None,
    check_integrations: bool = False,
    skills_dir: Optional[Path] = None
) -> ValidationResult:
    """
    Validate a single skill file.

    Returns ValidationResult with errors and warnings.
    """
    result = ValidationResult(skill_path.stem.replace(".skill", ""), skill_path)

    # Load skill file
    data, error = load_yaml_file(skill_path)
    if error:
        result.add_error(f"Failed to load: {error}")
        return result

    if not data:
        result.add_error("File is empty")
        return result

    # 1. JSON Schema validation (if available)
    if schema:
        validate_with_jsonschema(data, schema, result)

    # 2. ManifestId consistency check
    validate_manifest_id_consistency(data, result)

    # 3. Tool reference validation
    if tools_registry:
        available_tools = get_available_tools(tools_registry)
        validate_tool_refs(data, available_tools, result)

    # 4. Data source validation
    validate_data_sources(data, skill_path, result)

    # 5. Additional semantic checks (not covered by schema)
    metadata = data.get("metadata", {})
    spec = data.get("spec", {})

    # Check description is provided
    if not metadata.get("description"):
        result.add_warning("metadata.description is recommended")

    # Check directives are meaningful
    directives = spec.get("directives", "")
    if len(directives) < 20:
        result.add_warning("spec.directives seems too short")

    # 6. Integration validation (server connections, file paths)
    if check_integrations and skills_dir:
        skill_name = result.skill_name
        integration_results = validate_skill_integrations(skills_dir, skill_name, verbose=False)
        for resource, success, message in integration_results:
            result.add_integration_result(resource, success, message)

    return result


def discover_skill_files(skills_dir: Path, skill_names: Optional[List[str]] = None) -> List[Path]:
    """
    Discover skill files to validate.

    If skill_names is provided, only those skills are returned.
    """
    skills_path = skills_dir / "skills"
    if not skills_path.exists():
        return []

    all_files = list(skills_path.glob("*.skill.yaml"))

    if not skill_names:
        return sorted(all_files)

    # Filter to specified skills
    filtered = []
    for name in skill_names:
        # Try exact match first
        exact = skills_path / f"{name}.skill.yaml"
        if exact.exists():
            filtered.append(exact)
            continue

        # Try partial match
        matches = [f for f in all_files if name in f.stem]
        filtered.extend(matches)

    return sorted(set(filtered))


def format_text_output(results: List[ValidationResult], verbose: bool = False) -> Tuple[str, int]:
    """Format validation results as text."""
    lines = []
    total_errors = 0
    total_warnings = 0

    for result in results:
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)

        if result.is_valid and not result.warnings:
            if verbose:
                lines.append(f"{Colors.GREEN}✓{Colors.RESET} {result.skill_name}")
                # Show integration results if any (even when valid)
                for resource, success, message in result.integration_results:
                    if success:
                        lines.append(f"    {Colors.GREEN}✓{Colors.RESET} {resource}: {message}")
        else:
            status = f"{Colors.RED}✗{Colors.RESET}" if result.errors else f"{Colors.YELLOW}!{Colors.RESET}"
            lines.append(f"{status} {result.skill_name}")

            for err in result.errors:
                lines.append(f"    {Colors.RED}error:{Colors.RESET} {err}")

            for warn in result.warnings:
                lines.append(f"    {Colors.YELLOW}warning:{Colors.RESET} {warn}")

            # Show successful integration checks in verbose mode
            if verbose:
                for resource, success, message in result.integration_results:
                    if success:
                        lines.append(f"    {Colors.GREEN}✓{Colors.RESET} {resource}: {message}")

    # Summary
    lines.append("")
    if total_errors == 0 and total_warnings == 0:
        lines.append(f"{Colors.GREEN}All {len(results)} skills valid{Colors.RESET}")
    else:
        parts = []
        if total_errors > 0:
            parts.append(f"{Colors.RED}{total_errors} errors{Colors.RESET}")
        if total_warnings > 0:
            parts.append(f"{Colors.YELLOW}{total_warnings} warnings{Colors.RESET}")
        lines.append(f"Validated {len(results)} skills: {', '.join(parts)}")

    return "\n".join(lines), total_errors


def format_json_output(results: List[ValidationResult]) -> Tuple[str, int]:
    """Format validation results as JSON."""
    total_errors = sum(len(r.errors) for r in results)
    output = {
        "valid": total_errors == 0,
        "totalErrors": total_errors,
        "totalWarnings": sum(len(r.warnings) for r in results),
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(output, indent=2), total_errors


def run_validate(args) -> int:
    """
    Run the validate command.

    Returns exit code (0 for success, non-zero for validation errors).
    """
    skills_dir = get_skills_dir(args)

    if not skills_dir.exists():
        print_error(f"Skills directory not found: {skills_dir}")
        return 1

    # Load JSON schema
    schema, error = load_json_schema(skills_dir)
    if error:
        if not HAS_JSONSCHEMA:
            print_warning("jsonschema not installed. Install with: pip install jsonschema")
            print_warning("Falling back to basic validation.")
        else:
            print_warning(f"Could not load schema: {error}")
            print_warning("Schema validation will be skipped.")

    # Load tools registry for tool reference validation
    tools_registry, error = load_tools_registry(skills_dir)
    if error:
        print_warning(f"Could not load tools registry: {error}")
        print_warning("Tool references will not be validated against registry.")
        tools_registry = None

    # Discover skill files
    skill_files = discover_skill_files(skills_dir, args.skills if args.skills else None)

    if not skill_files:
        if args.skills:
            print_error(f"No matching skills found: {', '.join(args.skills)}")
            return 1
        else:
            print_info("No skill files found.")
            return 0

    # Validate each skill
    check_integrations = getattr(args, "integrations", False)
    results = []
    for skill_path in skill_files:
        result = validate_skill(
            skill_path, schema, tools_registry,
            check_integrations=check_integrations,
            skills_dir=skills_dir
        )
        results.append(result)

    # Format output
    if args.format == "json":
        output, error_count = format_json_output(results)
    else:
        if not args.quiet:
            print_header(f"Validating {len(results)} skills")
        output, error_count = format_text_output(results, args.verbose > 0)

    print(output)

    # Determine exit code
    if error_count > 0:
        return 1

    if args.strict:
        total_warnings = sum(len(r.warnings) for r in results)
        if total_warnings > 0:
            return 1

    return 0
