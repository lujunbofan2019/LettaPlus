import os
import json

def read_workflow_control_plane(workflow_id, redis_url=None, states_json=None, include_meta=True, compute_readiness=False):
    """
    Read control-plane data for a workflow from RedisJSON and (optionally) compute readiness.

    Redis keys:
      - cp:wf:{workflow_id}:meta
      - cp:wf:{workflow_id}:state:{state}

    If compute_readiness=True, the function returns, for each requested state, a boolean
    'ready' that is True iff all upstream states are present and have status == "done".

    Args:
      workflow_id (str):
        The workflow UUID (string).
      redis_url (str, optional):
        Redis connection URL (e.g., "redis://localhost:6379/0"). If not provided,
        uses env REDIS_URL or "redis://localhost:6379/0".
      states_json (str, optional):
        A JSON string of a list of state names to retrieve. If omitted or invalid,
        the function attempts to read ALL states listed in meta.states.
      include_meta (bool, optional):
        Whether to include the meta document in the response. Default True.
      compute_readiness (bool, optional):
        If True, compute the 'ready' flag for each returned state using meta.deps.upstream.

    Returns:
      dict:
        {
          "status": str or None,
          "error": str or None,
          "workflow_id": str or None,
          "meta": dict or None,            # present if include_meta=True and found
          "states": dict,                  # { state_name: state_doc }
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
    states_list = []
    readiness = None
    states_out = {}

    # 1) Load meta (optional but needed to infer full state list and readiness)
    if include_meta or compute_readiness or not states_json:
        try:
            meta = r.json().get("cp:wf:%s:meta" % workflow_id, '$')
            if isinstance(meta, list) and len(meta) == 1:
                meta = meta[0]
            if not isinstance(meta, dict):
                meta = None
        except Exception:
            meta = None

    # 2) Decide which states to read
    requested_states = None
    if states_json:
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
            # Unknown states to read
            return {
                "status": None,
                "error": "No states_json provided and meta.states unavailable. Cannot determine which states to read.",
                "workflow_id": workflow_id,
                "meta": meta if include_meta else None,
                "states": {},
                "readiness": None
            }

    # 3) Read state JSON docs
    for s in states_list:
        key = "cp:wf:%s:state:%s" % (workflow_id, s)
        try:
            doc = r.json().get(key, '$')
            if isinstance(doc, list) and len(doc) == 1:
                doc = doc[0]
            if isinstance(doc, dict):
                states_out[s] = doc
            else:
                states_out[s] = None
        except Exception:
            states_out[s] = None

    # 4) Compute readiness (optional)
    if compute_readiness:
        readiness = {}
        deps = {}
        if isinstance(meta, dict) and isinstance(meta.get("deps"), dict):
            deps = meta["deps"]

        for s in states_list:
            # ready if every upstream state exists AND has status == "done"
            ups = []
            if isinstance(deps.get(s), dict) and isinstance(deps[s].get("upstream"), list):
                ups = [u for u in deps[s]["upstream"] if isinstance(u, str)]
            if not ups:
                # Source states: ready if status is still pending
                current = states_out.get(s) or {}
                ready = (current.get("status") == "pending")
                readiness[s] = bool(ready)
                continue

            ok = True
            for u in ups:
                udoc = states_out.get(u)
                if not isinstance(udoc, dict) or udoc.get("status") != "done":
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
