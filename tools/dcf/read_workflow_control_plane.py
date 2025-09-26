import os
import json

def read_workflow_control_plane(workflow_id: str,
                                redis_url: str = None,
                                states_json: str = None,
                                include_meta: bool = True,
                                compute_readiness: bool = False) -> dict:
    """Read workflow control-plane documents from RedisJSON and optionally compute readiness.

    Redis keys (per workflow):
      - cp:wf:{workflow_id}:meta
      - cp:wf:{workflow_id}:state:{state_name}

    Readiness semantics:
      * A state is READY iff:
        - It has NO upstream deps and its own status is "pending"; OR
        - ALL upstream states have a success-like status in {"succeeded", "done", "skipped"}.
      * For robustness, we treat "done" as an alias for "succeeded".

    Args:
      workflow_id: Workflow UUID string.
      redis_url: Optional Redis URL (e.g., "redis://localhost:6379/0").
                 Defaults to env REDIS_URL or "redis://localhost:6379/0".
      states_json: Optional JSON string of a list of state names to fetch.
                   If omitted/invalid, we load meta and read all states in meta.states.
      include_meta: If True, include the meta document in the response.
      compute_readiness: If True, compute {state_name: bool} readiness using meta.deps.upstream.

    Returns:
      dict: {
        "status": str or None,
        "error": str or None,
        "workflow_id": str or None,
        "meta": dict or None,            # present if include_meta=True and found
        "states": dict,                  # { state_name: state_doc or None }
        "readiness": dict or None        # { state_name: bool }, when compute_readiness=True
      }
    """
    try:
        import redis  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: install the `redis` package. ImportError: %s" % e,
            "workflow_id": None,
            "meta": None,
            "states": {},
            "readiness": None
        }

    r_url = redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to connect to Redis at %s: %s: %s" % (r_url, e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "meta": None,
            "states": {},
            "readiness": None
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "Redis connection does not expose RedisJSON (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "meta": None,
            "states": {},
            "readiness": None
        }

    meta = None
    states_out = {}
    readiness = None

    # 1) Load meta when needed (to resolve state list or compute readiness)
    meta_needed = include_meta or compute_readiness or not states_json
    if meta_needed:
        try:
            meta = r.json().get("cp:wf:%s:meta" % workflow_id, '$')
            if isinstance(meta, list) and len(meta) == 1:
                meta = meta[0]
            if not isinstance(meta, dict):
                meta = None
        except Exception:
            meta = None

    # 2) Determine which states to read
    states_list = []
    requested_states = None
    if isinstance(states_json, str):
        try:
            tmp = json.loads(states_json)
            if isinstance(tmp, list):
                requested_states = [s for s in tmp if isinstance(s, str)]
        except Exception:
            requested_states = None

    if requested_states:
        states_list = requested_states
    else:
        if isinstance(meta, dict) and isinstance(meta.get("states"), list):
            states_list = [s for s in meta["states"] if isinstance(s, str)]
        else:
            return {
                "status": None,
                "error": "No states_json provided and meta.states unavailable. Cannot determine which states to read.",
                "workflow_id": workflow_id,
                "meta": meta if include_meta else None,
                "states": {},
                "readiness": None
            }

    # 3) Read each state document
    for s in states_list:
        key = "cp:wf:%s:state:%s" % (workflow_id, s)
        try:
            doc = r.json().get(key, '$')
            if isinstance(doc, list) and len(doc) == 1:
                doc = doc[0]
            states_out[s] = doc if isinstance(doc, dict) else None
        except Exception:
            states_out[s] = None

    # 4) Compute readiness if requested
    if compute_readiness:
        readiness = {}
        deps = {}
        if isinstance(meta, dict) and isinstance(meta.get("deps"), dict):
            deps = meta["deps"]

        # Treat these statuses as success-like (allow legacy "done")
        success_like = {"succeeded", "done", "skipped"}

        for s in states_list:
            ups = []
            node = deps.get(s) if isinstance(deps, dict) else None
            if isinstance(node, dict) and isinstance(node.get("upstream"), list):
                ups = [u for u in node["upstream"] if isinstance(u, str)]

            if not ups:
                # Source nodes: READY when they remain pending
                cur = states_out.get(s) or {}
                readiness[s] = bool(cur.get("status") == "pending")
                continue

            ok = True
            for u in ups:
                udoc = states_out.get(u)
                u_status = (udoc or {}).get("status")
                if u_status not in success_like:
                    ok = False
                    break
            readiness[s] = ok

    return {
        "status": "Read %d state(s) for workflow '%s'." % (len(states_list), workflow_id),
        "error": None,
        "workflow_id": workflow_id,
        "meta": meta if include_meta else None,
        "states": states_out,
        "readiness": readiness
    }
