from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

def create_workflow_control_plane(workflow_json: str,
                                  redis_url: str = None,
                                  expiry_secs: int = None,
                                  agents_map_json: str = None) -> Dict[str, Any]:
    """Create (idempotently) the RedisJSON control-plane for a workflow (choreography style).

    This seeds exactly one RedisJSON document for workflow metadata and one per state:
      - cp:wf:{workflow_id}:meta
      - cp:wf:{workflow_id}:state:{state_name}

    The meta document corresponds to `schemas/control-plane-meta-1.0.0.json`.
    Each state document corresponds to `schemas/control-plane-state-1.0.0.json`.

    Redis requirements:
      * Redis server with the RedisJSON module enabled.
      * redis-py that exposes `r.json()` with `.get()` / `.set()` and `nx=True`.

    Args:
      workflow_json (str):
        JSON string of the workflow definition. Prefer the ASL form with
        `asl.StartAt` and `asl.States`. If only `steps` exist, a linear DAG is
        inferred in order.
      redis_url (str, optional):
        Redis connection URL (e.g., "redis://redis:6379/0"). If not provided,
        uses env `REDIS_URL` or "redis://redis:6379/0".
      expiry_secs (int, optional):
        TTL to apply to seeded keys via EXPIRE. Omit or set <=0 for no TTL.
        (Recommended: no TTL during execution.)
      agents_map_json (str, optional):
        JSON string mapping state names to agent IDs. If provided and valid, it is
        copied into meta under `"agents"` for quick worker lookup, e.g.:
        {"Research": "agent_abc123", "Summarize": "agent_def456"}.

    Returns:
      dict: Result object:
        {
          "status": str or None,
          "error": str or None,
          "created_keys": [str],     # keys created in this call
          "existing_keys": [str],    # keys that already existed (left untouched)
          "meta_sample": dict        # meta JSON as persisted (round-tripped from Redis)
        }
    """
    # --- 0) Lazy import redis and connect ---
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

    r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
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
    if not isinstance(workflow_id, str) or not workflow_id:
        return {
            "status": None,
            "error": "workflow_json missing required 'workflow_id' (uuid string).",
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    # --- 2) Build DAG from ASL or steps ---
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
            nx = s_def.get("Next")
            if isinstance(nx, str):
                edges.append((s_name, nx))

            # Choice edges (Choices[].Next and Default)
            if s_type == "Choice":
                for ch in (s_def.get("Choices") or []):
                    nx2 = ch.get("Next")
                    if isinstance(nx2, str):
                        edges.append((s_name, nx2))
                if isinstance(s_def.get("Default"), str):
                    edges.append((s_name, s_def["Default"]))

            # Parallel / Map internals are worker-owned; only honor top-level Next
    else:
        steps = wf.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return {
                "status": None,
                "error": "Workflow must include either 'asl' (preferred) or non-empty 'steps' (array).",
                "created_keys": [],
                "existing_keys": [],
                "meta_sample": {}
            }
        prev = None
        for i, st in enumerate(steps):
            s_name = None
            if isinstance(st, dict):
                s_name = st.get("step_id")
            if not isinstance(s_name, str) or not s_name:
                s_name = "Step_%d" % (i + 1)
            states.append(s_name)
            if prev is not None:
                edges.append((prev, s_name))
            prev = s_name
        start_at = states[0] if states else None

    # Normalize/validate states
    states = list(dict.fromkeys(states))  # dedupe, preserve order
    if not states or not isinstance(start_at, str) or start_at not in states:
        return {
            "status": None,
            "error": "Unable to determine valid states and StartAt.",
            "created_keys": [],
            "existing_keys": [],
            "meta_sample": {}
        }

    # --- 3) Compute deps and terminal states ---
    upstream = {s: [] for s in states}
    downstream = {s: [] for s in states}
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

    # --- 4) Optional agents map (state_name -> agent_id) ---
    agents_map = {}
    if isinstance(agents_map_json, str) and agents_map_json.strip():
        try:
            tmp = json.loads(agents_map_json)
            if isinstance(tmp, dict):
                for k, v in tmp.items():
                    if isinstance(k, str) and k in upstream and isinstance(v, str):
                        agents_map[k] = v
        except Exception:
            # Ignore malformed map; keep empty
            pass

    # --- 5) Construct meta document ---
    now_iso = datetime.now(timezone.utc).isoformat()
    meta = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "schema_version": str(schema_version),
        "created_at": now_iso,
        "start_at": start_at,
        "terminal_states": terminal_states,
        "states": states,
        "agents": agents_map,  # optional, can be empty
        "skills": {},          # optional, planner may fill later
        "deps": {
            s: {"upstream": upstream.get(s, []), "downstream": downstream.get(s, [])}
            for s in states
        }
    }

    # --- 6) Seed RedisJSON keys idempotently ---
    created_keys = []
    existing_keys = []

    meta_key = "cp:wf:%s:meta" % workflow_id
    try:
        # JSON root path for RedisJSON v2 is '$'; NX to avoid clobbering existing meta
        res = r.json().set(meta_key, '$', meta, nx=True)
        if res:
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
        "status": "pending",   # pending|running|succeeded|failed|skipped
        "attempts": 0,
        "lease": {"token": None, "owner_agent_id": None, "ts": None, "ttl_s": None},
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

    # --- 7) Return meta round-tripped from Redis (for exact view) ---
    try:
        meta_sample = r.json().get(meta_key, '$')
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
