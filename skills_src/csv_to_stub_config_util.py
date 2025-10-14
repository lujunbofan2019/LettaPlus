# file: csv_to_stub_config.py
import csv
import json
from pathlib import Path

TOOLS_CSV = "skills_src/mcp_tools.csv"
CASES_CSV = "skills_src/mcp_cases.csv"
OUT_PATH = Path("generated/stub/stub_config.json")

def _parse_json(cell, default):
    cell = (cell or "").strip()
    if not cell:
        return default
    try:
        return json.loads(cell)
    except Exception:
        return default

def load_tools():
    tools = []
    with open(TOOLS_CSV, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            tools.append({
                "serverId": (row.get("serverId") or "").strip(),
                "toolName": (row.get("toolName") or "").strip(),
                "version": (row.get("version") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "paramsSchema": _parse_json(row.get("paramsSchema.json"), {"type":"object","properties":{}}),
                "resultSchema": _parse_json(row.get("resultSchema.json"), {}),
                "defaultResponse": _parse_json(row.get("defaultResponse.json"), {}),
                "rateLimit": {
                    "rps": int(row.get("rateLimit.rps") or 0)
                },
                "latencyMs": {
                    "default": int(row.get("latencyMs.default") or 0)
                }
            })
    return tools

def load_cases():
    cases = []
    with open(CASES_CSV, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cases.append({
                "serverId": (row.get("serverId") or "").strip(),
                "toolName": (row.get("toolName") or "").strip(),
                "caseId": (row.get("caseId") or "").strip(),
                "match": {
                    "strategy": (row.get("match.strategy") or "").strip(),
                    "expr": (row.get("match.expr") or "").strip(),
                    "value": (row.get("match.value") or "").strip()
                },
                "response": _parse_json(row.get("response.json"), {}),
                "latencyMsOverride": (int(row.get("latencyMs.override")) if (row.get("latencyMs.override") or "").strip().isdigit() else None),
                "errorMode": (row.get("errorMode") or "").strip() or None,
                "weight": (float(row.get("weight")) if (row.get("weight") or "").strip() not in ("", None) else None)
            })
    return cases

def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tools = load_tools()
    cases = load_cases()

    # Group cases under each tool
    case_map = {}
    for c in cases:
        key = (c["serverId"], c["toolName"])
        case_map.setdefault(key, []).append(c)

    config = {"servers": {}}
    for t in tools:
        sid = t["serverId"]
        tname = t["toolName"]
        if not sid or not tname:
            print(f"[WARN] Skipping invalid tool row: {t}")
            continue

        srv = config["servers"].setdefault(sid, {"tools": {}})
        tool_entry = {
            "version": t["version"],
            "description": t["description"],
            "paramsSchema": t["paramsSchema"],
            "resultSchema": t["resultSchema"],
            "defaultResponse": t["defaultResponse"],
            "rateLimit": t["rateLimit"],
            "latencyMs": t["latencyMs"],
            "cases": case_map.get((sid, tname), [])
        }
        srv["tools"][tname] = tool_entry

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"[OK] wrote {OUT_PATH}")

if __name__ == "__main__":
    main()
