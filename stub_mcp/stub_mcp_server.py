# file: stub_mcp_server.py
# Tiny MCP-like stub server for testing tools via JSON-RPC 2.0.
# - stdio mode: pure stdlib (default)
# - websocket mode: optional (requires `websockets` pkg) -> set STUB_MCP_WS=1
#
# Config file: JSON produced by csv_to_stub_config() => generated/stub/stub_config.json
# {
#   "servers": {
#     "<serverId>": {
#       "tools": {
#         "<toolName>": {
#           "version": "...",
#           "description": "...",
#           "paramsSchema": {...},
#           "resultSchema": {...},
#           "defaultResponse": {...},
#           "rateLimit": {"rps": int},
#           "latencyMs": {"default": int},
#           "cases": [
#             {
#               "caseId": "...",
#               "match": {"strategy": "exact|regex|jsonpath", "expr": "...", "value": "..."},
#               "response": {...},
#               "latencyMsOverride": int|None,
#               "errorMode": "throw|timeout|http_500"|None,
#               "weight": float|None
#             }
#           ]
#         }
#       }
#     }
#   }
# }
#
# Supported JSON-RPC methods:
# - "initialize": { "jsonrpc":"2.0","id":1,"method":"initialize","params":{} }
# - "tools/list": { "id":2,"method":"tools/list","params":{"serverId":"X"} }
# - "tools/call": { "id":3,"method":"tools/call","params":{"serverId":"X","toolName":"T","arguments":{...}} }
# - "shutdown":   { "id":4,"method":"shutdown","params":{} }

import os
import sys
import re
import json
import time
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

CONFIG_PATH = os.getenv("STUB_CONFIG", "generated/stub/stub_config.json")
WS_ENABLE = os.getenv("STUB_MCP_WS", "0") == "1"
WS_HOST = os.getenv("STUB_MCP_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("STUB_MCP_PORT", "8765"))

# --------- config & matching helpers (stdlib only) ---------

def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _get_tool(cfg: Dict[str, Any], server_id: str, tool_name: str) -> Optional[Dict[str, Any]]:
    return (((cfg.get("servers") or {}).get(server_id) or {}).get("tools") or {}).get(tool_name)

def _dot_get(d: Any, path: str) -> Any:
    # Very small JSONPath-ish: support "$.a.b.c" and "a.b.c"
    if not isinstance(d, dict):
        return None
    p = path.strip()
    if p.startswith("$."):
        p = p[2:]
    for seg in [s for s in p.split(".") if s]:
        if not isinstance(d, dict) or seg not in d:
            return None
        d = d[seg]
    return d

def _match_case(case: Dict[str, Any], args: Dict[str, Any]) -> bool:
    m = case.get("match") or {}
    strategy = (m.get("strategy") or "").lower()
    expr = (m.get("expr") or "")
    val = (m.get("value") or "")
    if strategy == "exact":
        # expr is a dotted key path; compare stringified value
        actual = _dot_get(args, expr) if expr else None
        return (None if actual is None else str(actual)) == val
    if strategy == "regex":
        try:
            return re.search(val, json.dumps(args, ensure_ascii=False)) is not None
        except Exception:
            return False
    if strategy == "jsonpath":
        actual = _dot_get(args, expr)
        return (None if actual is None else json.dumps(actual, ensure_ascii=False)) == val
    return False

def _pick_case(tool: Dict[str, Any], args: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], int]:
    # return (response_json_or_None, latency_ms)
    latency_default = int(((tool.get("latencyMs") or {}).get("default") or 0))
    cases = tool.get("cases") or []
    matches = [c for c in cases if _match_case(c, args)]
    if not matches:
        return (tool.get("defaultResponse"), latency_default)
    # No RNG: pick the first match (deterministic). If weight is present, still pick first.
    chosen = matches[0]
    resp = chosen.get("response")
    latency = chosen.get("latencyMsOverride")
    return (resp if resp is not None else tool.get("defaultResponse"),
            int(latency) if isinstance(latency, int) else latency_default)

_last_call_at: Dict[Tuple[str, str], float] = {}  # (serverId, toolName) -> epoch seconds

def _respect_rate_limit(server_id: str, tool: Dict[str, Any]) -> None:
    rps = int(((tool.get("rateLimit") or {}).get("rps") or 0))
    if rps <= 0:
        return
    key = (server_id, (tool.get("name") or ""))  # tool["name"] may be missing; harmless
    now = time.time()
    min_gap = 1.0 / float(max(1, rps))
    last = _last_call_at.get(key, 0.0)
    gap = now - last
    if gap < min_gap:
        time.sleep(min_gap - gap)
    _last_call_at[key] = time.time()

def _handle_call(cfg: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    server_id = params.get("serverId")
    tool_name = params.get("toolName")
    args = params.get("arguments") or {}
    if not isinstance(server_id, str) or not isinstance(tool_name, str):
        raise ValueError("tools/call requires string serverId and toolName")
    tool = _get_tool(cfg, server_id, tool_name)
    if not tool:
        return {"error": f"unknown tool {server_id}:{tool_name}"}
    _respect_rate_limit(server_id, tool)
    resp, latency_ms = _pick_case(tool, args)
    if latency_ms and latency_ms > 0:
        time.sleep(latency_ms / 1000.0)
    # honor simple errorMode if present on the matched case (already chosen)
    # we didn’t surface which case fired; do a second check
    for c in (tool.get("cases") or []):
        if _match_case(c, args):
            em = c.get("errorMode")
            if em == "timeout":
                time.sleep(10)  # crude
            if em == "throw":
                return {"error": "stub_thrown_error"}
            if em == "http_500":
                return {"error": "500: internal server error (stub)"}
            break
    return {"ok": True, "result": resp}

def _list_tools(cfg: Dict[str, Any], server_id: str) -> Dict[str, Any]:
    srv = (cfg.get("servers") or {}).get(server_id) or {}
    tools = srv.get("tools") or {}
    out = []
    for name, t in tools.items():
        out.append({
            "toolName": name,
            "version": t.get("version"),
            "description": t.get("description"),
            "paramsSchema": t.get("paramsSchema"),
            "resultSchema": t.get("resultSchema")
        })
    return {"ok": True, "tools": out}

# --------- stdio JSON-RPC 2.0 loop ---------

def _rpc_response(id_, result=None, error: Optional[str] = None) -> str:
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": id_, "error": {"code": -32000, "message": error}})
    return json.dumps({"jsonrpc": "2.0", "id": id_, "result": result})

def run_stdio() -> None:
    cfg = _load_config(CONFIG_PATH)
    print(json.dumps({"jsonrpc": "2.0", "method": "server/ready", "params": {"ts": datetime.utcnow().isoformat()}}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            mid = req.get("id")
            meth = req.get("method")
            params = req.get("params") or {}
            if meth == "initialize":
                print(_rpc_response(mid, {"ok": True, "mode": "stdio"}), flush=True)
            elif meth == "tools/list":
                result = _list_tools(cfg, params.get("serverId") or "")
                print(_rpc_response(mid, result), flush=True)
            elif meth == "tools/call":
                result = _handle_call(cfg, params)
                if "error" in result:
                    print(_rpc_response(mid, None, result["error"]), flush=True)
                else:
                    print(_rpc_response(mid, result), flush=True)
            elif meth == "shutdown":
                print(_rpc_response(mid, {"ok": True}), flush=True)
                break
            else:
                print(_rpc_response(mid, None, f"unknown method: {meth}"), flush=True)
        except Exception as e:
            # best-effort error
            try:
                mid = (req.get("id") if isinstance(req, dict) else None)
            except Exception:
                mid = None
            print(_rpc_response(mid, None, f"{e.__class__.__name__}: {e}"), flush=True)

# --------- optional websocket server ---------

async def _ws_handler(websocket):
    cfg = _load_config(CONFIG_PATH)
    await websocket.send(json.dumps({"jsonrpc": "2.0", "method": "server/ready", "params": {"ts": datetime.utcnow().isoformat(), "mode": "ws"}}))
    async for msg in websocket:
        try:
            req = json.loads(msg)
            mid = req.get("id")
            meth = req.get("method")
            params = req.get("params") or {}
            if meth == "initialize":
                await websocket.send(_rpc_response(mid, {"ok": True, "mode": "ws"}))
            elif meth == "tools/list":
                result = _list_tools(cfg, params.get("serverId") or "")
                await websocket.send(_rpc_response(mid, result))
            elif meth == "tools/call":
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, _handle_call, cfg, params)
                if "error" in result:
                    await websocket.send(_rpc_response(mid, None, result["error"]))
                else:
                    await websocket.send(_rpc_response(mid, result))
            elif meth == "shutdown":
                await websocket.send(_rpc_response(mid, {"ok": True}))
                break
            else:
                await websocket.send(_rpc_response(mid, None, f"unknown method: {meth}"))
        except Exception as e:
            mid = None
            try:
                mid = req.get("id")
            except Exception:
                pass
            await websocket.send(_rpc_response(mid, None, f"{e.__class__.__name__}: {e}"))

def run_ws() -> None:
    try:
        import websockets  # type: ignore
    except Exception:
        print("websocket mode requested but 'websockets' is not installed; falling back to stdio", file=sys.stderr)
        run_stdio()
        return
    loop = asyncio.get_event_loop()
    start_server = websockets.serve(_ws_handler, WS_HOST, WS_PORT, max_size=8 * 1024 * 1024)
    loop.run_until_complete(start_server)
    print(f"stub MCP websocket listening on ws://{WS_HOST}:{WS_PORT}", flush=True)
    loop.run_forever()

if __name__ == "__main__":
    if WS_ENABLE:
        run_ws()
    else:
        run_stdio()
