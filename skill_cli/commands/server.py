"""
Server command implementation.

Manages MCP servers: list, add, show, and validate server connections.
Features:
- Remember known servers for quick reuse
- Validate server connectivity
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..integration import (
    get_known_servers,
    get_recent_commands,
    get_recent_endpoints,
    prompt_with_suggestions,
    remember_server,
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


def load_server_registry(skills_dir: Path) -> tuple:
    """Load the server registry from registry.yaml."""
    registry_path = skills_dir / "registry.yaml"
    return load_yaml_file(registry_path)


def save_server_registry(skills_dir: Path, registry: Dict[str, Any]) -> Optional[str]:
    """Save the server registry to registry.yaml."""
    registry_path = skills_dir / "registry.yaml"
    return save_yaml_file(registry_path, registry)


def get_server_info(tools_registry: Dict, server_registry: Dict) -> Dict[str, Dict[str, Any]]:
    """Combine server info from both registries."""
    servers = {}

    # Get servers from tools.yaml
    for server_id, server_data in tools_registry.get("servers", {}).items():
        tool_count = len(server_data.get("tools", {}))
        case_count = sum(
            len(tool.get("cases", []))
            for tool in server_data.get("tools", {}).values()
        )
        servers[server_id] = {
            "id": server_id,
            "description": server_data.get("description", ""),
            "tool_count": tool_count,
            "case_count": case_count,
            "transport": None,
            "endpoint": None,
            "path": None,
            "command": None,
        }

    # Enrich with endpoint info from registry.yaml
    for server_id, server_data in server_registry.get("servers", {}).items():
        if server_id not in servers:
            servers[server_id] = {
                "id": server_id,
                "description": "",
                "tool_count": 0,
                "case_count": 0,
            }
        servers[server_id]["transport"] = server_data.get("transport", "")
        servers[server_id]["endpoint"] = server_data.get("endpoint", "")
        servers[server_id]["path"] = server_data.get("path", "")
        servers[server_id]["command"] = server_data.get("command", "")

    return servers


def run_server_list(args, skills_dir: Path) -> int:
    """List MCP servers."""
    tools_registry, t_error = load_tools_registry(skills_dir)
    server_registry, s_error = load_server_registry(skills_dir)

    if t_error and "not found" not in t_error.lower():
        print_warning(f"Could not load tools.yaml: {t_error}")
        tools_registry = {"servers": {}}

    if s_error and "not found" not in s_error.lower():
        print_warning(f"Could not load registry.yaml: {s_error}")
        server_registry = {"servers": {}}

    servers = get_server_info(tools_registry or {}, server_registry or {})

    if not servers:
        print_info("No servers found.")
        print_info("Add a server with: skill server add")
        return 0

    if args.format == "json":
        print(json.dumps(list(servers.values()), indent=2))
    else:
        print_header(f"MCP Servers ({len(servers)})")
        print()

        headers = ["ID", "TRANSPORT", "TOOLS", "ENDPOINT"]
        rows = []
        for server_id, info in sorted(servers.items()):
            transport = info.get("transport") or "?"
            endpoint = info.get("endpoint") or "(not configured)"
            if info.get("path"):
                endpoint = f"{endpoint}{info['path']}"
            if len(endpoint) > 35:
                endpoint = endpoint[:32] + "..."
            rows.append([
                server_id,
                transport,
                str(info["tool_count"]),
                endpoint,
            ])

        print(format_table(headers, rows, max_widths=[15, 15, 8, 40]))
        print()

        # Show descriptions
        for server_id, info in sorted(servers.items()):
            if info.get("description"):
                print(f"  {Colors.CYAN}{server_id}{Colors.RESET}: {info['description']}")

    return 0


def run_server_show(args, skills_dir: Path) -> int:
    """Show details of a specific server."""
    tools_registry, t_error = load_tools_registry(skills_dir)
    server_registry, s_error = load_server_registry(skills_dir)

    tools_registry = tools_registry or {"servers": {}}
    server_registry = server_registry or {"servers": {}}

    server_id = args.server_id
    servers = get_server_info(tools_registry, server_registry)

    if server_id not in servers:
        print_error(f"Server not found: {server_id}")
        print_info("Use 'skill server list' to see available servers")
        return 1

    info = servers[server_id]

    print_header(f"Server: {server_id}")
    print()
    print(f"  Description: {info.get('description') or '(none)'}")
    print(f"  Tools:       {info['tool_count']}")
    print(f"  Test cases:  {info['case_count']}")
    print()
    print(f"  Transport:   {info.get('transport') or '(not configured)'}")

    if info.get('transport') == 'stdio':
        print(f"  Command:     {info.get('command') or '(not configured)'}")
    else:
        print(f"  Endpoint:    {info.get('endpoint') or '(not configured)'}")
        print(f"  Path:        {info.get('path') or '(not configured)'}")

    # Validate connection
    print()
    if prompt_confirm("Validate connection?", default=True):
        transport = info.get('transport', 'streamable_http')
        endpoint = info.get('endpoint', '')
        path = info.get('path', '')
        command = info.get('command', '')

        success, message = validate_server_connection(
            transport, endpoint, path, command
        )

        if success:
            print_success(f"Connection: {message}")
        else:
            print_error(f"Connection failed: {message}")

    # List tools
    server_tools = tools_registry.get("servers", {}).get(server_id, {}).get("tools", {})
    if server_tools:
        print()
        print(f"{Colors.BOLD}Tools:{Colors.RESET}")
        for tool_name, tool_def in sorted(server_tools.items()):
            desc = tool_def.get("description", "")[:40]
            cases = len(tool_def.get("cases", []))
            print(f"  {Colors.CYAN}{tool_name}{Colors.RESET} ({cases} cases)")
            if desc:
                print(f"    {Colors.DIM}{desc}{Colors.RESET}")

    return 0


def run_server_add(args, skills_dir: Path) -> int:
    """Add a new MCP server interactively with validation and memory."""
    # Load existing registries
    tools_path = skills_dir / "tools.yaml"
    registry_path = skills_dir / "registry.yaml"

    tools_registry, _ = load_yaml_file(tools_path)
    server_registry, _ = load_yaml_file(registry_path)

    # Initialize if needed
    if not tools_registry:
        tools_registry = {
            "apiVersion": "tools/v1",
            "kind": "ToolsRegistry",
            "servers": {},
        }

    if not server_registry:
        server_registry = {
            "apiVersion": "registry/v1",
            "kind": "ServerRegistry",
            "env": "test",
            "servers": {},
        }

    print_header("Add New MCP Server")
    print()

    # Check for known servers
    known = get_known_servers(skills_dir)
    if known:
        print_info("You can reuse a known server configuration or create a new one.")
        print()
        print(f"{Colors.DIM}Known servers:{Colors.RESET}")
        known_list = list(known.items())
        for i, (sid, config) in enumerate(known_list, 1):
            transport = config.get("transport", "?")
            validated = "✓" if config.get("validated") else ""
            print(f"  {Colors.CYAN}{i}{Colors.RESET}. {sid} ({transport}) {validated}")

        print(f"  {Colors.CYAN}{len(known_list) + 1}{Colors.RESET}. [Create new server]")
        print()

        selection = prompt_input("Select (number) or enter new server ID")

        if selection.isdigit():
            idx = int(selection) - 1
            if 0 <= idx < len(known_list):
                # Reuse known server
                server_id, config = known_list[idx]
                print_success(f"Using known server: {server_id}")

                transport = config.get("transport", "streamable_http")
                endpoint = config.get("endpoint", "")
                path = config.get("path", "")
                command = config.get("command", "")

                # Ask for description
                print()
                description = prompt_input("Description", default=f"{server_id} server")

                # Skip to saving
                return _save_server(
                    skills_dir, tools_registry, server_registry,
                    tools_path, registry_path,
                    server_id, description, transport, endpoint, path, command
                )

        # User wants new server or entered a name
        if selection.isdigit() and int(selection) - 1 == len(known_list):
            server_id = prompt_input("New server ID")
        elif not selection.isdigit():
            server_id = selection
        else:
            server_id = prompt_input("Server ID")
    else:
        server_id = prompt_input("Server ID (e.g., search, llm, myapi)")

    if not server_id:
        print_info("Aborted.")
        return 0

    # Check if exists
    existing_tools = server_id in tools_registry.get("servers", {})
    existing_registry = server_id in server_registry.get("servers", {})

    if existing_tools or existing_registry:
        if not prompt_confirm(f"Server '{server_id}' already exists. Update it?", default=False):
            print_info("Aborted.")
            return 0

    # Description
    print()
    description = prompt_input("Description (what does this server provide?)")

    # Transport
    print()
    print_header("Connection Configuration")
    print()
    print_info("Transport types:")
    print(f"  {Colors.DIM}streamable_http{Colors.RESET} - HTTP-based MCP (most common)")
    print(f"  {Colors.DIM}sse{Colors.RESET}             - Server-Sent Events")
    print(f"  {Colors.DIM}stdio{Colors.RESET}           - Local process via stdin/stdout")
    print()

    transport = prompt_choice(
        "Transport type:",
        ["streamable_http", "sse", "stdio"],
        default="streamable_http"
    )

    endpoint = ""
    path = ""
    command = ""

    if transport in ("streamable_http", "sse"):
        print()
        # Show recent endpoints
        recent = get_recent_endpoints(skills_dir)
        endpoint = prompt_with_suggestions(
            "Endpoint URL",
            recent,
            default="http://localhost:8765"
        )

        path = prompt_input("Path (e.g., /mcp)", default="/mcp")

    elif transport == "stdio":
        print()
        print_info("Enter the command to start the MCP server process.")
        print_info("Examples: 'node my-mcp.js', '/path/to/mcp-server', 'python -m mymcp'")
        print()

        recent = get_recent_commands(skills_dir)
        command = prompt_with_suggestions(
            "Command",
            recent,
            default=""
        )

    # Validate connection
    print()
    print_header("Validation")

    success, message = validate_server_connection(
        transport, endpoint, path, command
    )

    if success:
        print_success(f"Validation passed: {message}")
        validated = True
    else:
        print_warning(f"Validation failed: {message}")
        if not prompt_confirm("Save anyway?", default=False):
            print_info("Aborted.")
            return 0
        validated = False

    return _save_server(
        skills_dir, tools_registry, server_registry,
        tools_path, registry_path,
        server_id, description, transport, endpoint, path, command, validated
    )


def _save_server(
    skills_dir: Path,
    tools_registry: Dict,
    server_registry: Dict,
    tools_path: Path,
    registry_path: Path,
    server_id: str,
    description: str,
    transport: str,
    endpoint: str,
    path: str,
    command: str,
    validated: bool = False
) -> int:
    """Save server configuration to files and cache."""
    # Save to tools.yaml
    if "servers" not in tools_registry:
        tools_registry["servers"] = {}

    if server_id not in tools_registry["servers"]:
        tools_registry["servers"][server_id] = {
            "description": description,
            "tools": {},
        }
    else:
        tools_registry["servers"][server_id]["description"] = description

    error = save_yaml_file(tools_path, tools_registry)
    if error:
        print_error(f"Failed to save tools.yaml: {error}")
        return 1

    # Save to registry.yaml
    if "servers" not in server_registry:
        server_registry["servers"] = {}

    server_config = {"transport": transport}
    if transport in ("streamable_http", "sse"):
        server_config["endpoint"] = endpoint
        server_config["path"] = path
    elif transport == "stdio":
        server_config["command"] = command

    server_registry["servers"][server_id] = server_config

    error = save_yaml_file(registry_path, server_registry)
    if error:
        print_error(f"Failed to save registry.yaml: {error}")
        return 1

    # Remember in cache
    remember_server(
        skills_dir, server_id, transport, endpoint, path, command, validated
    )

    print()
    print_success(f"Added server: {server_id}")
    print()
    print_info("Next steps:")
    print(f"  1. Add tools: skill tool add --server {server_id}")
    print(f"  2. View details: skill server show {server_id}")

    return 0


def run_server_validate(args, skills_dir: Path) -> int:
    """Validate all server connections."""
    server_registry, error = load_server_registry(skills_dir)

    if error:
        print_error(f"Failed to load registry.yaml: {error}")
        return 1

    servers = server_registry.get("servers", {})

    if not servers:
        print_info("No servers configured in registry.yaml")
        return 0

    print_header(f"Validating {len(servers)} servers")
    print()

    all_passed = True

    for server_id, config in sorted(servers.items()):
        transport = config.get("transport", "streamable_http")
        endpoint = config.get("endpoint", "")
        path = config.get("path", "")
        command = config.get("command", "")

        success, message = validate_server_connection(
            transport, endpoint, path, command, verbose=False
        )

        if success:
            print(f"{Colors.GREEN}✓{Colors.RESET} {server_id}: {message}")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} {server_id}: {message}")
            all_passed = False

    print()
    if all_passed:
        print_success("All servers validated successfully")
    else:
        print_warning("Some servers failed validation")

    return 0 if all_passed else 1


def run_server(args) -> int:
    """Run the server command."""
    skills_dir = get_skills_dir(args)

    if not hasattr(args, 'server_command') or args.server_command is None:
        print_error("No subcommand specified. Use: skill server list|add|show|validate")
        return 1

    if args.server_command == "list":
        return run_server_list(args, skills_dir)
    elif args.server_command == "add":
        return run_server_add(args, skills_dir)
    elif args.server_command == "show":
        return run_server_show(args, skills_dir)
    elif args.server_command == "validate":
        return run_server_validate(args, skills_dir)
    else:
        print_error(f"Unknown server command: {args.server_command}")
        return 1
