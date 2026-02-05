"""
List command implementation.

Lists all skills in the skills_src directory with optional filtering.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import (
    Colors,
    format_table,
    get_skills_dir,
    load_yaml_file,
    print_error,
    print_header,
)


def discover_skills(skills_dir: Path) -> List[Dict[str, Any]]:
    """
    Discover all skill files in the skills directory.

    Returns a list of skill metadata dictionaries.
    """
    skills = []
    skills_path = skills_dir / "skills"

    if not skills_path.exists():
        return skills

    for skill_file in sorted(skills_path.glob("**/*.skill.yaml")):
        data, error = load_yaml_file(skill_file)
        if error:
            skills.append({
                "file": skill_file.name,
                "error": error,
            })
            continue

        if not data:
            continue

        metadata = data.get("metadata", {})
        spec = data.get("spec", {})
        permissions = spec.get("permissions", {})

        skills.append({
            "file": skill_file.name,
            "name": metadata.get("name", "unknown"),
            "version": metadata.get("version", "0.0.0"),
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "egress": permissions.get("egress", "none"),
            "tools": [t.get("ref", "") for t in spec.get("tools", [])],
            "tool_count": len(spec.get("tools", [])),
        })

    return skills


def filter_skills(skills: List[Dict[str, Any]], tags: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Filter skills by tags."""
    if not tags:
        return skills

    filtered = []
    for skill in skills:
        if "error" in skill:
            continue
        skill_tags = set(skill.get("tags", []))
        if skill_tags.intersection(tags):
            filtered.append(skill)

    return filtered


def format_table_output(skills: List[Dict[str, Any]], show_tools: bool) -> str:
    """Format skills as a table."""
    if show_tools:
        headers = ["NAME", "VERSION", "TAGS", "EGRESS", "TOOLS"]
        rows = []
        for s in skills:
            if "error" in s:
                rows.append([s["file"], "ERROR", s["error"], "", ""])
            else:
                rows.append([
                    s["name"],
                    s["version"],
                    ", ".join(s["tags"]),
                    s["egress"],
                    ", ".join(s["tools"]),
                ])
        return format_table(headers, rows, max_widths=[25, 8, 20, 10, 50])
    else:
        headers = ["NAME", "VERSION", "DESCRIPTION", "TAGS", "EGRESS"]
        rows = []
        for s in skills:
            if "error" in s:
                rows.append([s["file"], "ERROR", s["error"], "", ""])
            else:
                rows.append([
                    s["name"],
                    s["version"],
                    s["description"][:40] + "..." if len(s.get("description", "")) > 40 else s.get("description", ""),
                    ", ".join(s["tags"]),
                    s["egress"],
                ])
        return format_table(headers, rows, max_widths=[25, 8, 45, 20, 10])


def format_json_output(skills: List[Dict[str, Any]]) -> str:
    """Format skills as JSON."""
    return json.dumps(skills, indent=2)


def format_yaml_output(skills: List[Dict[str, Any]]) -> str:
    """Format skills as YAML."""
    try:
        import yaml
        return yaml.safe_dump(skills, default_flow_style=False, allow_unicode=True)
    except ImportError:
        return "YAML output requires PyYAML. Install with: pip install pyyaml"


def format_names_output(skills: List[Dict[str, Any]]) -> str:
    """Format skills as simple name list."""
    names = [s["name"] for s in skills if "error" not in s]
    return "\n".join(names)


def run_list(args) -> int:
    """
    Run the list command.

    Returns exit code (0 for success, non-zero for failure).
    """
    skills_dir = get_skills_dir(args)

    if not skills_dir.exists():
        print_error(f"Skills directory not found: {skills_dir}")
        return 1

    # Discover skills
    skills = discover_skills(skills_dir)

    if not skills:
        if not args.quiet:
            print("No skills found.")
        return 0

    # Filter by tags if specified
    if args.tags:
        tag_list = [t.strip() for t in args.tags.split(",")]
        skills = filter_skills(skills, tag_list)

    if not skills:
        if not args.quiet:
            print("No skills match the specified filters.")
        return 0

    # Format output
    if args.format == "json":
        output = format_json_output(skills)
    elif args.format == "yaml":
        output = format_yaml_output(skills)
    elif args.format == "names":
        output = format_names_output(skills)
    else:  # table
        if not args.quiet:
            print_header(f"Skills ({len(skills)} found)")
        output = format_table_output(skills, args.tools)

    print(output)
    return 0
