import os
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

def csv_to_stub_config(mcp_tools_csv_path: str = "skills_src/mcp_tools.csv",
                       mcp_cases_csv_path: str = "skills_src/mcp_cases.csv",
                       out_path: str = "generated/stub/stub_config.json") -> Dict[str, Any]:
    """
    Generate a deterministic stub MCP server configuration from local CSV files.

    Inputs:
      1) mcp_tools_csv_path (default: skills_src/mcp_tools.csv)
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

      2) mcp_cases_csv_path (default: skills_src/mcp_cases.csv)
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

        # Load tools
        servers: Dict[str, Any] = {}
        tool_rows: List[Dict[str, Any]] = []
        with tools_csv.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                server_id = (row.get("serverId") or "").strip()
                tool_name = (row.get("toolName") or "").strip()
                if not server_id or not tool_name:
                    out["warnings"].append(f"Skipping invalid tool row (serverId/toolName missing): {row}")
                    continue

                entry = {
                    "version": (row.get("version") or "").strip(),
                    "description": (row.get("description") or "").strip(),
                    "paramsSchema": parse_json(row.get("paramsSchema.json"), {"type": "object", "properties": {}}),
                    "resultSchema": parse_json(row.get("resultSchema.json"), {}),
                    "defaultResponse": parse_json(row.get("defaultResponse.json"), {}),
                    "rateLimit": {"rps": int((row.get("rateLimit.rps") or "0").strip() or "0")},
                    "latencyMs": {"default": int((row.get("latencyMs.default") or "0").strip() or "0")},
                    "cases": []
                }
                servers.setdefault(server_id, {"tools": {}})["tools"][tool_name] = entry
                tool_rows.append({"serverId": server_id, "toolName": tool_name})

        # Load cases (optional)
        case_count = 0
        if cases_csv.exists():
            with cases_csv.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    server_id = (row.get("serverId") or "").strip()
                    tool_name = (row.get("toolName") or "").strip()
                    if not server_id or not tool_name:
                        out["warnings"].append(f"Skipping invalid case row (serverId/toolName missing): {row}")
                        continue

                    if server_id not in servers or tool_name not in servers[server_id]["tools"]:
                        out["warnings"].append(
                            f"Case row references unknown tool {server_id}:{tool_name}; skipping."
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
        with out_p.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

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
