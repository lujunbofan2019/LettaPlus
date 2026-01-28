"""
Init command implementation.

Creates new skills through guided interactive prompts.
Supports two modes:
  - Real skills: Fulfilled by real MCP servers (need integration details)
  - Simulated skills: Fulfilled by stub_mcp (need test cases)
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils import (
    Colors,
    format_table,
    get_skills_dir,
    load_yaml_file,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    prompt_choice,
    prompt_confirm,
    prompt_input,
    save_yaml_file,
)


def load_tools_registry(skills_dir: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    """Load the tools registry from tools.yaml."""
    tools_path = skills_dir / "tools.yaml"
    data, error = load_yaml_file(tools_path)
    if error or not data:
        return {"apiVersion": "tools/v1", "kind": "ToolsRegistry", "servers": {}}, error
    return data, None


def save_tools_registry(skills_dir: Path, registry: Dict[str, Any]) -> Optional[str]:
    """Save the tools registry to tools.yaml."""
    tools_path = skills_dir / "tools.yaml"
    return save_yaml_file(tools_path, registry)


def get_available_tools(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract available tools from registry."""
    tools = {}
    for server_id, server_data in registry.get("servers", {}).items():
        for tool_name, tool_def in server_data.get("tools", {}).items():
            ref = f"{server_id}:{tool_name}"
            tools[ref] = {
                "server_id": server_id,
                "tool_name": tool_name,
                "description": tool_def.get("description", ""),
            }
    return tools


def validate_skill_name(name: str) -> Optional[str]:
    """Validate skill name format."""
    if not name:
        return "Skill name is required"
    if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", name):
        return "Skill name must be lowercase with dots (e.g., research.web)"
    return None


def prompt_skill_basics() -> Tuple[Optional[str], str, List[str]]:
    """Prompt for basic skill info: name, description, tags."""
    print_info("Skill names use dot notation: domain.capability (e.g., research.competitor_analysis)")
    print()

    while True:
        name = prompt_input("Skill name")
        if not name:
            return None, "", []
        error = validate_skill_name(name)
        if error:
            print_error(error)
            continue
        break

    print()
    print_info("Describe what this skill enables an agent to do.")
    print_info("This helps the Planner understand when to assign this skill.")
    description = prompt_input("Description")

    print()
    print_info("Tags help categorize the skill (e.g., research, analysis, writing)")
    tags_input = prompt_input("Tags (comma-separated)", default="")
    tags = [t.strip().lower() for t in tags_input.split(",") if t.strip()]

    return name, description or "A custom skill", tags


def prompt_egress_and_secrets() -> Tuple[str, List[str]]:
    """Prompt for permissions."""
    print()
    print_header("Permissions")
    print_info("What network access does this skill need?")
    print(f"  {Colors.DIM}none{Colors.RESET}     - No external access")
    print(f"  {Colors.DIM}intranet{Colors.RESET} - Internal APIs only")
    print(f"  {Colors.DIM}internet{Colors.RESET} - External APIs")
    print()

    egress = prompt_choice("Egress:", ["none", "intranet", "internet"], default="none")

    print()
    secrets_input = prompt_input("Required API keys (comma-separated, or blank)", default="")
    secrets = [s.strip().upper() for s in secrets_input.split(",") if s.strip()]

    return egress, secrets


def prompt_directives(name: str, description: str) -> str:
    """Prompt for skill directives."""
    print()
    print_header("Directives")
    print_info("Directives tell the Worker agent how to use this skill effectively.")
    print_info("Be specific about:")
    print_info("  - What the skill should accomplish")
    print_info("  - How to interpret and present results")
    print_info("  - Any constraints or quality criteria")
    print()

    # Generate default based on description
    default = f"""You are executing the {name} skill.

Purpose: {description}

Guidelines:
- Follow the task requirements precisely
- Use the available tools appropriately
- Provide clear, structured output
- Report any issues or limitations encountered"""

    print(f"{Colors.DIM}Default directives:{Colors.RESET}")
    for line in default.split("\n")[:6]:
        print(f"  {Colors.DIM}{line}{Colors.RESET}")
    print()

    if prompt_confirm("Use default directives?", default=True):
        return default

    print()
    print_info("Enter custom directives (press Enter twice to finish):")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            lines.pop()
            break
        lines.append(line)

    return "\n".join(lines) if lines else default


# =============================================================================
# REAL SKILL CREATION
# =============================================================================

def prompt_real_tool_selection(available_tools: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prompt user to select existing tools for a real skill."""
    print()
    print_header("Tool Selection")

    if not available_tools:
        print_warning("No tools found in tools.yaml")
        print_info("Add tools first with: skill tool add")
        return []

    print_info(f"Select tools this skill requires ({len(available_tools)} available):")
    print()

    tool_list = sorted(available_tools.items())
    for i, (ref, info) in enumerate(tool_list, 1):
        desc = info.get("description", "")[:50]
        print(f"  {Colors.CYAN}{i:2}{Colors.RESET}. {ref}")
        if desc:
            print(f"      {Colors.DIM}{desc}{Colors.RESET}")

    print()
    print_info("Enter numbers separated by commas (e.g., 1,3)")
    selection = prompt_input("Select tools")

    if not selection:
        return []

    selected = []
    try:
        indices = [int(x.strip()) for x in selection.split(",") if x.strip()]
        for idx in indices:
            if 1 <= idx <= len(tool_list):
                ref, info = tool_list[idx - 1]
                selected.append({
                    "ref": ref,
                    "required": len(selected) == 0,
                    "description": info.get("description", ""),
                })
    except ValueError:
        print_warning("Invalid selection")
        return []

    return selected


def run_init_real(args, skills_dir: Path) -> int:
    """Create a real skill fulfilled by actual MCP servers."""
    print_header("Create Real Skill")
    print()
    print_info("Real skills are fulfilled by actual MCP servers and APIs.")
    print_info("You'll select from existing tools configured with real endpoints.")
    print()

    registry, _ = load_tools_registry(skills_dir)
    available_tools = get_available_tools(registry)

    # Basic info
    name, description, tags = prompt_skill_basics()
    if not name:
        print_info("Aborted.")
        return 0

    # Check exists
    skill_file = skills_dir / "skills" / f"{name}.skill.yaml"
    if skill_file.exists() and not args.force:
        if not prompt_confirm(f"Skill '{name}' exists. Overwrite?", default=False):
            return 0

    # Permissions
    egress, secrets = prompt_egress_and_secrets()

    # Tool selection
    tools = prompt_real_tool_selection(available_tools)

    # Directives
    directives = prompt_directives(name, description)

    # Create skill
    skill_data = {
        "apiVersion": "skill/v1",
        "kind": "Skill",
        "metadata": {
            "manifestId": f"skill.{name}@0.1.0",
            "name": name,
            "version": "0.1.0",
            "description": description,
            "tags": tags,
        },
        "spec": {
            "permissions": {"egress": egress},
            "directives": directives,
            "tools": tools,
        },
    }
    if secrets:
        skill_data["spec"]["permissions"]["secrets"] = secrets

    skill_file.parent.mkdir(parents=True, exist_ok=True)
    error = save_yaml_file(skill_file, skill_data)
    if error:
        print_error(f"Failed to create skill: {error}")
        return 1

    print()
    print_success(f"Created real skill: {skill_file}")
    print()
    print_info("Next steps:")
    print(f"  1. Validate: skill validate {name}")
    print(f"  2. Generate manifest: skill generate")

    return 0


# =============================================================================
# SIMULATED SKILL CREATION
# =============================================================================

def prompt_tool_parameter() -> Optional[Dict[str, Any]]:
    """Prompt for a single tool parameter."""
    param_name = prompt_input("  Parameter name (or Enter to finish)")
    if not param_name:
        return None

    param_type = prompt_choice(
        f"  Type for '{param_name}':",
        ["string", "integer", "number", "boolean", "array", "object"],
        default="string"
    )

    param_desc = prompt_input(f"  Description", default="")
    required = prompt_confirm(f"  Required?", default=True)

    return {
        "name": param_name,
        "type": param_type,
        "description": param_desc,
        "required": required,
    }


def prompt_test_case(tool_name: str, params: List[Dict]) -> Optional[Dict[str, Any]]:
    """Prompt for a BDD-style test case."""
    print()
    print(f"{Colors.BOLD}Test Case{Colors.RESET}")
    print_info("Define: Given this input, the stub returns this output")
    print()

    # Scenario description
    scenario = prompt_input("Scenario name (e.g., 'successful search', 'empty results')")
    if not scenario:
        return None

    # Input conditions
    print()
    print_info("What input triggers this case?")
    strategy = prompt_choice(
        "Match strategy:",
        ["exact", "contains", "regex", "always"],
        default="contains"
    )

    match = {"strategy": strategy}

    if strategy != "always":
        if params:
            param_names = [p["name"] for p in params]
            path = prompt_choice("Which parameter to match:", param_names, default=param_names[0])
        else:
            path = prompt_input("Parameter path to match")

        match["path"] = path

        if strategy == "exact":
            value = prompt_input("Exact value to match")
        elif strategy == "contains":
            value = prompt_input("Value that input should contain")
        elif strategy == "regex":
            value = prompt_input("Regex pattern to match")

        match["value"] = value

    # Expected output
    print()
    print_info("What should the stub return for this case?")
    print_info("Enter JSON (can use templates like {{ now_iso }}, {{ uuid }})")

    response_str = prompt_input("Response JSON")
    try:
        response = json.loads(response_str) if response_str else {}
    except json.JSONDecodeError:
        print_warning("Invalid JSON, wrapping as string")
        response = {"result": response_str}

    return {
        "id": f"case_{scenario.lower().replace(' ', '_')}",
        "match": match,
        "response": response,
    }


def prompt_simulated_tool(server_id: str) -> Optional[Dict[str, Any]]:
    """Prompt for a complete simulated tool with test cases."""
    print()
    print(f"{Colors.BOLD}Define Tool{Colors.RESET}")
    print_info("This tool will be simulated by stub_mcp with your test cases.")
    print()

    tool_name = prompt_input("Tool name (e.g., search_competitors, analyze_market)")
    if not tool_name:
        return None

    tool_desc = prompt_input("What does this tool do?")

    # Parameters
    print()
    print_info("Define the tool's input parameters:")
    params = []
    while True:
        param = prompt_tool_parameter()
        if not param:
            break
        params.append(param)

    # Build params schema
    params_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    for p in params:
        params_schema["properties"][p["name"]] = {
            "type": p["type"],
            "description": p["description"],
        }
        if p["required"]:
            params_schema["required"].append(p["name"])

    # Default response
    print()
    print_info("Default response when no test case matches:")
    default_resp_str = prompt_input("Default JSON", default="{}")
    try:
        default_resp = json.loads(default_resp_str)
    except json.JSONDecodeError:
        default_resp = {}

    # Test cases (the key part for simulation!)
    print()
    print_header("Test Cases (BDD Scenarios)")
    print_info("Define input→output mappings for deterministic testing.")
    print_info("Each case represents a scenario the Planner/Worker might encounter.")
    print()

    cases = []
    while True:
        if not cases:
            print_info("Add at least one test case for meaningful simulation.")
        case = prompt_test_case(tool_name, params)
        if not case:
            if not cases:
                print_warning("No test cases defined - tool will always return default response")
            break
        cases.append(case)
        print_success(f"Added: {case['id']}")

        if not prompt_confirm("Add another test case?", default=True):
            break

    return {
        "name": tool_name,
        "definition": {
            "version": "0.1.0",
            "description": tool_desc,
            "params": params_schema,
            "defaults": {
                "response": default_resp,
                "latencyMs": 100,
            },
            "cases": cases,
        },
        "skill_ref": {
            "ref": f"{server_id}:{tool_name}",
            "required": True,
            "description": tool_desc,
        },
    }


def run_init_simulate(args, skills_dir: Path) -> int:
    """Create a simulated skill fulfilled by stub_mcp."""
    print_header("Create Simulated Skill")
    print()
    print_info("Simulated skills are fulfilled by stub_mcp with controlled test cases.")
    print_info("You'll define tools with BDD-style input→output mappings.")
    print()

    registry, _ = load_tools_registry(skills_dir)

    # Basic info
    name, description, tags = prompt_skill_basics()
    if not name:
        print_info("Aborted.")
        return 0

    # Check exists
    skill_file = skills_dir / "skills" / f"{name}.skill.yaml"
    if skill_file.exists() and not args.force:
        if not prompt_confirm(f"Skill '{name}' exists. Overwrite?", default=False):
            return 0

    # For simulated skills, egress doesn't matter (stub_mcp handles everything)
    egress = "none"
    secrets = []

    # Create a server for this skill's tools (or use existing)
    server_id = name.replace(".", "_")
    print()
    print_info(f"Tools will be added to server: {server_id}")

    # Define tools with test cases
    print()
    print_header("Tool Definition")
    print_info("Define the tools this skill needs, with test cases for each.")
    print()

    tools = []
    tool_defs = []

    while True:
        tool_data = prompt_simulated_tool(server_id)
        if not tool_data:
            if not tools:
                print_warning("At least one tool is required")
                continue
            break

        tools.append(tool_data["skill_ref"])
        tool_defs.append((tool_data["name"], tool_data["definition"]))
        print()
        print_success(f"Added tool: {server_id}:{tool_data['name']}")

        if not prompt_confirm("Add another tool?", default=False):
            break

    # Directives
    directives = prompt_directives(name, description)

    # Save tools to registry
    if server_id not in registry.get("servers", {}):
        if "servers" not in registry:
            registry["servers"] = {}
        registry["servers"][server_id] = {
            "description": f"Tools for {name} skill (simulated)",
            "tools": {},
        }

    for tool_name, tool_def in tool_defs:
        registry["servers"][server_id]["tools"][tool_name] = tool_def

    error = save_tools_registry(skills_dir, registry)
    if error:
        print_error(f"Failed to update tools.yaml: {error}")
        return 1

    # Create skill
    skill_data = {
        "apiVersion": "skill/v1",
        "kind": "Skill",
        "metadata": {
            "manifestId": f"skill.{name}@0.1.0",
            "name": name,
            "version": "0.1.0",
            "description": description,
            "tags": tags + ["simulated"],
        },
        "spec": {
            "permissions": {"egress": egress},
            "directives": directives,
            "tools": tools,
        },
    }

    skill_file.parent.mkdir(parents=True, exist_ok=True)
    error = save_yaml_file(skill_file, skill_data)
    if error:
        print_error(f"Failed to create skill: {error}")
        return 1

    print()
    print_success(f"Created simulated skill: {skill_file}")
    print_success(f"Added {len(tool_defs)} tool(s) to tools.yaml")
    print()
    print_info("Next steps:")
    print(f"  1. Validate: skill validate {name}")
    print(f"  2. Generate: skill generate")
    print(f"  3. Test: skill test --tool {server_id}:{tool_defs[0][0]}")

    return 0


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_init(args) -> int:
    """Run the init command."""
    skills_dir = get_skills_dir(args)

    # Ask user which mode
    print_header("Create New Skill")
    print()
    print_info("Skills can be fulfilled in two ways:")
    print()
    print(f"  {Colors.CYAN}1. Real{Colors.RESET} - Connects to actual MCP servers and APIs")
    print(f"     {Colors.DIM}Use when integrating with real services{Colors.RESET}")
    print()
    print(f"  {Colors.CYAN}2. Simulated{Colors.RESET} - Uses stub_mcp with controlled test cases")
    print(f"     {Colors.DIM}Use for testing workflows with predictable responses{Colors.RESET}")
    print()

    mode = prompt_choice("Skill type:", ["Real", "Simulated"], default="Simulated")

    if mode == "Real":
        return run_init_real(args, skills_dir)
    else:
        return run_init_simulate(args, skills_dir)
