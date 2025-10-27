import os
import json
import uuid
from pathlib import Path

def create_worker_agents(workflow_json: str,
                         imports_base_dir: str = None,
                         agent_name_prefix: str = None,
                         default_tags_json: str = None) -> dict:
    """Create one worker agent per ASL Task state using Letta .af v2 templates.

    Resolution order for agent templates:
      1) Embedded .af v2 entities in workflow JSON:  workflow.af_v2_entities.agents[*]
         - Matched by AgentBinding.agent_ref.id or AgentBinding.agent_ref.name
      2) External .af bundles listed under workflow.af_imports[*] (if present)
         - Each bundle is a JSON file containing .af v2 multi-entity blocks; agents indexed by id/name
      3) Inline legacy .af v1:  workflow.agents[*].agent_config  (as a last resort)

    Notes:
      * Only top-level ASL Task states are materialized as workers.
      * This function does NOT load skills; workers will dynamically load skills at runtime.
      * To avoid duplicate platform tools when many workers share the same template, we:
          - Look up existing platform tools by name.
          - Replace template `tools` with `tool_ids` when matches are found.
          - Skip source-defined tools we cannot safely de-duplicate (add a warning).
        This means templates should prefer referencing pre-registered tools (by name / id).

    Args:
      workflow_json: The workflow document as a JSON string. Should contain `asl.StartAt` and `asl.States`.
      imports_base_dir: Base directory for resolving relative paths in `workflow.af_imports[*]`.
      agent_name_prefix: Prefix for created agent names, e.g. "wf-{workflow_id}-".
                         If omitted, defaults to "wf-{workflow_id}-".
      default_tags_json: JSON string array of extra tags (e.g., ["worker", "choreo"]).
                         Each agent also receives "wf:{workflow_id}" and "state:{StateName}".

    Returns:
      dict: {
        "status": str or None,
        "error": str or None,
        "workflow_id": str or None,
        "agents_map": dict,                 # { state_name: agent_id }
        "created": list,                    # [{ "state": ..., "agent_id": ..., "agent_name": ... }, ...]
        "warnings": list                    # non-fatal issues
      }
    """
    # --- Resolve Letta client lazily ---
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: letta_client not importable: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": None,
            "agents_map": {},
            "created": [],
            "warnings": ["Install/upgrade Letta Python client in the server image."]
        }

    warnings = []
    created = []
    agents_map = {}

    # --- Load workflow JSON ---
    try:
        wf = json.loads(workflow_json)
    except Exception as e:
        return {
            "status": None,
            "error": "Invalid workflow_json: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": None,
            "agents_map": {},
            "created": [],
            "warnings": []
        }

    workflow_id = wf.get("workflow_id")
    if not workflow_id:
        return {
            "status": None,
            "error": "workflow_json missing required 'workflow_id' (uuid).",
            "workflow_id": None,
            "agents_map": {},
            "created": [],
            "warnings": []
        }

    # --- Collect Task states from ASL ---
    asl = wf.get("asl") or {}
    states_obj = asl.get("States") or {}
    if not states_obj:
        return {
            "status": None,
            "error": "No ASL States found. Provide 'asl.StartAt' and 'asl.States'.",
            "workflow_id": workflow_id,
            "agents_map": {},
            "created": [],
            "warnings": []
        }

    task_states = []
    for s_name, s_def in states_obj.items():
        if isinstance(s_def, dict) and s_def.get("Type") == "Task":
            task_states.append(s_name)
    if not task_states:
        return {
            "status": None,
            "error": "No Task states found to materialize.",
            "workflow_id": workflow_id,
            "agents_map": {},
            "created": [],
            "warnings": []
        }

    # --- Optional default tags ---
    extra_tags = []
    if isinstance(default_tags_json, str) and default_tags_json.strip():
        try:
            tmp = json.loads(default_tags_json)
            if isinstance(tmp, list):
                extra_tags = [str(x) for x in tmp]
            else:
                warnings.append("Ignored default_tags_json: not a JSON array.")
        except Exception:
            warnings.append("Ignored invalid default_tags_json (must be a JSON array of strings).")

    # --- Index agent templates (embedded and imported) ---
    embedded_index_by_id = {}
    embedded_index_by_name = {}

    af_v2_entities = wf.get("af_v2_entities") or {}
    if isinstance(af_v2_entities.get("agents"), list):
        for agent_ent in af_v2_entities.get("agents") or []:
            if not isinstance(agent_ent, dict):
                continue
            a_id = agent_ent.get("id")
            a_name = agent_ent.get("name")
            if isinstance(a_id, str):
                embedded_index_by_id[a_id] = agent_ent
            if isinstance(a_name, str):
                embedded_index_by_name[a_name] = agent_ent

    imported_index_by_id = {}
    imported_index_by_name = {}
    af_imports = wf.get("af_imports") or []
    base_dir = Path(imports_base_dir).expanduser() if imports_base_dir else None

    for entry in af_imports:
        if not isinstance(entry, str):
            continue
        # Resolve path (supports file://)
        try:
            p_str = entry
            if p_str.startswith("file://"):
                p = Path(p_str[7:])
            else:
                p = Path(p_str)
            if base_dir and not p.is_absolute():
                p = (base_dir / p).resolve()
            else:
                p = p.expanduser().resolve()
            with open(str(p), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            warnings.append("Skipping af_import '%s' (load error: %s: %s)." % (entry, e.__class__.__name__, e))
            continue

        # Data may be a multi-entity .af v2 bundle or a single agent
        agents_list = []
        if isinstance(data, dict) and isinstance(data.get("agents"), list):
            agents_list = data.get("agents")
        elif isinstance(data, dict) and data.get("id") and data.get("name"):
            agents_list = [data]
        else:
            # Could be a different bundle shape; skip silently
            continue

        for agent_ent in agents_list or []:
            if not isinstance(agent_ent, dict):
                continue
            a_id = agent_ent.get("id")
            a_name = agent_ent.get("name")
            if isinstance(a_id, str):
                imported_index_by_id[a_id] = agent_ent
            if isinstance(a_name, str):
                imported_index_by_name[a_name] = agent_ent

    # --- Initialize Letta client ---
    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://letta:8283"))
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to initialize Letta client: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "agents_map": {},
            "created": [],
            "warnings": warnings
        }

    # Build global tool index by name -> id (to avoid duplicate creation when templates include `tools`)
    tools_by_name = {}
    try:
        platform_tools = client.tools.list()
        for t in platform_tools:
            nm = getattr(t, "name", None)
            tid = getattr(t, "id", None) or getattr(t, "tool_id", None)
            if nm and tid:
                tools_by_name[nm] = tid
    except Exception:
        # Non-fatal: if we can't list tools, we simply won't map template tools to ids
        pass

    # Default runtime agent name prefix
    base_prefix = agent_name_prefix or ("wf-%s-" % workflow_id)

    # --- For each Task state, resolve a template and create an agent ---
    for s_name in task_states:
        s_def = states_obj.get(s_name, {}) or {}

        # Resolve AgentBinding (v2) or fallback to inline v1
        agent_binding = s_def.get("AgentBinding") or {}
        ref = agent_binding.get("agent_ref") or {}
        ref_id = ref.get("id") if isinstance(ref, dict) else None
        ref_name = ref.get("name") if isinstance(ref, dict) else None

        template_kind = None  # "v2" | "v1"
        template_payload = None

        # 1) v2 by id/name (prefer embedded, then imported)
        if isinstance(ref_id, str):
            if ref_id in embedded_index_by_id:
                template_kind, template_payload = "v2", embedded_index_by_id[ref_id]
            elif ref_id in imported_index_by_id:
                template_kind, template_payload = "v2", imported_index_by_id[ref_id]
            else:
                return {
                    "status": None,
                    "error": "AgentBinding.agent_ref.id '%s' not found in embedded or imported .af v2 entities." % ref_id,
                    "workflow_id": workflow_id,
                    "agents_map": agents_map,
                    "created": created,
                    "warnings": warnings
                }
        elif isinstance(ref_name, str):
            if ref_name in embedded_index_by_name:
                template_kind, template_payload = "v2", embedded_index_by_name[ref_name]
            elif ref_name in imported_index_by_name:
                template_kind, template_payload = "v2", imported_index_by_name[ref_name]
            else:
                return {
                    "status": None,
                    "error": "AgentBinding.agent_ref.name '%s' not found in embedded or imported .af v2 entities." % ref_name,
                    "workflow_id": workflow_id,
                    "agents_map": agents_map,
                    "created": created,
                    "warnings": warnings
                }
        else:
            # 2) Fallback: inline .af v1 agent_config matched by name
            inline_agents = wf.get("agents") or []
            # Try AgentBinding's (missing) ref name, else state_def.agent_name, else state name
            target_name = (s_def.get("agent_name") if isinstance(s_def.get("agent_name"), str) else None) or s_name
            for a in inline_agents:
                if isinstance(a, dict) and a.get("agent_name") == target_name and isinstance(a.get("agent_config"), dict):
                    template_kind, template_payload = "v1", a.get("agent_config")
                    break
            if template_kind is None:
                return {
                    "status": None,
                    "error": "No agent template found for state '%s'. Provide AgentBinding.agent_ref (v2) or inline .af v1 agent." % s_name,
                    "workflow_id": workflow_id,
                    "agents_map": agents_map,
                    "created": created,
                    "warnings": warnings
                }

        # --- Build creation payload from v2/v1 template, de-duping tools ---
        creation_payload = {}
        template_obj = template_payload if isinstance(template_payload, dict) else {}

        # Common pass-through keys
        for k in ["name", "description", "system", "agent_type", "tags", "llm_config",
                  "embedding_config", "message_buffer_autoclear", "messages",
                  "core_memory", "tool_exec_environment_variables", "tool_rules",
                  "tool_ids", "tools"]:
            if k in template_obj:
                creation_payload[k] = template_obj[k]

        # De-duplicate tools: prefer attaching tool_ids resolved by tool name; avoid creating new ones from source
        resolved_tool_ids = []
        # If template already provides tool_ids, we keep them
        if isinstance(creation_payload.get("tool_ids"), list) and creation_payload["tool_ids"]:
            for tid in creation_payload["tool_ids"]:
                if isinstance(tid, str):
                    resolved_tool_ids.append(tid)
        # If template provides inline tools, try to map by name
        elif isinstance(creation_payload.get("tools"), list):
            for tool_spec in creation_payload["tools"]:
                if not isinstance(tool_spec, dict):
                    continue
                tname = tool_spec.get("name")
                # Map by name -> existing platform id
                if isinstance(tname, str) and tname in tools_by_name:
                    resolved_tool_ids.append(tools_by_name[tname])
                else:
                    # We intentionally DO NOT register source-defined tools here to avoid duplicates
                    # (workers should acquire tools via skills).
                    warnings.append("State '%s': tool '%s' not mapped to platform id; skipping to avoid duplicates." %
                                    (s_name, tname if isinstance(tname, str) else "<unnamed>"))

        # Replace with deduped ids if any; remove inline tools to avoid re-creation
        if resolved_tool_ids:
            creation_payload["tool_ids"] = list(dict.fromkeys(resolved_tool_ids))  # unique, preserve order
        creation_payload.pop("tools", None)

        # Ensure a unique, informative runtime name
        base_name = creation_payload.get("name") if isinstance(creation_payload.get("name"), str) else s_name
        runtime_name = "%s%s" % (agent_name_prefix or ("wf-%s-" % workflow_id), base_name)
        # Avoid extremely long names; append short UUID suffix to reduce collision risk
        runtime_name = (runtime_name[:48] + "-" + str(uuid.uuid4())[:8]) if len(runtime_name) > 56 else runtime_name

        # Tags: workflow + state + any extras (ensure strings)
        tags = creation_payload.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        tags = [t if isinstance(t, str) else str(t) for t in tags]
        tags.extend(["wf:%s" % workflow_id, "state:%s" % s_name, "role:worker"])
        for t in extra_tags:
            if t not in tags:
                tags.append(t)
        creation_payload["tags"] = tags

        # Create the agent
        try:
            agent_obj = client.agents.create(**creation_payload, name=runtime_name)
        except TypeError:
            # Some SDKs want name as part of payload, not a kwarg
            creation_payload["name"] = runtime_name
            agent_obj = client.agents.create(**creation_payload)
        except Exception as e:
            return {
                "status": None,
                "error": "Failed to create agent for state '%s': %s: %s" % (s_name, e.__class__.__name__, e),
                "workflow_id": workflow_id,
                "agents_map": agents_map,
                "created": created,
                "warnings": warnings
            }

        agent_id = getattr(agent_obj, "id", None) or getattr(agent_obj, "agent_id", None)
        agent_name = getattr(agent_obj, "name", runtime_name)
        if not agent_id:
            return {
                "status": None,
                "error": "Agent created for state '%s' but no ID returned by Letta." % s_name,
                "workflow_id": workflow_id,
                "agents_map": agents_map,
                "created": created,
                "warnings": warnings
            }

        agents_map[s_name] = agent_id
        created.append({"state": s_name, "agent_id": agent_id, "agent_name": agent_name})

    status = "Created %d worker agents for workflow '%s'." % (len(created), workflow_id)
    return {
        "status": status,
        "error": None,
        "workflow_id": workflow_id,
        "agents_map": agents_map,
        "created": created,
        "warnings": warnings
    }
