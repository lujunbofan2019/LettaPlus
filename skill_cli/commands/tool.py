"""
Tool command implementation.

Manages MCP tools: list, add, and show tool details.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..integration import (
    get_known_servers,
    prompt_server_with_memory,
    validate_server_connection,
)
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


def load_tools_registry(skills_dir: Path) -> tuple:
    """Load the tools registry from tools.yaml."""
    tools_path = skills_dir / "tools.yaml"
    return load_yaml_file(tools_path)


def get_all_tools(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract all tools from registry with full info."""
    tools = {}
    servers = registry.get("servers", {})

    for server_id, server_data in servers.items():
        for tool_name, tool_def in server_data.get("tools", {}).items():
            ref = f"{server_id}:{tool_name}"
            tools[ref] = {
                "server_id": server_id,
                "tool_name": tool_name,
                "version": tool_def.get("version", "0.1.0"),
                "description": tool_def.get("description", ""),
                "params": tool_def.get("params", {}),
                "result": tool_def.get("result", {}),
                "defaults": tool_def.get("defaults", {}),
                "cases": tool_def.get("cases", []),
            }

    return tools


def run_tool_list(args, skills_dir: Path) -> int:
    """List available tools."""
    registry, error = load_tools_registry(skills_dir)

    if error:
        print_error(f"Failed to load tools.yaml: {error}")
        return 1

    if not registry:
        print_info("No tools found. Create tools.yaml or add tools with: skill tool add")
        return 0

    tools = get_all_tools(registry)

    # Filter by server if specified
    if args.server:
        tools = {k: v for k, v in tools.items() if v["server_id"] == args.server}

    if not tools:
        print_info("No tools match the filter.")
        return 0

    if args.format == "json":
        print(json.dumps(list(tools.values()), indent=2))
    else:
        print_header(f"Available Tools ({len(tools)})")
        print()

        # Group by server
        by_server: Dict[str, List] = {}
        for ref, info in sorted(tools.items()):
            server = info["server_id"]
            if server not in by_server:
                by_server[server] = []
            by_server[server].append((ref, info))

        for server_id, server_tools in sorted(by_server.items()):
            print(f"{Colors.BOLD}{server_id}{Colors.RESET}")
            for ref, info in server_tools:
                desc = info["description"][:50] + "..." if len(info["description"]) > 50 else info["description"]
                cases = len(info["cases"])
                print(f"  {Colors.CYAN}{info['tool_name']}{Colors.RESET}")
                if desc:
                    print(f"    {Colors.DIM}{desc}{Colors.RESET}")
                print(f"    {Colors.DIM}Cases: {cases}{Colors.RESET}")
            print()

    return 0


def run_tool_show(args, skills_dir: Path) -> int:
    """Show details of a specific tool."""
    registry, error = load_tools_registry(skills_dir)

    if error:
        print_error(f"Failed to load tools.yaml: {error}")
        return 1

    tools = get_all_tools(registry)
    tool_ref = args.tool_ref

    if tool_ref not in tools:
        print_error(f"Tool not found: {tool_ref}")
        print_info("Use 'skill tool list' to see available tools")
        return 1

    tool = tools[tool_ref]

    print_header(f"Tool: {tool_ref}")
    print()
    print(f"  Server:      {tool['server_id']}")
    print(f"  Name:        {tool['tool_name']}")
    print(f"  Version:     {tool['version']}")
    print(f"  Description: {tool['description']}")
    print()

    if tool["params"]:
        print(f"{Colors.BOLD}Input Parameters:{Colors.RESET}")
        print(json.dumps(tool["params"], indent=2))
        print()

    if tool["result"]:
        print(f"{Colors.BOLD}Result Schema:{Colors.RESET}")
        print(json.dumps(tool["result"], indent=2))
        print()

    if tool["defaults"]:
        print(f"{Colors.BOLD}Defaults:{Colors.RESET}")
        print(json.dumps(tool["defaults"], indent=2))
        print()

    if tool["cases"]:
        print(f"{Colors.BOLD}Test Cases ({len(tool['cases'])}):{Colors.RESET}")
        for case in tool["cases"]:
            case_id = case.get("id", "unknown")
            match = case.get("match", {})
            strategy = match.get("strategy", "unknown")
            print(f"  - {case_id} ({strategy})")

    return 0


def prompt_tool_params() -> Dict[str, Any]:
    """Interactively build tool parameter schema."""
    print()
    print_header("Input Parameters")
    print_info("Define the parameters this tool accepts.")
    print_info("Each parameter needs: name, type, description, and whether it's required.")
    print()

    params = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    while True:
        param_name = prompt_input("Parameter name (or Enter to finish)")
        if not param_name:
            break

        param_type = prompt_choice(
            f"Type for '{param_name}':",
            ["string", "integer", "number", "boolean", "array", "object"],
            default="string"
        )

        param_desc = prompt_input(f"Description for '{param_name}'", default="")

        params["properties"][param_name] = {
            "type": param_type,
        }
        if param_desc:
            params["properties"][param_name]["description"] = param_desc

        if prompt_confirm(f"Is '{param_name}' required?", default=True):
            params["required"].append(param_name)

        print()

    return params


def prompt_test_case(tool_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Interactively create a test case."""
    print()
    print_header("Add Test Case")
    print_info("Test cases define expected responses for specific inputs.")
    print()

    case_id = prompt_input("Case ID (e.g., case_success, case_empty)")
    if not case_id:
        return None

    # Match strategy
    print()
    strategy = prompt_choice(
        "Match strategy:",
        ["always", "exact", "contains", "regex"],
        default="always"
    )

    match = {"strategy": strategy}

    if strategy != "always":
        # Get the parameter to match on
        param_names = list(params.get("properties", {}).keys())
        if param_names:
            path = prompt_choice(
                "Parameter to match:",
                param_names,
                default=param_names[0]
            )
            match["path"] = path

            value = prompt_input("Value to match")
            match["value"] = value
        else:
            print_warning("No parameters defined, using 'always' strategy")
            match = {"strategy": "always"}

    # Response
    print()
    print_info("Enter the response JSON (or press Enter for a simple placeholder):")
    response_input = prompt_input("Response JSON", default='{"status": "success"}')

    try:
        response = json.loads(response_input)
    except json.JSONDecodeError:
        print_warning("Invalid JSON, using as string value")
        response = {"result": response_input}

    return {
        "id": case_id,
        "match": match,
        "response": response,
    }


def run_tool_add(args, skills_dir: Path) -> int:
    """Add a new tool interactively."""
    tools_path = skills_dir / "tools.yaml"
    registry, error = load_yaml_file(tools_path)

    if error and "not found" not in error.lower():
        print_error(f"Failed to load tools.yaml: {error}")
        return 1

    # Initialize registry if needed
    if not registry:
        registry = {
            "apiVersion": "tools/v1",
            "kind": "ToolsRegistry",
            "servers": {},
        }

    servers = registry.get("servers", {})
    server_ids = list(servers.keys())

    # Get known servers from memory for suggestions
    known_servers = get_known_servers(skills_dir)

    print_header("Add New Tool")
    print()

    # 1. Select or create server (with memory suggestions)
    if args.server:
        server_id = args.server
    else:
        # Combine existing servers from tools.yaml and known servers from cache
        all_server_options = set(server_ids) | set(known_servers.keys())

        if all_server_options:
            print_info("Select an existing server or create a new one")

            # Show servers with validation status from cache
            options_list = []
            for sid in sorted(all_server_options):
                if sid in known_servers and known_servers[sid].get("validated"):
                    options_list.append(f"{sid} ✓")
                else:
                    options_list.append(sid)

            options_list.append("[Create new server]")

            choice = prompt_choice(
                "Server:",
                options_list,
                default=options_list[0] if options_list else "[Create new server]"
            )

            # Strip the validation mark if present
            if choice == "[Create new server]":
                # Use memory-aware server prompting
                server_config = prompt_server_with_memory(skills_dir, "Enter new server details")
                if server_config:
                    server_id = server_config["id"]
                else:
                    print_info("Aborted.")
                    return 0
            else:
                server_id = choice.replace(" ✓", "")
        else:
            # No existing servers - prompt for new one with memory
            server_config = prompt_server_with_memory(skills_dir, "Enter server details")
            if server_config:
                server_id = server_config["id"]
            else:
                server_id = prompt_input("Server ID (e.g., search, llm, datasets)")

    if not server_id:
        print_info("Aborted.")
        return 0

    # Ensure server exists
    if server_id not in servers:
        server_desc = prompt_input(f"Description for server '{server_id}'", default=f"{server_id} tools")
        servers[server_id] = {
            "description": server_desc,
            "tools": {},
        }
        print_success(f"Created server: {server_id}")

    # 2. Tool name
    print()
    tool_name = prompt_input("Tool name (e.g., search_query, fetch_data)")
    if not tool_name:
        print_info("Aborted.")
        return 0

    # Check if exists
    if tool_name in servers[server_id].get("tools", {}):
        if not prompt_confirm(f"Tool '{tool_name}' already exists. Overwrite?", default=False):
            print_info("Aborted.")
            return 0

    # 3. Tool details
    print()
    tool_version = prompt_input("Version", default="0.1.0")
    tool_desc = prompt_input("Description")

    # 4. Parameters
    params = prompt_tool_params()

    # 5. Defaults
    print()
    print_header("Default Response")
    print_info("Define what the stub server returns when no test case matches.")
    default_response = prompt_input("Default response JSON", default='{}')

    try:
        default_resp_parsed = json.loads(default_response)
    except json.JSONDecodeError:
        default_resp_parsed = {}

    default_latency = prompt_input("Default latency (ms)", default="100")

    defaults = {
        "response": default_resp_parsed,
        "latencyMs": int(default_latency),
    }

    # 6. Test cases
    cases = []
    print()
    if prompt_confirm("Add test cases now?", default=True):
        while True:
            case = prompt_test_case(tool_name, params)
            if not case:
                break
            cases.append(case)
            print_success(f"Added case: {case['id']}")
            print()
            if not prompt_confirm("Add another test case?", default=False):
                break

    # Build tool definition
    tool_def = {
        "version": tool_version,
        "description": tool_desc,
        "params": params,
        "defaults": defaults,
    }

    if cases:
        tool_def["cases"] = cases

    # Save to registry
    if "tools" not in servers[server_id]:
        servers[server_id]["tools"] = {}

    servers[server_id]["tools"][tool_name] = tool_def
    registry["servers"] = servers

    error = save_yaml_file(tools_path, registry)
    if error:
        print_error(f"Failed to save tools.yaml: {error}")
        return 1

    print()
    print_success(f"Added tool: {server_id}:{tool_name}")
    print()
    print_info("Next steps:")
    print(f"  1. Review: skill tool show {server_id}:{tool_name}")
    print(f"  2. Use in a skill: skill init")
    print(f"  3. Regenerate stub config: skill generate --stub-only")

    return 0


def run_tool(args) -> int:
    """Run the tool command."""
    skills_dir = get_skills_dir(args)

    if not hasattr(args, 'tool_command') or args.tool_command is None:
        print_error("No subcommand specified. Use: skill tool list|add|show")
        return 1

    if args.tool_command == "list":
        return run_tool_list(args, skills_dir)
    elif args.tool_command == "add":
        return run_tool_add(args, skills_dir)
    elif args.tool_command == "show":
        return run_tool_show(args, skills_dir)
    else:
        print_error(f"Unknown tool command: {args.tool_command}")
        return 1
