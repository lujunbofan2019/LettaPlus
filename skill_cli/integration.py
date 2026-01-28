"""
Integration validation and resource memory for the skill CLI.

Handles:
- Validation of MCP server connections (HTTP, SSE, stdio)
- Validation of file paths and other resources
- Caching known resources for quick reuse
"""

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .utils import (
    Colors,
    load_yaml_file,
    print_error,
    print_info,
    print_success,
    print_warning,
    save_yaml_file,
)


# =============================================================================
# RESOURCE CACHE (Remember known resources)
# =============================================================================

CACHE_FILE = ".skill_cli_cache.yaml"


def get_cache_path(skills_dir: Path) -> Path:
    """Get path to the resource cache file."""
    return skills_dir / CACHE_FILE


def load_resource_cache(skills_dir: Path) -> Dict[str, Any]:
    """Load the resource cache."""
    cache_path = get_cache_path(skills_dir)
    data, error = load_yaml_file(cache_path)
    if error or not data:
        return {
            "servers": {},  # serverId -> {transport, endpoint, path, last_used, validated}
            "endpoints": [],  # List of recently used endpoints for quick selection
            "commands": [],  # List of recently used stdio commands
        }
    return data


def save_resource_cache(skills_dir: Path, cache: Dict[str, Any]) -> Optional[str]:
    """Save the resource cache."""
    cache_path = get_cache_path(skills_dir)
    return save_yaml_file(cache_path, cache)


def remember_server(
    skills_dir: Path,
    server_id: str,
    transport: str,
    endpoint: str,
    path: str = "",
    command: str = "",
    validated: bool = False
):
    """Remember a server configuration for quick reuse."""
    cache = load_resource_cache(skills_dir)

    # Update servers
    cache["servers"][server_id] = {
        "transport": transport,
        "endpoint": endpoint,
        "path": path,
        "command": command,
        "validated": validated,
    }

    # Update recent endpoints
    if transport in ("streamable_http", "sse") and endpoint:
        full_endpoint = f"{endpoint}{path}" if path else endpoint
        if full_endpoint not in cache["endpoints"]:
            cache["endpoints"].insert(0, full_endpoint)
            cache["endpoints"] = cache["endpoints"][:10]  # Keep last 10

    # Update recent commands
    if transport == "stdio" and command:
        if command not in cache["commands"]:
            cache["commands"].insert(0, command)
            cache["commands"] = cache["commands"][:10]  # Keep last 10

    save_resource_cache(skills_dir, cache)


def get_known_servers(skills_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Get all known servers from cache."""
    cache = load_resource_cache(skills_dir)
    return cache.get("servers", {})


def get_recent_endpoints(skills_dir: Path) -> List[str]:
    """Get recently used endpoints."""
    cache = load_resource_cache(skills_dir)
    return cache.get("endpoints", [])


def get_recent_commands(skills_dir: Path) -> List[str]:
    """Get recently used stdio commands."""
    cache = load_resource_cache(skills_dir)
    return cache.get("commands", [])


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_http_endpoint(
    endpoint: str,
    path: str = "",
    timeout: float = 5.0
) -> Tuple[bool, str]:
    """
    Validate an HTTP/HTTPS endpoint is reachable.

    Returns (success, message).
    """
    full_url = f"{endpoint.rstrip('/')}{path}"

    try:
        # Try a simple HEAD request first (faster)
        req = Request(full_url, method="HEAD")
        req.add_header("User-Agent", "skill-cli/0.1.0")

        with urlopen(req, timeout=timeout) as response:
            return True, f"Reachable (HTTP {response.status})"

    except HTTPError as e:
        # HTTP errors still mean the server is reachable
        if e.code in (404, 405, 401, 403):
            return True, f"Reachable (HTTP {e.code} - endpoint exists)"
        return False, f"HTTP error: {e.code} {e.reason}"

    except URLError as e:
        return False, f"Connection failed: {e.reason}"

    except socket.timeout:
        return False, f"Connection timed out after {timeout}s"

    except Exception as e:
        return False, f"Error: {e}"


def validate_mcp_endpoint(
    endpoint: str,
    path: str = "/mcp",
    timeout: float = 5.0
) -> Tuple[bool, str]:
    """
    Validate an MCP endpoint by attempting to initialize a session.

    Returns (success, message).
    """
    full_url = f"{endpoint.rstrip('/')}{path}"

    try:
        # Send MCP initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "skill-cli", "version": "0.1.0"},
            },
        }

        req = Request(
            full_url,
            data=json.dumps(init_request).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)

            if "result" in result:
                return True, "MCP server responding"
            elif "error" in result:
                return True, f"MCP server responding (error: {result['error'].get('message', 'unknown')})"
            else:
                return True, "MCP endpoint reachable"

    except HTTPError as e:
        if e.code == 405:
            return True, "Endpoint exists (may need proper MCP request)"
        return False, f"HTTP error: {e.code} {e.reason}"

    except URLError as e:
        return False, f"Connection failed: {e.reason}"

    except json.JSONDecodeError:
        return True, "Endpoint reachable (non-JSON response)"

    except Exception as e:
        return False, f"Error: {e}"


def validate_stdio_command(command: str) -> Tuple[bool, str]:
    """
    Validate a stdio command/executable exists.

    Returns (success, message).
    """
    if not command:
        return False, "No command specified"

    # Split command to get the executable
    parts = command.split()
    executable = parts[0]

    # Check if it's an absolute path
    if os.path.isabs(executable):
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return True, f"Executable found: {executable}"
        elif os.path.isfile(executable):
            return False, f"File exists but not executable: {executable}"
        else:
            return False, f"File not found: {executable}"

    # Check if it's in PATH
    found = shutil.which(executable)
    if found:
        return True, f"Found in PATH: {found}"

    return False, f"Command not found: {executable}"


def validate_file_path(file_path: str, base_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Validate a file path exists.

    Returns (success, message).
    """
    if not file_path:
        return False, "No path specified"

    path = Path(file_path)

    # Handle relative paths
    if not path.is_absolute() and base_dir:
        path = base_dir / path

    if path.exists():
        if path.is_file():
            size = path.stat().st_size
            return True, f"File exists ({size} bytes)"
        elif path.is_dir():
            return True, "Directory exists"
        else:
            return True, "Path exists"

    return False, f"Path not found: {path}"


def validate_server_connection(
    transport: str,
    endpoint: str = "",
    path: str = "",
    command: str = "",
    verbose: bool = True
) -> Tuple[bool, str]:
    """
    Validate a server connection based on transport type.

    Returns (success, message).
    """
    if transport == "streamable_http":
        if verbose:
            print_info(f"Validating HTTP endpoint: {endpoint}{path}")
        return validate_mcp_endpoint(endpoint, path)

    elif transport == "sse":
        if verbose:
            print_info(f"Validating SSE endpoint: {endpoint}{path}")
        # SSE endpoints should at least be HTTP reachable
        return validate_http_endpoint(endpoint, path)

    elif transport == "stdio":
        if verbose:
            print_info(f"Validating command: {command}")
        return validate_stdio_command(command)

    else:
        return False, f"Unknown transport: {transport}"


# =============================================================================
# INTERACTIVE HELPERS
# =============================================================================

def prompt_with_suggestions(
    prompt: str,
    suggestions: List[str],
    default: str = ""
) -> str:
    """
    Prompt for input with suggestions from cache.

    Shows numbered suggestions for quick selection.
    """
    from .utils import prompt_input

    if suggestions:
        print(f"{Colors.DIM}Recent:{Colors.RESET}")
        for i, suggestion in enumerate(suggestions[:5], 1):
            print(f"  {Colors.CYAN}{i}{Colors.RESET}. {suggestion}")
        print()
        print_info("Enter a number to select, or type a new value")

    value = prompt_input(prompt, default=default)

    # Check if user entered a number
    if value.isdigit():
        idx = int(value) - 1
        if 0 <= idx < len(suggestions):
            return suggestions[idx]

    return value


def prompt_server_with_memory(
    skills_dir: Path,
    prompt_text: str = "Select or enter server"
) -> Optional[Dict[str, Any]]:
    """
    Prompt for server selection with memory of known servers.

    Returns server config dict or None if cancelled.
    """
    from .utils import prompt_choice, prompt_confirm, prompt_input

    known = get_known_servers(skills_dir)

    if known:
        print_info("Known servers:")
        print()
        server_list = list(known.items())
        for i, (sid, config) in enumerate(server_list, 1):
            transport = config.get("transport", "?")
            endpoint = config.get("endpoint", "")
            validated = "✓" if config.get("validated") else "?"
            print(f"  {Colors.CYAN}{i}{Colors.RESET}. {sid} ({transport}) {validated}")
            if endpoint:
                print(f"      {Colors.DIM}{endpoint}{Colors.RESET}")
        print()
        print(f"  {Colors.CYAN}{len(server_list) + 1}{Colors.RESET}. [Enter new server]")
        print()

        selection = prompt_input("Select server (number or new ID)")

        if selection.isdigit():
            idx = int(selection) - 1
            if 0 <= idx < len(server_list):
                server_id, config = server_list[idx]
                return {"id": server_id, **config}
            elif idx == len(server_list):
                # User wants to enter new server
                pass
            else:
                return None
        elif selection in known:
            return {"id": selection, **known[selection]}
        else:
            # Treat as new server ID
            return prompt_new_server(skills_dir, selection)

    return prompt_new_server(skills_dir)


def prompt_new_server(
    skills_dir: Path,
    server_id: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Prompt for new server configuration.

    Returns server config dict or None if cancelled.
    """
    from .utils import prompt_choice, prompt_confirm, prompt_input

    if not server_id:
        server_id = prompt_input("Server ID (e.g., search, llm, myapi)")
        if not server_id:
            return None

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
        recent = get_recent_endpoints(skills_dir)
        endpoint = prompt_with_suggestions(
            "Endpoint URL",
            recent,
            default="http://localhost:8765"
        )

        path = prompt_input("Path (e.g., /mcp)", default="/mcp")

    elif transport == "stdio":
        print()
        recent = get_recent_commands(skills_dir)
        command = prompt_with_suggestions(
            "Command to run",
            recent,
            default=""
        )

    # Validate
    print()
    if prompt_confirm("Validate connection now?", default=True):
        success, message = validate_server_connection(
            transport, endpoint, path, command
        )
        if success:
            print_success(f"Validation: {message}")
            validated = True
        else:
            print_warning(f"Validation failed: {message}")
            if not prompt_confirm("Continue anyway?", default=False):
                return None
            validated = False
    else:
        validated = False

    # Remember this server
    remember_server(
        skills_dir, server_id, transport, endpoint, path, command, validated
    )

    return {
        "id": server_id,
        "transport": transport,
        "endpoint": endpoint,
        "path": path,
        "command": command,
        "validated": validated,
    }


def validate_skill_integrations(
    skills_dir: Path,
    skill_name: str,
    verbose: bool = True
) -> List[Tuple[str, bool, str]]:
    """
    Validate all integrations for a skill.

    Returns list of (resource_name, success, message).
    """
    results = []

    # Load skill
    skill_path = skills_dir / "skills" / f"{skill_name}.skill.yaml"
    skill_data, error = load_yaml_file(skill_path)
    if error:
        return [("skill_file", False, error)]

    # Load registry
    registry_path = skills_dir / "registry.yaml"
    registry, _ = load_yaml_file(registry_path)
    servers = (registry or {}).get("servers", {})

    # Check each tool's server
    tools = skill_data.get("spec", {}).get("tools", [])
    for tool in tools:
        ref = tool.get("ref", "")
        if ":" in ref:
            server_id, tool_name = ref.split(":", 1)
            resource_name = f"server:{server_id}"

            if server_id in servers:
                server_config = servers[server_id]
                transport = server_config.get("transport", "streamable_http")
                endpoint = server_config.get("endpoint", "")
                path = server_config.get("path", "")
                command = server_config.get("command", "")

                if verbose:
                    print_info(f"Checking {resource_name}...")

                success, message = validate_server_connection(
                    transport, endpoint, path, command, verbose=False
                )
                results.append((resource_name, success, message))
            else:
                results.append((resource_name, False, "Server not configured in registry.yaml"))

    # Check data source files
    data_sources = skill_data.get("spec", {}).get("dataSources", [])
    for ds in data_sources:
        if "file" in ds:
            file_path = ds["file"]
            resource_name = f"file:{file_path}"

            if verbose:
                print_info(f"Checking {resource_name}...")

            success, message = validate_file_path(file_path, skill_path.parent)
            results.append((resource_name, success, message))

    return results
