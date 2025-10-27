import os
import json
from typing import Any, Dict, List

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")
MAX_TEXT_CONTENT_CHUNK_SIZE = int(os.getenv("SKILL_MAX_TEXT_CHARS", "4900"))

REGISTRY_PATH = os.getenv("SKILL_REGISTRY_PATH", "skills_src/registry.json")

def load_skill_with_resolver(skill_json: str, agent_id: str) -> Dict[str, Any]:
    """
    Load a skill into a Letta agent with local MCP resolver.

    Inputs:
      skill_json: JSON string of a Skill Manifest v2.0.0.
      agent_id:   Target Letta agent id.

    Behavior:
      - Validates basic JSON shape (best-effort).
      - Attaches directives (as a block).
      - Resolves and attaches tools:
          * If requiredTools[].definition.type == "registered": attach by platformToolId.
          * If type == "mcp_server": read skills_src/registry.json to map logical serverId to a concrete endpoint.
            Registry shape:
              {
                "servers": {
                  "stub-tools": { "transport": "ws", "endpoint": "ws://stub-mcp:8765" },
                  "local-stdio": { "transport": "stdio", "command": "python", "args": ["stub_mcp_server.py"] }
                }
              }
            - For "ws": registers/attaches an MCP client pointing to endpoint.
            - For "stdio": registers/attaches an MCP client spawning command+args.
          * Duplicate attachments are skipped.
      - Attaches text data sources, chunked to MAX_TEXT_CONTENT_CHUNK_SIZE.
      - Records loaded skill resources into a per-agent state block (STATE_BLOCK_LABEL).

    Returns:
      {
        "ok": bool,
        "exit_code": int,        # 0 ok, 4 error
        "status": str|None,
        "error": str|None,
        "added": {
          "memory_block_ids": [str],
          "tool_ids": [str],
          "data_block_ids": [str]
        },
        "warnings": [str]
      }
    """
    out: Dict[str, Any] = {"ok": False, "exit_code": 4, "status": None, "error": None,
                           "added": {"memory_block_ids": [], "tool_ids": [], "data_block_ids": []},
                           "warnings": []}

    try:
        inst = json.loads(skill_json)
    except Exception as ex:
        out["error"] = f"JSONDecodeError: {ex}"
        return out

    try:
        from letta_client import Letta  # type: ignore
    except Exception as ex:
        out["error"] = f"Letta SDK import error: {ex}"
        return out

    # Load registry
    registry: Dict[str, Any] = {"servers": {}}
    try:
        if os.path.exists(REGISTRY_PATH):
            with open(REGISTRY_PATH, "r", encoding="utf-8") as rf:
                registry = json.load(rf)
        else:
            out["warnings"].append(f"Registry not found at {REGISTRY_PATH}; mcp_server tools may fail to resolve.")
    except Exception as ex:
        out["warnings"].append(f"Registry load failed: {ex}")

    def resolve_mcp(server_id: str) -> Dict[str, Any]:
        rec = (registry.get("servers") or {}).get(server_id) or {}
        # normalize
        transport = (rec.get("transport") or "").lower()
        if transport not in ("ws", "stdio"):
            return {}
        if transport == "ws":
            return {"mode": "ws", "endpoint": rec.get("endpoint")}
        return {"mode": "stdio", "command": rec.get("command"), "args": rec.get("args") or []}

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        _ = client.agents.retrieve(agent_id)
    except Exception as ex:
        out["error"] = f"Agent retrieval error: {ex}"
        return out

    manifest_id = inst.get("manifestId")
    skill_name = inst.get("skillName")
    skill_version = inst.get("skillVersion")

    # 1) Directives -> block
    directives = inst.get("skillDirectives") or ""
    if directives:
        label = f"skill_directives_{skill_name}_{manifest_id}"
        try:
            blk = client.blocks.create(label=label, value=directives)
            blk_id = getattr(blk, 'id', None)
            client.agents.blocks.attach(agent_id=agent_id, block_id=blk_id)
            out["added"]["memory_block_ids"].append(blk_id)
        except Exception as ex:
            out["error"] = f"Failed to attach directives block: {ex}"
            return out

    # 2) Tools
    try:
        attached = client.agents.tools.list(agent_id=agent_id)
        attached_ids = {getattr(t, 'id', None) or getattr(t, 'tool_id', None) for t in attached}
    except Exception:
        attached_ids = set()

    for tr in (inst.get("requiredTools") or []):
        tname = (tr.get("toolName") or "").strip()
        defi = tr.get("definition") or {}
        ttype = (defi.get("type") or "").strip()

        try:
            if ttype == "registered":
                plat_id = defi.get("platformToolId")
                if not plat_id:
                    raise ValueError("registered tool requires platformToolId")
                tool_obj = client.tools.retrieve(tool_id=plat_id)
                tid = getattr(tool_obj, 'id', None)
                if tid and tid not in attached_ids:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tid)
                    out["added"]["tool_ids"].append(tid)
                    attached_ids.add(tid)

            elif ttype == "mcp_server":
                server_id = (defi.get("serverId") or "").strip()
                if not server_id:
                    out["warnings"].append(f"mcp_server for '{tname}' missing serverId; skipped")
                    continue
                r = resolve_mcp(server_id)
                if not r:
                    out["warnings"].append(f"mcp_server '{server_id}' could not be resolved; skipped")
                    continue

                # Register (or reuse) an MCP connector at the agent level; API names vary by SDK version.
                # We try two shapes: tools.create_mcp_ws / tools.create_mcp_stdio
                if r["mode"] == "ws":
                    endpoint = r.get("endpoint")
                    if not endpoint:
                        out["warnings"].append(f"mcp_server '{server_id}' missing ws endpoint; skipped")
                        continue
                    # Example API names; adapt to your SDK:
                    # tool = client.tools.create_mcp_ws(name=tname, endpoint=endpoint)
                    tool = client.tools.create(name=f"mcp:{server_id}:{tname}",
                                               description=f"MCP WS {server_id}:{tname}",
                                               source_type="mcp_server",
                                               metadata_={"transport": "ws", "endpoint": endpoint, "serverId": server_id, "toolName": tname})
                else:
                    cmd = r.get("command")
                    args = r.get("args") or []
                    if not cmd:
                        out["warnings"].append(f"mcp_server '{server_id}' missing stdio command; skipped")
                        continue
                    tool = client.tools.create(name=f"mcp:{server_id}:{tname}",
                                               description=f"MCP stdio {server_id}:{tname}",
                                               source_type="mcp_server",
                                               metadata_={"transport": "stdio", "command": cmd, "args": args, "serverId": server_id, "toolName": tname})

                tid = getattr(tool, 'id', None)
                if tid and tid not in attached_ids:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tid)
                    out["added"]["tool_ids"].append(tid)
                    attached_ids.add(tid)

            else:
                out["warnings"].append(f"Unknown tool definition type '{ttype}' for '{tname}'")
        except Exception as ex:
            out["error"] = f"Failed processing tool '{tname}': {ex}"
            return out

    # 3) Data sources (text only)
    for ds in (inst.get("requiredDataSources") or []):
        cid = (ds.get("dataSourceId") or "").strip()
        content = ds.get("content") or {}
        if content.get("type") == "text_content":
            text = content.get("text") or ""
            if not text:
                continue
            chunks = [text[i:i+MAX_TEXT_CONTENT_CHUNK_SIZE] for i in range(0, len(text), MAX_TEXT_CONTENT_CHUNK_SIZE)]
            base_label = f"skill_ds_{skill_name}_{cid}"
            for idx, chunk in enumerate(chunks, start=1):
                label = base_label if len(chunks) == 1 else f"{base_label}_chunk_{idx}_of_{len(chunks)}"
                try:
                    b = client.blocks.create(label=label, value=chunk)
                    bid = getattr(b, 'id', None)
                    client.agents.blocks.attach(agent_id=agent_id, block_id=bid)
                    out["added"]["data_block_ids"].append(bid)
                except Exception as ex:
                    out["error"] = f"Failed to attach data source '{cid}' chunk {idx}: {ex}"
                    return out
        else:
            out["warnings"].append(f"Unsupported data source type for {cid}; only text_content is handled")

    # 4) Update per-agent skill state
    try:
        state = {}
        state_block_id = None
        blocks = client.agents.blocks.list(agent_id=agent_id)
        for b in blocks:
            if getattr(b, 'label', '') == STATE_BLOCK_LABEL:
                state_block_id = getattr(b, 'block_id', None) or getattr(b, 'id', None)
                if state_block_id:
                    full = client.blocks.retrieve(block_id=state_block_id)
                    val = getattr(full, 'value', '{}')
                    state = json.loads(val) if isinstance(val, str) else (val or {})
                break
        if manifest_id in state:
            raise ValueError(f"Skill '{manifest_id}' already loaded on agent '{agent_id}'.")
        state[manifest_id] = {
            "skillName": skill_name,
            "skillVersion": skill_version,
            "memoryBlockIds": out["added"]["memory_block_ids"],
            "toolIds": out["added"]["tool_ids"],
            "dataSourceBlockIds": out["added"]["data_block_ids"]
        }
        new_value = json.dumps(state, indent=2)
        if state_block_id:
            client.blocks.modify(block_id=state_block_id, value=new_value)
        else:
            sb = client.blocks.create(label=STATE_BLOCK_LABEL, value=new_value)
            sbid = getattr(sb, 'id', None)
            client.agents.blocks.attach(agent_id=agent_id, block_id=sbid)
    except Exception as ex:
        out["error"] = f"State tracking error: {ex}"
        return out

    out["ok"] = True
    out["exit_code"] = 0
    out["status"] = f"Loaded skill '{skill_name}' v{skill_version} (manifest {manifest_id})"
    return out
