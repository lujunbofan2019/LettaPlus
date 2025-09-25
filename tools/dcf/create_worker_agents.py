import os
import json
import uuid
from pathlib import Path

def create_worker_agents(workflow_json, imports_base_dir=None, agent_name_prefix=None, default_tags_json=None):
    """
    Create one worker agent per ASL Task state using Letta .af v2 templates.

    Resolution order for agent templates:
      1) Embedded .af v2 entities in workflow JSON:  workflow.af_v2_entities.agents[*]
         - Matched by AgentBinding.agent_ref.id or AgentBinding.agent_ref.name
      2) External .af bundles listed under workflow.af_imports[*] (if present)
         - Each bundle is a JSON file containing .af v2 multi-entity blocks; agents indexed by id/name
      3) Inline legacy .af v1:  workflow.agents[*].agent_config  (as a last resort)

    Notes:
    - Only top-level ASL Task states are materialized as workers.
    - This function does not perform skill loading; workers are expected to load skills at runtime.
    - Tool attachments that come with the template are passed through to Letta when available. This tool
      does not attempt to register tools-from-source to avoid duplicates; prefer pre-registered tools.

    Args:
      workflow_json (str):
        The workflow document as a JSON string. Should contain `asl.StartAt + asl.States`.
      imports_base_dir (str, optional):
        Base directory used to resolve relative paths found in `workflow.af_imports[*]`.
        If omitted, relative paths are resolved as-is (current working directory of the Letta server).
      agent_name_prefix (str, optional):
        A prefix used when creating agent names, e.g. "wf-{workflow_id}-". If omitted, the function uses
        "wf-{workflow_id}-" automatically.
      default_tags_json (str, optional):
        JSON string of a list of extra tags to add to each created agent (e.g., ["worker", "choreo"]).
        The function also tags each agent with "wf:{workflow_id}" and "state:{StateName}".

    Returns:
      dict:
        {
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
    workflow_id = None

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
    if default_tags_json:
        try:
            tmp = json.loads(default_tags_json)
            if isinstance(tmp, list):
                extra_tags = [str(x) for x in tmp]
        except Exception:
            warnings.append("Ignored invalid default_tags_json (must be a JSON array of strings).")

    # --- Index agent templates (embedded and imported) ---
    # Index by both id and name for fast lookup.
    embedded_index_by_id = {}
    embedded_index_by_name = {}

    af_v2_entities = wf.get("af_v2_entities") or {}
    for agent_ent in af_v2_entities.get("agents", []) or []:
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
    # Optional: workflow.af_imports => array of JSON paths to .af v2 bundles
    af_imports = wf.get("af_imports") or []
    base_dir = Path(imports_base_dir) if imports_base_dir else None

    def _load_json_from_path(p_str):
        # Support plain paths and file:// URIs
        try:
            if p_str.startswith("file://"):
                p = Path(p_str[7:])
            else:
                p = Path(p_str)
            if base_dir and not p.is_absolute():
                p = base_dir / p
            with open(str(p), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    for entry in af_imports:
        if not isinstance(entry, str):
            continue
        data = _load_json_from_path(entry)
        if not isinstance(data, dict):
            warnings.append("Skipping af_import '%s' (not loadable JSON)." % entry)
            continue

        # Data may be a multi-entity .af v2 bundle or a single agent.
        agents_list = []
        if isinstance(data.get("agents"), list):
            agents_list = data.get("agents")
        elif data.get("id") and data.get("name"):  # single agent entity
            agents_list = [data]
        else:
            # Some bundles may nest agents deeper; we keep it simple here.
            pass

        for agent_ent in agents_list or []:
            if not isinstance(agent_ent, dict):
                continue
            a_id = agent_ent.get("id")
            a_name = agent_ent.get("name")
            if isinstance(a_id, str):
                imported_index_by_id[a_id] = agent_ent
            if isinstance(a_name, str):
                imported_index_by_name[a_name] = agent_ent

    # --- Helper: resolve an AgentBinding to an .af v2 agent entity or .af v1 inline config ---
    def _resolve_agent_for_state(state_name, state_def):
        # 1) Try AgentBinding.agent_ref (v2 reference)
        agent_binding = state_def.get("AgentBinding") or {}
        ref = agent_binding.get("agent_ref") or {}

        ref_id = ref.get("id") if isinstance(ref, dict) else None
        ref_name = ref.get("name") if isinstance(ref, dict) else None

        if isinstance(ref_id, str):
            # Prefer embedded, then imported
            if ref_id in embedded_index_by_id:
                return ("v2", embedded_index_by_id[ref_id])
            if ref_id in imported_index_by_id:
                return ("v2", imported_index_by_id[ref_id])
            return ("error", "AgentBinding.agent_ref.id '%s' not found in embedded or imported .af v2 entities." % ref_id)

        if isinstance(ref_name, str):
            if ref_name in embedded_index_by_name:
                return ("v2", embedded_index_by_name[ref_name])
            if ref_name in imported_index_by_name:
                return ("v2", imported_index_by_name[ref_name])
            return ("error", "AgentBinding.agent_ref.name '%s' not found in embedded or imported .af v2 entities." % ref_name)

        # 2) Fallback: inline .af v1 in workflow.agents[*] where agent_name matches
        inline_agents = wf.get("agents") or []
        # match state_def.AgentBinding.agent_ref.name to agents[*].agent_name if present, else use state_name
        target_name = ref_name or state_def.get("agent_name") or state_name
        for a in inline_agents:
            if isinstance(a, dict) and a.get("agent_name") == target_name and isinstance(a.get("agent_config"), dict):
                return ("v1", a.get("agent_config"))

        return ("error", "No agent template found for state '%s'. Provide AgentBinding.agent_ref (v2) or an inline .af v1 agent." % state_name)

    # --- Create agents via Letta API ---
    base_prefix = agent_name_prefix or ("wf-%s-" % workflow_id)
    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to initialize Letta client: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "agents_map": {},
            "created": [],
            "warnings": warnings
        }

    for s_name in task_states:
        s_def = states_obj.get(s_name, {}) or {}
        kind, template_or_error = _resolve_agent_for_state(s_name, s_def)
        if kind == "error":
            return {
                "status": None,
                "error": template_or_error,
                "workflow_id": workflow_id,
                "agents_map": agents_map,
                "created": created,
                "warnings": warnings
            }

        # Build a creation payload from v2 or v1 template
        creation_payload = {}
        if kind == "v2":
            v2 = template_or_error
            # Minimal pass-through fields commonly accepted by Letta agent creation
            for k in ["name", "description", "system", "agent_type", "tags", "llm_config",
                      "embedding_config", "message_buffer_autoclear", "messages",
                      "core_memory", "tool_exec_environment_variables", "tool_rules",
                      "tool_ids", "tools"]:
                if k in v2:
                    creation_payload[k] = v2[k]
        else:  # v1 inline
            v1 = template_or_error
            for k in ["name", "description", "system", "agent_type", "tags", "llm_config",
                      "embedding_config", "message_buffer_autoclear", "messages",
                      "core_memory", "tool_exec_environment_variables", "tool_rules",
                      "tools"]:
                if k in v1:
                    creation_payload[k] = v1[k]

        # Ensure a unique, informative runtime name
        base_name = creation_payload.get("name") or s_name
        runtime_name = "%s%s" % (base_prefix, base_name)
        # Avoid extremely long names; append short UUID suffix to reduce collision risk
        runtime_name = (runtime_name[:48] + "-" + str(uuid.uuid4())[:8]) if len(runtime_name) > 56 else runtime_name

        # Tags: workflow + state + any extras
        tags = creation_payload.get("tags") or []
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
            # Some SDKs want name as part of payload, not a kwarg; fallback
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
