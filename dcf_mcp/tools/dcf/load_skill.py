from typing import Any, Dict
import os
import json

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")
MAX_TEXT_CONTENT_CHUNK_SIZE = int(os.getenv("SKILL_MAX_TEXT_CHARS", "4900"))

ALLOW_PYTHON_SOURCE = os.getenv("ALLOW_PYTHON_SOURCE_SKILLS", "0") == "1"
ALLOW_MCP = os.getenv("ALLOW_MCP_SKILLS", "0") == "1"

def load_skill(skill_json: str, agent_id: str) -> Dict[str, Any]:
    """Load a skill into a Letta agent: attach directives, tools, and data sources.

    This function assumes:
      - the manifest is already validated against `skill-manifest-v2.0.0.json`.
      - `python_source` and `mcp_server` tool definitions are feature-gated by environment flags ALLOW_PYTHON_SOURCE_SKILLS / ALLOW_MCP_SKILLS.
      - Per-agent bookkeeping is stored in a block labeled by SKILL_STATE_BLOCK_LABEL (default: "dcf_active_skills").

    Args:
        skill_json (str):
            JSON string containing a **validated** skill manifest (schema v2.0.0).
        agent_id (str):
            Target Letta agent ID that will receive the skill.

    Returns:
        dict: Result object with status and details:
            {
              "ok": bool,
              "exit_code": int,         # 0 on success, 4 on error
              "status": str or None,
              "error": str or None,
              "added": {
                "memory_block_ids": list[str],
                "tool_ids": list[str],
                "data_block_ids": list[str]
              },
              "warnings": list[str]
            }
    """
    out = {
        "ok": False,
        "exit_code": 4,
        "status": None,
        "error": None,
        "added": {"memory_block_ids": [], "tool_ids": [], "data_block_ids": []},
        "warnings": []
    }

    # Basic runtime type checks for clearer errors in tool-call contexts
    if not isinstance(skill_json, str):
        out["error"] = "TypeError: skill_json must be a JSON string"
        return out
    if not isinstance(agent_id, str):
        out["error"] = "TypeError: agent_id must be a string"
        return out

    try:
        inst = json.loads(skill_json)
    except Exception as ex:
        out["error"] = "JSONDecodeError: %s" % ex
        return out

    # Late import so this module stays importable without the SDK for validation-only contexts
    try:
        from letta_client import Letta
    except Exception as ex:
        out["error"] = "Letta SDK import error: %s" % ex
        return out

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        # Ensure agent exists
        _ = client.agents.retrieve(agent_id)
    except Exception as ex:
        out["error"] = "Agent retrieval error: %s" % ex
        return out

    manifest_id = inst.get("manifestId")
    skill_name = inst.get("skillName")
    skill_version = inst.get("skillVersion")

    # --- 1) Attach directives as a block ---
    directives = inst.get("skillDirectives") or ""
    if directives:
        label = f"skill_directives_{skill_name}_{manifest_id}"
        try:
            blk = client.blocks.create(label=label, value=directives)
            blk_id = getattr(blk, 'id', None)
            if not blk_id:
                raise RuntimeError("No block id returned")
            client.agents.blocks.attach(agent_id=agent_id, block_id=blk_id)
            out["added"]["memory_block_ids"].append(blk_id)
        except Exception as ex:
            out["error"] = "Failed to attach directives block: %s" % ex
            return out

    # --- 2) Attach tools ---
    # Ensure we have a set of currently attached tool ids to avoid duplicates
    try:
        attached = client.agents.tools.list(agent_id=agent_id)
        attached_ids = {getattr(t, 'id', None) or getattr(t, 'tool_id', None) for t in attached}
    except Exception:
        attached_ids = set()

    for tr in (inst.get("requiredTools") or []):
        tname = tr.get("toolName")
        defi = tr.get("definition") or {}
        ttype = defi.get("type")

        try:
            if ttype == "registered":
                plat_id = defi.get("platformToolId")
                if not plat_id:
                    raise ValueError("registered tool requires platformToolId")
                tool_obj = client.tools.retrieve(tool_id=plat_id)
                tid = getattr(tool_obj, 'id', None)
                if not tid:
                    raise RuntimeError("Tool retrieval returned no id")
                if tid not in attached_ids:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tid)
                    out["added"]["tool_ids"].append(tid)
                    attached_ids.add(tid)

            elif ttype == "python_source":
                if not ALLOW_PYTHON_SOURCE:
                    out["warnings"].append(f"python_source for '{tname}' skipped (feature disabled)")
                else:
                    source = defi.get("sourceCode") or ""
                    if not source:
                        raise ValueError("python_source requires sourceCode")
                    # Implement environment-specific registration here:
                    # e.g., reg = client.tools.create_from_source(name=tname, source_code=source)
                    raise NotImplementedError("Tool registration from python_source is environment-specific")

            elif ttype == "mcp_server":
                if not ALLOW_MCP:
                    out["warnings"].append(f"mcp_server for '{tname}' skipped (feature disabled)")
                else:
                    # Implement MCP server + tool registration for your Letta version:
                    raise NotImplementedError("MCP tool registration is environment-specific")

            else:
                out["warnings"].append(f"Unknown tool definition type '{ttype}' for '{tname}'")
        except Exception as ex:
            out["error"] = f"Failed processing tool '{tname}': {ex}"
            return out

    # --- 3) Attach data sources (text_content only) ---
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
                    if not bid:
                        raise RuntimeError("No block id returned for data source chunk")
                    client.agents.blocks.attach(agent_id=agent_id, block_id=bid)
                    out["added"]["data_block_ids"].append(bid)
                except Exception as ex:
                    out["error"] = f"Failed to attach data source '{cid}' chunk {idx}: {ex}"
                    return out
        else:
            out["warnings"].append(f"Unsupported data source type for {cid}; only text_content is handled")

    # --- 4) Update per-agent skill state block ---
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
                    try:
                        state = json.loads(val) if isinstance(val, str) else (val or {})
                    except Exception:
                        state = {}
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
            if not sbid:
                raise RuntimeError("Failed to create skill state block")
            client.agents.blocks.attach(agent_id=agent_id, block_id=sbid)
    except Exception as ex:
        out["error"] = f"State tracking error: {ex}"
        return out

    out["ok"] = True
    out["exit_code"] = 0
    out["status"] = f"Loaded skill '{skill_name}' v{skill_version} (manifest {manifest_id})"
    return out
