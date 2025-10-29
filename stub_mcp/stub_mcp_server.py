"""Streamable HTTP stub MCP server for deterministic tool responses."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from mcp import types
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

CONFIG_PATH = Path(os.getenv("STUB_CONFIG", "generated/stub/stub_config.json"))
STREAMABLE_HTTP_PATH = os.getenv("STUB_MCP_PATH", "/mcp")
APP_HOST = os.getenv("STUB_MCP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("STUB_MCP_PORT", "8765"))


def _load_config_from_disk(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ensure_schema(value: Any, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return default or {"type": "object", "properties": {}}


def _dot_get(obj: Any, path: str) -> Any:
    if not isinstance(obj, dict):
        return None
    expr = path.strip()
    if expr.startswith("$."):
        expr = expr[2:]
    if not expr:
        return None
    current: Any = obj
    for segment in (part for part in expr.split(".") if part):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _match_case(case: Dict[str, Any], arguments: Dict[str, Any]) -> bool:
    match_cfg = case.get("match") or {}
    strategy = (match_cfg.get("strategy") or "").lower()
    expr = (match_cfg.get("expr") or "")
    expected = (match_cfg.get("value") or "")

    if strategy == "exact":
        actual = _dot_get(arguments, expr) if expr else None
        return (None if actual is None else str(actual)) == expected

    if strategy == "regex":
        try:
            import re

            return re.search(expected, json.dumps(arguments, ensure_ascii=False)) is not None
        except re.error:
            return False

    if strategy == "jsonpath":
        actual = _dot_get(arguments, expr)
        return (None if actual is None else json.dumps(actual, ensure_ascii=False)) == expected

    return False


def _pick_case(tool: Dict[str, Any], arguments: Dict[str, Any]) -> tuple[Any, int, Optional[Dict[str, Any]]]:
    latency_default = int(((tool.get("latencyMs") or {}).get("default") or 0))
    for case in tool.get("cases") or []:
        if _match_case(case, arguments):
            response = case.get("response")
            latency_override = case.get("latencyMsOverride")
            response_payload = response if response is not None else tool.get("defaultResponse")
            latency_value = int(latency_override) if isinstance(latency_override, int) else latency_default
            return response_payload, latency_value, case
    return tool.get("defaultResponse"), latency_default, None


_last_call_at: Dict[tuple[str, str], float] = {}
_rate_lock = asyncio.Lock()

_VALID_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _sanitize_tool_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    if not sanitized:
        return "tool"
    if not _VALID_TOOL_NAME_RE.match(sanitized):
        return "tool"
    return sanitized


async def _respect_rate_limit(server_id: str, tool_name: str, tool: Dict[str, Any]) -> None:
    rps = int(((tool.get("rateLimit") or {}).get("rps") or 0))
    if rps <= 0:
        return

    async with _rate_lock:
        now = time.perf_counter()
        min_gap = 1.0 / float(max(1, rps))
        last = _last_call_at.get((server_id, tool_name), 0.0)
        gap = now - last
        if gap < min_gap:
            await asyncio.sleep(min_gap - gap)
        _last_call_at[(server_id, tool_name)] = time.perf_counter()


@dataclass
class StubCallOutcome:
    payload: Any
    is_error: bool
    error_message: Optional[str] = None


@dataclass
class StubToolEntry:
    server_id: str
    tool_name: str
    raw_name: str
    raw: Dict[str, Any]

    def build_tool_definition(self) -> types.Tool:
        description = self.raw.get("description") or None
        params_schema = _ensure_schema(self.raw.get("paramsSchema"))
        result_schema_raw = self.raw.get("resultSchema")
        result_schema = result_schema_raw if isinstance(result_schema_raw, dict) else None
        meta: Dict[str, Any] = {
            "serverId": self.server_id,
            "version": self.raw.get("version") or None,
        }
        default_response = self.raw.get("defaultResponse")
        if default_response is not None:
            meta["defaultResponse"] = default_response
        latency_default = ((self.raw.get("latencyMs") or {}).get("default"))
        if latency_default is not None:
            meta["latencyMs"] = latency_default
        rate_limit = ((self.raw.get("rateLimit") or {}).get("rps"))
        if rate_limit is not None:
            meta["rateLimitRps"] = rate_limit

        meta["originalName"] = self.raw_name

        return types.Tool(
            name=self.tool_name,
            description=description,
            inputSchema=params_schema,
            outputSchema=result_schema,
            meta=meta,
        )

    async def invoke(self, arguments: Dict[str, Any]) -> StubCallOutcome:
        await _respect_rate_limit(self.server_id, self.tool_name, self.raw)
        response, latency_ms, matched_case = _pick_case(self.raw, arguments)

        if latency_ms and latency_ms > 0:
            await asyncio.sleep(latency_ms / 1000.0)

        error_mode = (matched_case or {}).get("errorMode")
        if isinstance(error_mode, str):
            mode = error_mode.lower().strip()
            if mode == "timeout":
                await asyncio.sleep(10)
            elif mode == "throw":
                return StubCallOutcome(payload=None, is_error=True, error_message="stub_thrown_error")
            elif mode == "http_500":
                return StubCallOutcome(
                    payload=None,
                    is_error=True,
                    error_message="500: internal server error (stub)",
                )

        payload = response
        if payload is None:
            payload = self.raw.get("defaultResponse")

        return StubCallOutcome(payload=payload, is_error=False)


class StubConfigManager:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._cache_config: Dict[str, Any] | None = None
        self._tool_index: Dict[str, StubToolEntry] = {}
        self._raw_index: Dict[str, StubToolEntry] = {}
        self._mtime: Optional[float] = None

    def refresh(self) -> bool:
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError as exc:
            if self._cache_config is None:
                self._cache_config = {"servers": {}}
                self._tool_index = {}
            print(f"[stub-mcp] stub config missing at {self._path}: {exc}", file=sys.stderr)
            return False
        except OSError as exc:
            print(f"[stub-mcp] unable to stat config {self._path}: {exc}", file=sys.stderr)
            return False

        if self._cache_config is not None and self._mtime == mtime:
            return False

        try:
            config = _load_config_from_disk(self._path)
        except Exception as exc:  # noqa: BLE001
            print(f"[stub-mcp] failed to load config {self._path}: {exc}", file=sys.stderr)
            return False

        servers = config.get("servers") or {}
        new_index: Dict[str, StubToolEntry] = {}
        duplicates: Dict[str, set[str]] = {}
        raw_seen: Dict[str, str] = {}
        for server_id, server_payload in servers.items():
            tools_payload = (server_payload or {}).get("tools") or {}
            for raw_tool_name, tool_config in tools_payload.items():
                tool_config = tool_config or {}
                meta_block = tool_config.get("meta") or {}
                original_name = (meta_block.get("originalToolName") or raw_tool_name)

                if raw_tool_name in raw_seen:
                    duplicates.setdefault(raw_tool_name, set()).update({raw_seen[raw_tool_name], server_id})
                    continue

                sanitized = _sanitize_tool_name(raw_tool_name)
                unique_name = sanitized
                if unique_name in new_index:
                    counter = 2
                    base = sanitized
                    while f"{base}_{counter}" in new_index:
                        counter += 1
                    unique_name = f"{base}_{counter}"

                entry = StubToolEntry(
                    server_id=server_id,
                    tool_name=unique_name,
                    raw_name=original_name,
                    raw=tool_config,
                )
                new_index[unique_name] = entry
                raw_seen[raw_tool_name] = server_id

        if duplicates:
            for name, server_ids in duplicates.items():
                joined = ", ".join(sorted(server_ids))
                print(
                    f"[stub-mcp] duplicate tool '{name}' encountered for servers: {joined}; using first definition only",
                    file=sys.stderr,
                )

        self._cache_config = config
        self._tool_index = new_index
        self._raw_index = {entry.raw_name: entry for entry in new_index.values()}
        self._mtime = mtime
        print(f"[stub-mcp] loaded {len(new_index)} tools from {self._path}")
        return True

    def list_tool_entries(self) -> Iterable[StubToolEntry]:
        self.refresh()
        return self._tool_index.values()

    def get_tool(self, name: str) -> Optional[StubToolEntry]:
        self.refresh()
        entry = self._tool_index.get(name)
        if entry is not None:
            return entry
        return self._raw_index.get(name)


CONFIG = StubConfigManager(CONFIG_PATH)
server = Server(name="stub-mcp-server")


@server.list_tools()
async def list_tools(_: types.ListToolsRequest | None = None) -> types.ListToolsResult:
    entries = list(CONFIG.list_tool_entries())
    # Deterministic ordering by serverId then toolName
    entries.sort(key=lambda item: (item.server_id, item.tool_name))
    tools = [entry.build_tool_definition() for entry in entries]
    return types.ListToolsResult(tools=tools)


@server.call_tool()
async def call_tool(tool_name: str, arguments: Dict[str, Any]) -> types.CallToolResult | Dict[str, Any] | Iterable[types.ContentBlock]:
    entry = CONFIG.get_tool(tool_name)
    if entry is None:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"unknown tool '{tool_name}'",
                )
            ],
            structuredContent=None,
            isError=True,
        )

    outcome = await entry.invoke(arguments or {})
    if outcome.is_error:
        message = outcome.error_message or "stub tool error"
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=message)],
            structuredContent=None,
            isError=True,
        )

    payload = outcome.payload
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {"result": None}

    if isinstance(payload, (list, tuple)):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = str(payload)
    return [types.TextContent(type="text", text=text)]


session_manager = StreamableHTTPSessionManager(app=server)
streamable_http_app = StreamableHTTPASGIApp(session_manager)


def _healthcheck_route(_request):
    return JSONResponse({"ok": True})


app = Starlette(
    routes=[
        Route(STREAMABLE_HTTP_PATH, streamable_http_app, methods=["GET", "POST"]),
        Route("/healthz", _healthcheck_route, methods=["GET"]),
    ],
    lifespan=lambda _: session_manager.run(),
)


def main() -> None:
    import uvicorn

    uvicorn.run("stub_mcp_server:app", host=APP_HOST, port=APP_PORT, log_level="info")


if __name__ == "__main__":
    main()