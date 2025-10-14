# file: csv_to_manifests.py
import csv
import json
import os
from pathlib import Path

SKILLS_CSV = "skills_src/skills.csv"
REFS_CSV = "skills_src/skill_tool_refs.csv"
OUT_DIR = Path("generated/skills")
CATALOG_PATH = Path("generated/catalogs/skills_catalog.json")

def _parse_json_cell(cell):
    cell = (cell or "").strip()
    if not cell:
        return None
    try:
        return json.loads(cell)
    except Exception:
        # allow simple comma-separated tags shorthand elsewhere; here we expect JSON only
        return None

def _parse_tags_csv(cell):
    # tags column is comma-separated (not JSON)
    raw = (cell or "").strip()
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]

def ensure_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_skill_rows():
    rows = []
    with open(SKILLS_CSV, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows

def load_refs():
    refs = {}
    with open(REFS_CSV, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            mid = row.get("manifestId", "").strip()
            if not mid:
                continue
            refs.setdefault(mid, []).append({
                "serverId": (row.get("serverId") or "").strip(),
                "toolName": (row.get("toolName") or "").strip(),
                "required": (row.get("required") or "true").strip().lower() == "true",
                "notes": (row.get("notes") or "").strip()
            })
    return refs

def build_manifest(row, refs_for_manifest):
    manifest_id = (row.get("manifestId") or "").strip()
    name = (row.get("skillName") or "").strip()
    ver = (row.get("skillVersion") or "").strip()
    desc = (row.get("description") or "").strip()
    tags = _parse_tags_csv(row.get("tags"))
    egress = (row.get("permissions.egress") or "none").strip()
    secrets = _parse_json_cell(row.get("permissions.secrets")) or []
    directives = (row.get("skillDirectives") or "").strip()
    data_sources = _parse_json_cell(row.get("dataSources.json")) or []

    if not manifest_id or not name or not ver:
        raise ValueError(f"Missing required fields in skills.csv row (manifestId/skillName/skillVersion). Row={row}")

    # requiredTools from mapping
    required_tools = []
    for ref in refs_for_manifest or []:
        sid = ref["serverId"]
        tname = ref["toolName"]
        if not sid or not tname:
            continue
        required_tools.append({
            "toolName": tname,
            "definition": {
                "type": "mcp_server",
                "serverId": sid,
                "toolName": tname
            },
            "required": bool(ref["required"])
        })

    doc = {
        "manifestId": manifest_id,
        "skillPackageId": None,
        "skillName": name,
        "skillVersion": ver,
        "description": desc or None,
        "tags": tags,
        "permissions": {
            "egress": egress if egress in ("none", "intranet", "internet") else "none",
            "secrets": secrets
        },
        "skillDirectives": directives,
        "requiredTools": required_tools,
        "requiredDataSources": data_sources
    }
    return doc

def main():
    ensure_dirs()
    skill_rows = load_skill_rows()
    refs_index = load_refs()
    catalog = {"skills": []}

    for row in skill_rows:
        mid = (row.get("manifestId") or "").strip()
        refs = refs_index.get(mid, [])
        try:
            manifest = build_manifest(row, refs)
        except Exception as e:
            print(f"[ERROR] {mid or '<missing manifestId>'}: {e}")
            continue

        out_path = OUT_DIR / f"{manifest['manifestId']}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        catalog["skills"].append({
            "manifestId": manifest["manifestId"],
            "skillName": manifest["skillName"],
            "skillVersion": manifest["skillVersion"],
            "path": str(out_path)
        })
        print(f"[OK] wrote {out_path}")

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"[OK] wrote {CATALOG_PATH}")

if __name__ == "__main__":
    main()
