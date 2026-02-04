"""
Test command implementation.

Runs test cases defined in tools.yaml against the stub MCP server.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
)


def parse_sse_response(body: str) -> Optional[Dict[str, Any]]:
    """
    Parse SSE (Server-Sent Events) response to extract JSON data.

    SSE format:
        event: message
        data: {"jsonrpc":"2.0",...}

    Returns the parsed JSON or None if parsing fails.
    """
    lines = body.strip().split("\n")
    for line in lines:
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    return None


class TestResult:
    """Holds test execution result."""

    def __init__(
        self,
        case_id: str,
        tool_ref: str,
        passed: bool,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ):
        self.case_id = case_id
        self.tool_ref = tool_ref
        self.passed = passed
        self.error = error
        self.latency_ms = latency_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "caseId": self.case_id,
            "toolRef": self.tool_ref,
            "passed": self.passed,
            "error": self.error,
            "latencyMs": self.latency_ms,
        }


def get_mcp_session(stub_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Initialize an MCP session with the stub server.

    Returns (session_id, error).
    """
    try:
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "skill-cli", "version": "0.1.0"},
            },
        }

        req = Request(
            f"{stub_url}/mcp",
            data=json.dumps(init_request).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            # Try both header names for compatibility
            session_id = response.headers.get("mcp-session-id") or response.headers.get("mcp-session")
            return session_id, None

    except HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        return None, f"Connection failed: {e.reason}"
    except Exception as e:
        return None, str(e)


def call_tool(
    stub_url: str,
    session_id: Optional[str],
    server_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], float]:
    """
    Call a tool on the stub MCP server.

    Returns (result, error, latency_ms).
    """
    start_time = time.time()

    try:
        call_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": f"{server_id}:{tool_name}",
                "arguments": arguments,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["mcp-session-id"] = session_id

        req = Request(
            f"{stub_url}/mcp",
            data=json.dumps(call_request).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urlopen(req, timeout=30) as response:
            latency_ms = (time.time() - start_time) * 1000
            body = response.read().decode("utf-8")

            # Handle SSE (Server-Sent Events) response format
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                result = parse_sse_response(body)
                if result is None:
                    return None, "Failed to parse SSE response", latency_ms
            else:
                result = json.loads(body)

            if "error" in result:
                return None, result["error"].get("message", "Unknown error"), latency_ms

            return result.get("result"), None, latency_ms

    except HTTPError as e:
        latency_ms = (time.time() - start_time) * 1000
        return None, f"HTTP {e.code}: {e.reason}", latency_ms
    except URLError as e:
        latency_ms = (time.time() - start_time) * 1000
        return None, f"Connection failed: {e.reason}", latency_ms
    except json.JSONDecodeError as e:
        latency_ms = (time.time() - start_time) * 1000
        return None, f"Invalid JSON response: {e}", latency_ms
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return None, str(e), latency_ms


def extract_test_cases(tools_registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all test cases from the tools registry.

    Returns list of test case objects with server/tool context.
    """
    cases = []
    servers = tools_registry.get("servers", {})

    for server_id, server_data in servers.items():
        for tool_name, tool_def in server_data.get("tools", {}).items():
            tool_ref = f"{server_id}:{tool_name}"

            for case in tool_def.get("cases", []):
                cases.append({
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "tool_ref": tool_ref,
                    "case_id": case.get("id", "unknown"),
                    "match": case.get("match", {}),
                    "response": case.get("response"),
                    "error_mode": case.get("errorMode"),
                })

    return cases


def build_test_input(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build test input from a case's match criteria.

    For exact/contains matches, use the value directly.
    For regex matches, generate a matching value.
    """
    match = case.get("match", {})
    strategy = match.get("strategy", "always")
    path = match.get("path", "")
    value = match.get("value", "")

    if strategy == "always":
        return {}

    if strategy == "exact":
        return {path: value}

    if strategy == "contains":
        return {path: [{"text": value}]}

    if strategy == "regex":
        # For regex, just use the pattern as input (it should match itself for simple patterns)
        return {path: value.replace(".*", "test ")}

    return {}


def filter_cases(
    cases: List[Dict[str, Any]],
    skills: Optional[List[str]] = None,
    tools: Optional[List[str]] = None,
    case_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter test cases by skill, tool, or case ID."""
    filtered = cases

    # Filter by tool reference
    if tools:
        filtered = [c for c in filtered if c["tool_ref"] in tools]

    # Filter by case ID
    if case_ids:
        filtered = [c for c in filtered if c["case_id"] in case_ids]

    # Filter by skill (requires loading skills to find tool refs)
    # This is a more complex filter that we'll skip for now

    return filtered


def run_test_cases(
    cases: List[Dict[str, Any]],
    stub_url: str,
    verbose: bool = False,
) -> List[TestResult]:
    """Run test cases against the stub server."""
    results = []

    # Get MCP session
    session_id, error = get_mcp_session(stub_url)
    if error:
        # Return all tests as failed
        for case in cases:
            results.append(TestResult(
                case_id=case["case_id"],
                tool_ref=case["tool_ref"],
                passed=False,
                error=f"Session init failed: {error}",
            ))
        return results

    # Run each test case
    for case in cases:
        case_id = case["case_id"]
        tool_ref = case["tool_ref"]

        # Build test input
        test_input = build_test_input(case)

        if verbose:
            print_info(f"Testing {tool_ref} / {case_id}")

        # Call the tool
        result, error, latency_ms = call_tool(
            stub_url=stub_url,
            session_id=session_id,
            server_id=case["server_id"],
            tool_name=case["tool_name"],
            arguments=test_input,
        )

        # Check for expected error mode
        error_mode = case.get("error_mode")
        if error_mode:
            # Test expects an error
            if error:
                results.append(TestResult(
                    case_id=case_id,
                    tool_ref=tool_ref,
                    passed=True,
                    latency_ms=latency_ms,
                ))
            else:
                results.append(TestResult(
                    case_id=case_id,
                    tool_ref=tool_ref,
                    passed=False,
                    error=f"Expected error mode '{error_mode}' but got success",
                    latency_ms=latency_ms,
                ))
        else:
            # Test expects success
            if error:
                results.append(TestResult(
                    case_id=case_id,
                    tool_ref=tool_ref,
                    passed=False,
                    error=error,
                    latency_ms=latency_ms,
                ))
            else:
                results.append(TestResult(
                    case_id=case_id,
                    tool_ref=tool_ref,
                    passed=True,
                    latency_ms=latency_ms,
                ))

    return results


def format_text_results(results: List[TestResult], verbose: bool = False) -> str:
    """Format test results as text."""
    lines = []

    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    # Show failed tests
    for r in failed:
        lines.append(f"{Colors.RED}✗{Colors.RESET} {r.tool_ref} / {r.case_id}")
        if r.error:
            lines.append(f"    {Colors.DIM}{r.error}{Colors.RESET}")

    # Show passed tests if verbose
    if verbose:
        for r in passed:
            latency = f" ({r.latency_ms:.0f}ms)" if r.latency_ms else ""
            lines.append(f"{Colors.GREEN}✓{Colors.RESET} {r.tool_ref} / {r.case_id}{latency}")

    # Summary
    lines.append("")
    total = len(results)
    pass_count = len(passed)
    fail_count = len(failed)

    if fail_count == 0:
        lines.append(f"{Colors.GREEN}All {total} tests passed{Colors.RESET}")
    else:
        lines.append(f"{Colors.RED}{fail_count} failed{Colors.RESET}, {Colors.GREEN}{pass_count} passed{Colors.RESET} ({total} total)")

    return "\n".join(lines)


def format_json_results(results: List[TestResult]) -> str:
    """Format test results as JSON."""
    passed = len([r for r in results if r.passed])
    failed = len([r for r in results if not r.passed])

    output = {
        "passed": passed,
        "failed": failed,
        "total": len(results),
        "results": [r.to_dict() for r in results],
    }

    return json.dumps(output, indent=2)


def format_junit_results(results: List[TestResult]) -> str:
    """Format test results as JUnit XML."""
    passed = len([r for r in results if r.passed])
    failed = len([r for r in results if not r.passed])
    total_time = sum(r.latency_ms or 0 for r in results) / 1000

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="skill-cli" tests="{len(results)}" failures="{failed}" time="{total_time:.3f}">',
    ]

    for r in results:
        time_attr = f' time="{r.latency_ms / 1000:.3f}"' if r.latency_ms else ""
        if r.passed:
            lines.append(f'  <testcase name="{r.tool_ref}/{r.case_id}"{time_attr}/>')
        else:
            lines.append(f'  <testcase name="{r.tool_ref}/{r.case_id}"{time_attr}>')
            error_msg = r.error.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if r.error else "Unknown error"
            lines.append(f'    <failure message="{error_msg}"/>')
            lines.append('  </testcase>')

    lines.append('</testsuite>')

    return "\n".join(lines)


def generate_coverage_report(
    cases: List[Dict[str, Any]],
    results: List[TestResult],
    tools_registry: Dict[str, Any],
) -> str:
    """Generate a coverage report showing which tools/cases were tested."""
    lines = []

    # Count tools and cases per server
    servers = tools_registry.get("servers", {})
    total_tools = 0
    total_cases = 0

    for server_id, server_data in servers.items():
        server_tools = server_data.get("tools", {})
        total_tools += len(server_tools)
        for tool_def in server_tools.values():
            total_cases += len(tool_def.get("cases", []))

    tested_cases = len(results)
    tested_tools = len(set(r.tool_ref for r in results))

    lines.append(f"\n{Colors.BOLD}Coverage Report{Colors.RESET}")
    lines.append(f"  Tools:  {tested_tools}/{total_tools} ({100 * tested_tools / total_tools:.0f}%)" if total_tools else "  Tools: 0")
    lines.append(f"  Cases:  {tested_cases}/{total_cases} ({100 * tested_cases / total_cases:.0f}%)" if total_cases else "  Cases: 0")

    return "\n".join(lines)


def run_test(args) -> int:
    """
    Run the test command.

    Returns exit code (0 for success, non-zero for test failures).
    """
    skills_dir = get_skills_dir(args)

    if not skills_dir.exists():
        print_error(f"Skills directory not found: {skills_dir}")
        return 1

    # Load tools registry
    tools_path = skills_dir / "tools.yaml"
    tools_registry, error = load_yaml_file(tools_path)
    if error:
        print_error(f"Failed to load tools.yaml: {error}")
        return 1

    # Extract test cases
    all_cases = extract_test_cases(tools_registry)

    if not all_cases:
        print_info("No test cases found in tools.yaml")
        return 0

    # Filter cases
    cases = filter_cases(
        all_cases,
        skills=args.skills,
        tools=args.tools,
        case_ids=args.cases,
    )

    if not cases:
        print_warning("No test cases match the specified filters")
        return 0

    if not args.quiet:
        print_header(f"Running {len(cases)} test cases")
        print_info(f"Stub server: {args.stub_url}")

    # Run tests
    results = run_test_cases(cases, args.stub_url, args.verbose > 0)

    # Format output
    if args.format == "json":
        output = format_json_results(results)
    elif args.format == "junit":
        output = format_junit_results(results)
    else:
        output = format_text_results(results, args.verbose > 0)

    print(output)

    # Show coverage if requested
    if args.coverage:
        coverage = generate_coverage_report(cases, results, tools_registry)
        print(coverage)

    # Return exit code based on test results
    failed = len([r for r in results if not r.passed])
    return 1 if failed > 0 else 0
