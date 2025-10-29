import os
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict


DEFAULT_STUB_CONFIG_FILENAME = "stub_config.json"

_VALID_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _sanitize_tool_name(name: str) -> str:
    """Return a legal MCP tool identifier, replacing illegal characters early."""

    name = (name or "").strip()
    if _VALID_TOOL_NAME_RE.fullmatch(name):
        return name

    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        sanitized = "tool"
    if not _VALID_TOOL_NAME_RE.fullmatch(sanitized):
        sanitized = "tool"
    return sanitized

def csv_to_stub_config(mcp_tools_csv_path: str = "/app/skills_src/mcp_tools.csv",
                       mcp_cases_csv_path: str = "/app/skills_src/mcp_cases.csv",
                       out_path: str = "/app/generated/stub/stub_config.json") -> Dict[str, Any]:
    """
    Generate a deterministic stub MCP server configuration from local CSV files.

    Inputs:
      1) mcp_tools_csv_path
         Columns (strings unless noted):
           - serverId            (logical server id; required)
           - toolName            (required)
           - version
           - description
           - paramsSchema.json   (JSON; default {"type":"object","properties":{}})
           - resultSchema.json   (JSON; default {})
           - defaultResponse.json (JSON; default {})
           - rateLimit.rps       (int; default 0)
           - latencyMs.default   (int; default 0)

      2) mcp_cases_csv_path
         Optional; zero or more rows mapping input matching -> response overrides:
           - serverId, toolName, caseId
           - match.strategy  in {exact, jsonpath, regex}
           - match.expr      (JSONPath or key, depending on strategy)
           - match.value     (string; for exact compare or regex)
           - response.json   (JSON; returned when match fires)
           - latencyMs.override (int; optional)
           - errorMode       in {throw, timeout, http_500} (optional)
           - weight          (float; optional; for multiple matches)

    Output:
      - Single JSON file at out_path with shape:
        {
          "servers": {
            "<serverId>": {
              "tools": {
                "<toolName>": {
                  "version": "...",
                  "description": "...",
                  "paramsSchema": {...},
                  "resultSchema": {...},
                  "defaultResponse": {...},
                  "rateLimit": {"rps": int},
                  "latencyMs": {"default": int},
                  "cases": [ { ... }, ... ]
                }
              }
            }
          }
        }

    Return:
      {
        "ok": bool,
        "exit_code": int,         # 0 ok, 4 error
        "status": str or None,
        "error": str or None,
        "written_file": str or None,
        "tool_count": int,
        "case_count": int,
        "warnings": [str]
      }

    Notes:
      - The stub MCP server (to be implemented) can read this file to expose tools and case-based behaviors
        without any external dependency. Real vs stub endpoints are chosen by your loader resolver at runtime.
    """
    out: Dict[str, Any] = {
        "ok": False,
        "exit_code": 4,
        "status": None,
        "error": None,
        "written_file": None,
        "tool_count": 0,
        "case_count": 0,
        "warnings": []
    }

    try:
        tools_csv = Path(mcp_tools_csv_path)
        cases_csv = Path(mcp_cases_csv_path)
        out_p = Path(out_path)

        if out_path:
            # Permit callers to pass a directory (e.g. "generated/stub/" or ".")
            # and transparently create the default stub config file within it.
            if (
                out_p.is_dir()
                or str(out_path).endswith(("/", "\\"))
                or out_p.suffix == ""
            ):
                out_p = out_p / DEFAULT_STUB_CONFIG_FILENAME
        else:
            out_p = Path(DEFAULT_STUB_CONFIG_FILENAME)

        out_p.parent.mkdir(parents=True, exist_ok=True)

        if not tools_csv.exists():
            out["error"] = f"tools CSV not found: {tools_csv}"
            return out
        if not cases_csv.exists():
            out["warnings"].append(f"cases CSV not found: {cases_csv} (continuing with zero cases)")

        # Helpers (inlined)
        def parse_json(cell: str, default: Any) -> Any:
            cell = (cell or "").strip()
            if not cell:
                return default
            try:
                return json.loads(cell)
            except Exception:
                return default

        def parse_int(cell: str, default: int = 0) -> int:
            raw = (cell or "").strip()
            try:
                return int(raw)
            except Exception:
                return default

        # Load tools
        servers: Dict[str, Any] = {}
        tool_aliases: Dict[str, Dict[str, str]] = {}
        warned_tools: set[tuple[str, str]] = set()
        with tools_csv.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                server_id = (row.get("serverId") or "").strip()
                tool_name_raw = (row.get("toolName") or "").strip()
                if not server_id or not tool_name_raw:
                    out["warnings"].append(f"Skipping invalid tool row (serverId/toolName missing): {row}")
                    continue

                tool_name = _sanitize_tool_name(tool_name_raw)
                if tool_name != tool_name_raw and (server_id, tool_name_raw) not in warned_tools:
                    out["warnings"].append(
                        f"Sanitized tool name '{tool_name_raw}' -> '{tool_name}' for server '{server_id}'."
                    )
                    warned_tools.add((server_id, tool_name_raw))

                server_entry = servers.setdefault(server_id, {"tools": {}})
                if tool_name in server_entry["tools"]:
                    out["error"] = (
                        f"Sanitized tool name collision for server '{server_id}': '{tool_name_raw}' "
                        f"conflicts with existing tool key '{tool_name}'."
                    )
                    return out

                entry = {
                    "version": (row.get("version") or "").strip(),
                    "description": (row.get("description") or "").strip(),
                    "paramsSchema": parse_json(row.get("paramsSchema.json"), {"type": "object", "properties": {}}),
                    "resultSchema": parse_json(row.get("resultSchema.json"), {}),
                    "defaultResponse": parse_json(row.get("defaultResponse.json"), {}),
                    "rateLimit": {"rps": parse_int(row.get("rateLimit.rps"), 0)},
                    "latencyMs": {"default": parse_int(row.get("latencyMs.default"), 0)},
                    "cases": [],
                    "meta": {"originalToolName": tool_name_raw},
                }
                server_entry["tools"][tool_name] = entry
                alias_map = tool_aliases.setdefault(server_id, {})
                alias_map[tool_name_raw] = tool_name
                alias_map[tool_name] = tool_name

        # Load cases (optional)
        case_count = 0
        if cases_csv.exists():
            with cases_csv.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    server_id = (row.get("serverId") or "").strip()
                    tool_name_raw = (row.get("toolName") or "").strip()
                    if not server_id or not tool_name_raw:
                        out["warnings"].append(f"Skipping invalid case row (serverId/toolName missing): {row}")
                        continue

                    alias_map = tool_aliases.get(server_id, {})
                    tool_name = alias_map.get(tool_name_raw)
                    if tool_name is None:
                        sanitized_guess = _sanitize_tool_name(tool_name_raw)
                        tool_name = alias_map.get(sanitized_guess)
                    if tool_name is None or tool_name not in servers.get(server_id, {}).get("tools", {}):
                        out["warnings"].append(
                            f"Case row references unknown tool {server_id}:{tool_name_raw}; skipping."
                        )
                        continue

                    # Build case record
                    try:
                        latency_override_raw = (row.get("latencyMs.override") or "").strip()
                        latency_override = int(latency_override_raw) if latency_override_raw.isdigit() else None
                    except Exception:
                        latency_override = None

                    weight_raw = (row.get("weight") or "").strip()
                    try:
                        weight = float(weight_raw) if weight_raw not in ("", None) else None
                    except Exception:
                        weight = None

                    case_obj = {
                        "caseId": (row.get("caseId") or "").strip(),
                        "match": {
                            "strategy": (row.get("match.strategy") or "").strip(),
                            "expr": (row.get("match.expr") or "").strip(),
                            "value": (row.get("match.value") or "").strip()
                        },
                        "response": parse_json(row.get("response.json"), {}),
                        "latencyMsOverride": latency_override,
                        "errorMode": ((row.get("errorMode") or "").strip() or None),
                        "weight": weight
                    }
                    servers[server_id]["tools"][tool_name]["cases"].append(case_obj)
                    case_count += 1

        config = {"servers": servers}
        # Write atomically so the running stub server never reads a partial file.
        tmp_path = out_p.with_suffix(out_p.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(out_p)

        out["written_file"] = str(out_p)
        out["tool_count"] = sum(len(srv["tools"]) for srv in servers.values())
        out["case_count"] = case_count
        out["ok"] = True
        out["exit_code"] = 0
        out["status"] = f"Wrote stub config for {out['tool_count']} tool(s) and {out['case_count']} case(s)."
        return out

    except Exception as e:
        out["error"] = f"{e.__class__.__name__}: {e}"
        return out
