import os
import json
from datetime import datetime, timezone

def create_workflow_control_plane(workflow_json, redis_url=None, expiry_secs=None, agents_map_json=None):
    """
    Create (idempotently) the RedisJSON control-plane for a workflow (choreography style).

    This seeds the following JSON keys (one top-level JSON document per key):
      - cp:wf:{workflow_id}:meta
      - cp:wf:{workflow_id}:state:{state}

    The meta document aligns with `schemas/control-plane-meta-1.0.0.json`.
    Each state document aligns with `schemas/control-plane-state-1.0.0.json`.

    Redis requirements:
      - Redis server with RedisJSON module enabled.
      - redis-py with JSON command support (r.json().get / set).

    Args:
      workflow_json (str):
        JSON string of the workflow definition. Prefer the `asl` form with `StartAt` and `States`.
        If only `steps` exist, a linear DAG is inferred in the given order.
      redis_url (str, optional):
        Redis connection URL (e.g., "redis://localhost:6379/0"). If not provided, uses env `REDIS_URL`
        or the default "redis://localhost:6379/0".
      expiry_secs (int, optional):
        TTL to apply to seeded keys via EXPIRE. Omit or set <=0 for no TTL (recommended during execution).
      agents_map_json (str, optional):
        JSON string mapping state names to agent IDs. If provided and valid, stored into the meta document
        under `agents` for quick lookup by workers. E.g. { "Research": "agent_abc123", "Summarize": "agent_def456" }

    Returns:
      dict:
        {
          "status": str or None,
          "error": str or None,
          "created_keys": list,     # keys created in this call
          "existing_keys": list,    # keys detected as already present (left untouched)
          "meta_sample": dict       # meta document that was written or fetched
        }
    """

    # --- 0) Lazy import redis and check JSON support ---
    try:
        import redis  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: install the `redis` package. ImportError: %s" % e,
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    r_url = redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to connect to Redis at %s: %s: %s" % (r_url, e.__class__.__name__, e),
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "Redis connection does not expose RedisJSON (r.json()). Ensure RedisJSON module is enabled.",
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    # --- 1) Parse workflow JSON ---
    try:
        wf = json.loads(workflow_json)
    except Exception as e:
        return {
            "status": None,
            "error": "Invalid workflow_json: %s: %s" % (e.__class__.__name__, e),
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    workflow_id = wf.get("workflow_id")
    workflow_name = wf.get("workflow_name") or wf.get("workflowName") or "unnamed-workflow"
    schema_version = wf.get("workflow_schema_version") or "unknown"
    if not workflow_id:
        return {
            "status": None,
            "error": "workflow_json missing required 'workflow_id' (uuid).",
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    # --- 2) Build DAG from ASL or steps (top-level only) ---
    states = []
    start_at = None
    edges = []  # list of (src, dst)

    asl = wf.get("asl")
    if isinstance(asl, dict) and isinstance(asl.get("States"), dict):
        start_at = asl.get("StartAt")
        states_obj = asl.get("States") or {}
        states = list(states_obj.keys())

        for s_name, s_def in states_obj.items():
            if not isinstance(s_def, dict):
                continue
            s_type = s_def.get("Type")

            # Common Next edge
            if isinstance(s_def.get("Next"), str):
                edges.append((s_name, s_def["Next"]))

            # Choice edges (Choices[].Next and Default)
            if s_type == "Choice":
                for ch in s_def.get("Choices", []) or []:
                    nx = ch.get("Next")
                    if isinstance(nx, str):
                        edges.append((s_name, nx))
                if isinstance(s_def.get("Default"), str):
                    edges.append((s_name, s_def["Default"]))

            # Parallel/Map: branch internals are owned by the worker; downstream handled by 'Next'

    else:
        steps = wf.get("steps") or []
        if not steps:
            return {
                "status": None,
                "error": "Workflow must include either 'asl' (preferred) or non-empty 'steps'.",
                "created_keys": [],
                "existing_keys": [],
                "meta_sample": {}
            }
        prev = None
        for i, st in enumerate(steps):
            s_name = st.get("step_id") or ("Step_%d" % (i + 1))
            states.append(s_name)
            if prev is not None:
                edges.append((prev, s_name))
            prev = s_name
        start_at = states[0] if states else None

    if not states or not start_at:
        return {
            "status": None,
            "error": "Unable to determine states and StartAt.",
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    # --- 3) Compute deps and terminal states ---
    upstream = { s: [] for s in states }
    downstream = { s: [] for s in states }
    for src, dst in edges:
        if dst in upstream and src not in upstream[dst]:
            upstream[dst].append(src)
        if src in downstream and dst not in downstream[src]:
            downstream[src].append(dst)

    terminal_candidates = set()
    states_obj = (asl or {}).get("States") or {}
    for s in states:
        s_def = states_obj.get(s, {}) if isinstance(states_obj, dict) else {}
        s_type = s_def.get("Type")
        end_flag = bool(s_def.get("End")) if isinstance(s_def, dict) else False
        has_down = len(downstream.get(s, [])) > 0
        if s_type in ("Succeed", "Fail") or end_flag or not has_down:
            terminal_candidates.add(s)
    terminal_states = sorted(list(terminal_candidates))

    # --- 4) Optional agents map ---
    agents_map = {}
    if agents_map_json:
        try:
            tmp = json.loads(agents_map_json)
            if isinstance(tmp, dict):
                for k, v in tmp.items():
                    if k in upstream and isinstance(v, str):
                        agents_map[k] = v
        except Exception:
            # Ignore malformed agents_map_json
            pass

    # --- 5) Construct meta document (aligned to schemas/control-plane-meta-1.0.0.json) ---
    meta = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "schema_version": str(schema_version),
        "start_at": start_at,
        "terminal_states": terminal_states,
        "states": states,
        "agents": agents_map,     # optional, can be empty
        "skills": {},             # optional, planner may fill later
        "deps": { s: { "upstream": upstream.get(s, []), "downstream": downstream.get(s, []) } for s in states }
    }

    # --- 6) Seed RedisJSON keys idempotently ---
    created_keys = []
    existing_keys = []

    meta_key = "cp:wf:%s:meta" % workflow_id
    # JSON root path for RedisJSON v2 is '$'
    try:
        # Use NX to avoid overwriting an existing JSON key
        res = r.json().set(meta_key, '$', meta, nx=True)
        if res:  # set returns True/OK-like value on success, None if NX failed
            created_keys.append(meta_key)
            if isinstance(expiry_secs, int) and expiry_secs > 0:
                r.expire(meta_key, int(expiry_secs))
        else:
            existing_keys.append(meta_key)
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to write meta JSON: %s: %s" % (e.__class__.__name__, e),
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    default_state = {
        "status": "pending",
        "attempts": 0,
        "lease": { "token": None, "owner_agent_id": None, "ts": None, "ttl_s": None },
        "started_at": None,
        "finished_at": None,
        "last_error": None
    }

    for s in states:
        skey = "cp:wf:%s:state:%s" % (workflow_id, s)
        try:
            res = r.json().set(skey, '$', default_state, nx=True)
            if res:
                created_keys.append(skey)
                if isinstance(expiry_secs, int) and expiry_secs > 0:
                    r.expire(skey, int(expiry_secs))
            else:
                existing_keys.append(skey)
        except Exception as e:
            return {
                "status": None,
                "error": "Failed to write state JSON for '%s': %s: %s" % (s, e.__class__.__name__, e),
                "created_keys": created_keys,
                "existing_keys": existing_keys,
                "meta_sample": {}
            }

    # Fetch meta_sample (from Redis) so caller sees the actual persisted value
    try:
        meta_sample = r.json().get(meta_key, '$')
        # r.json().get returns a dict at root when path='$'; some deployments may return list with single element.
        if isinstance(meta_sample, list) and len(meta_sample) == 1:
            meta_sample = meta_sample[0]
        if not isinstance(meta_sample, dict):
            meta_sample = {}
    except Exception:
        meta_sample = {}

    status = "Control-plane created (or detected) for workflow '%s' with %d states." % (workflow_id, len(states))
    return {
        "status": status,
        "error": None,
        "created_keys": created_keys,
        "existing_keys": existing_keys,
        "meta_sample": meta_sample
    }
