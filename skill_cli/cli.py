"""
Main CLI dispatcher for the skill command.

This module provides the entry point and argument parsing for all skill commands.
"""

import argparse
import sys
from typing import List, Optional

from . import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with all subcommands."""

    parser = argparse.ArgumentParser(
        prog="skill",
        description="DCF Skill CLI - Author, validate, and manage DCF skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  skill init                         Create a new skill (real or simulated)
  skill tool list                    List available tools
  skill tool add                     Add a new tool interactively
  skill server list                  List MCP servers
  skill server add                   Add a new MCP server
  skill validate                     Validate all skills
  skill generate                     Generate manifests and stub config
  skill list                         List all skills
  skill test                         Run test cases against stub server

Workflow:
  1. skill init          Create skill with tools and test cases
  2. skill validate      Validate skill definition
  3. skill generate      Generate manifests and stub config
  4. skill test          Run test cases against stub_mcp

For more information on a command:
  skill <command> --help
        """
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    parser.add_argument(
        "--skills-dir",
        default=None,
        help="Path to skills_src directory (default: auto-detect)"
    )

    parser.add_argument(
        "--generated-dir",
        default=None,
        help="Path to generated output directory (default: auto-detect)"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-essential output"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="count",
        default=0,
        help="Increase output verbosity (can be repeated)"
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="<command>"
    )

    # =========================================================================
    # init command - Create skills interactively
    # =========================================================================
    init_parser = subparsers.add_parser(
        "init",
        help="Create a new skill interactively",
        description="Create a new skill through guided interactive prompts. "
                    "Supports two modes: Real (for production with actual APIs) "
                    "and Simulated (for testing with stub_mcp and BDD test cases)."
    )
    init_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing skill files"
    )

    # =========================================================================
    # tool command - Manage tools
    # =========================================================================
    tool_parser = subparsers.add_parser(
        "tool",
        help="Manage MCP tools",
        description="List, add, or inspect MCP tools."
    )
    tool_subparsers = tool_parser.add_subparsers(
        dest="tool_command",
        title="tool commands",
        metavar="<subcommand>"
    )

    # tool list
    tool_list_parser = tool_subparsers.add_parser(
        "list",
        help="List available tools",
        description="List all tools defined in tools.yaml."
    )
    tool_list_parser.add_argument(
        "--server",
        help="Filter by server ID"
    )
    tool_list_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)"
    )

    # tool add
    tool_add_parser = tool_subparsers.add_parser(
        "add",
        help="Add a new tool interactively",
        description="Add a new tool to tools.yaml through guided prompts."
    )
    tool_add_parser.add_argument(
        "--server",
        help="Server ID to add the tool to (will prompt if not specified)"
    )

    # tool show
    tool_show_parser = tool_subparsers.add_parser(
        "show",
        help="Show details of a specific tool",
        description="Display detailed information about a tool."
    )
    tool_show_parser.add_argument(
        "tool_ref",
        help="Tool reference (serverId:toolName)"
    )

    # =========================================================================
    # server command - Manage MCP servers
    # =========================================================================
    server_parser = subparsers.add_parser(
        "server",
        help="Manage MCP servers",
        description="List, add, or inspect MCP servers."
    )
    server_subparsers = server_parser.add_subparsers(
        dest="server_command",
        title="server commands",
        metavar="<subcommand>"
    )

    # server list
    server_list_parser = server_subparsers.add_parser(
        "list",
        help="List MCP servers",
        description="List all servers defined in tools.yaml and registry.yaml."
    )
    server_list_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)"
    )

    # server add
    server_add_parser = server_subparsers.add_parser(
        "add",
        help="Add a new MCP server interactively",
        description="Add a new MCP server through guided prompts."
    )

    # server show
    server_show_parser = server_subparsers.add_parser(
        "show",
        help="Show details of a specific server",
        description="Display detailed information about a server."
    )
    server_show_parser.add_argument(
        "server_id",
        help="Server ID"
    )

    # server validate
    server_validate_parser = server_subparsers.add_parser(
        "validate",
        help="Validate all server connections",
        description="Test connectivity to all configured MCP servers."
    )

    # =========================================================================
    # validate command
    # =========================================================================
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate skill YAML files",
        description="Validate skill files against the JSON schema and check tool references."
    )
    validate_parser.add_argument(
        "skills",
        nargs="*",
        help="Specific skills to validate (default: all)"
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )
    validate_parser.add_argument(
        "--integrations",
        action="store_true",
        help="Also validate server connections and file paths"
    )
    validate_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # =========================================================================
    # generate command
    # =========================================================================
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate manifests and stub config",
        description="Generate JSON manifests from YAML skills and stub server configuration."
    )
    generate_parser.add_argument(
        "--manifests-only",
        action="store_true",
        help="Only generate skill manifests"
    )
    generate_parser.add_argument(
        "--stub-only",
        action="store_true",
        help="Only generate stub server config"
    )
    generate_parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Watch for changes and regenerate automatically"
    )
    generate_parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean generated directory before generating"
    )

    # =========================================================================
    # list command
    # =========================================================================
    list_parser = subparsers.add_parser(
        "list",
        help="List available skills",
        description="List all skills in the skills_src directory."
    )
    list_parser.add_argument(
        "--format",
        choices=["table", "json", "yaml", "names"],
        default="table",
        help="Output format (default: table)"
    )
    list_parser.add_argument(
        "--tags",
        help="Filter by tags (comma-separated)"
    )
    list_parser.add_argument(
        "--tools",
        action="store_true",
        help="Include tool information"
    )

    # =========================================================================
    # test command
    # =========================================================================
    test_parser = subparsers.add_parser(
        "test",
        help="Run test cases against stub server",
        description="Execute test cases defined in tools.yaml against the stub MCP server."
    )
    test_parser.add_argument(
        "--skill", "-s",
        action="append",
        dest="skills",
        help="Test specific skill (can be repeated)"
    )
    test_parser.add_argument(
        "--tool", "-t",
        action="append",
        dest="tools",
        help="Test specific tool (format: serverId:toolName)"
    )
    test_parser.add_argument(
        "--case", "-c",
        action="append",
        dest="cases",
        help="Test specific case ID"
    )
    test_parser.add_argument(
        "--stub-url",
        default="http://localhost:8765",
        help="Stub server URL (default: http://localhost:8765)"
    )
    test_parser.add_argument(
        "--coverage",
        action="store_true",
        help="Show coverage report"
    )
    test_parser.add_argument(
        "--format",
        choices=["text", "json", "junit"],
        default="text",
        help="Output format (default: text)"
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI."""

    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Import and run the appropriate command
    try:
        if args.command == "init":
            from .commands.init import run_init
            return run_init(args)

        elif args.command == "tool":
            from .commands.tool import run_tool
            return run_tool(args)

        elif args.command == "server":
            from .commands.server import run_server
            return run_server(args)

        elif args.command == "validate":
            from .commands.validate import run_validate
            return run_validate(args)

        elif args.command == "generate":
            from .commands.generate import run_generate
            return run_generate(args)

        elif args.command == "list":
            from .commands.list import run_list
            return run_list(args)

        elif args.command == "test":
            from .commands.test import run_test
            return run_test(args)

        else:
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        if args.verbose > 0:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
