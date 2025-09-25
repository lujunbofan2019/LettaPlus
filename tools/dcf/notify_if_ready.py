import os
import json
from datetime import datetime, timezone

def notify_if_ready(workflow_id,
                    state,
                    redis_url=None,
                    reason=None,
                    payload_json=None,
                    require_ready=True,
                    skip_if_status_in_json=None,
                    message_role="system",
                    async_message=False,
                    max_steps=None):
    """
    Notify a single target state's assigned worker agent IFF the state is ready.

    "Ready" means: every upstream dependency (from meta.deps[state].upstream) has a
    control-plane state document whose 'status' == "done". Source states (no upstream)
    are considered ready by default.

    This function is choreography-friendly:
      - It does NOT acquire a lease or mutate the state.
      - It simply signals the assigned agent (meta.agents[state]) if conditions are met.

    Args:
      workflow_id (str):
        Workflow UUID.
      state (str):
        Target state name (usually an ASL Task).
      redis_url (str, optional):
        Redis connection URL, e.g. "redis://localhost:6379/0". Defaults to env REDIS_URL
        or "redis://localhost:6379/0".
      reason (str, optional):
        Short reason for the event (e.g., "initial", "upstream_done", "retry").
      payload_json (str, optional):
        Optional JSON string included in the event payload for the target worker.
      require_ready (bool, optional):
        If True (default), only notify when upstream deps are satisfied. When False, readiness
        is ignored and a notification is sent (use carefully).
      skip_if_status_in_json (str, optional):
        JSON string of a list of statuses that should cause the notify to be skipped.
        Default is '["running", "done", "failed"]'.
      message_role (str, optional):
        Role for the Letta message. Default "system" for workflow events.
      async_message (bool, optional):
        If True, uses the async message endpoint (background run). Default False (sync).
      max_steps (int, optional):
        Optional Letta max_steps hint for the recipient agent's run.

    Returns:
      dict:
        {
          "status": str or None,          # human-readable summary
          "error": str or None,           # error on failure
          "workflow_id": str,
          "state": str,
          "ready": bool or None,          # readiness computed (or None when require_ready=False)
          "skipped": bool,                # True when not sent due to readiness/status checks
          "skip_reason": str or None,     # why it was skipped
          "agent_id": str or None,        # destination agent id (if any)
          "message_id": str or None,      # sync mode: last message id (best-effort)
          "run_id": str or None           # async mode: run id (best-effort)
        }
    """
    # --- Optional deps ---
    try:
        import redis  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: install the `redis` package. ImportError: %s" % e,
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "dependency_missing",
            "agent_id": None,
            "message_id": None,
            "run_id": None
        }

    try:
        from letta_client import Letta  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: letta_client not importable: %s" % e,
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "dependency_missing",
            "agent_id": None,
            "message_id": None,
            "run_id": None
        }

    # --- Redis connection ---
    r_url = redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to connect to Redis at %s: %s: %s" % (r_url, e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "redis_unreachable",
            "agent_id": None,
            "message_id": None,
            "run_id": None
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "RedisJSON not available (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "redisjson_missing",
            "agent_id": None,
            "message_id": None,
            "run_id": None
        }

    meta_key = "cp:wf:%s:meta" % workflow_id
    state_key = "cp:wf:%s:state:%s" % (workflow_id, state)

    # --- Load meta
    try:
        meta = r.json().get(meta_key, '$')
        if isinstance(meta, list) and len(meta) == 1:
            meta = meta[0]
        if not isinstance(meta, dict):
            return {
                "status": None,
                "error": "Control-plane meta not found or invalid at %s" % meta_key,
                "workflow_id": workflow_id,
                "state": state,
                "ready": None,
                "skipped": True,
                "skip_reason": "meta_missing",
                "agent_id": None,
                "message_id": None,
                "run_id": None
            }
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to read meta: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "meta_read_error",
            "agent_id": None,
            "message_id": None,
            "run_id": None
        }

    deps = meta.get("deps") or {}
    agents_map = meta.get("agents") or {}
    agent_id = agents_map.get(state)

    if not agent_id:
        return {
            "status": None,
            "error": "No agent assigned: meta.agents['%s'] missing." % state,
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "no_agent_assigned",
            "agent_id": None,
            "message_id": None,
            "run_id": None
        }

    # --- Read current state document for skip policy
    try:
        sdoc = r.json().get(state_key, '$')
        if isinstance(sdoc, list) and len(sdoc) == 1:
            sdoc = sdoc[0]
        if not isinstance(sdoc, dict):
            return {
                "status": None,
                "error": "State doc not found or invalid at %s" % state_key,
                "workflow_id": workflow_id,
                "state": state,
                "ready": None,
                "skipped": True,
                "skip_reason": "state_missing",
                "agent_id": agent_id,
                "message_id": None,
                "run_id": None
            }
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to read state doc: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "state_read_error",
            "agent_id": agent_id,
            "message_id": None,
            "run_id": None
        }

    # --- Skip policy (default: skip when already non-pending)
    default_skip = ["running", "done", "failed"]
    try:
        skip_list = json.loads(skip_if_status_in_json) if skip_if_status_in_json else default_skip
        if not isinstance(skip_list, list):
            skip_list = default_skip
    except Exception:
        skip_list = default_skip

    cur_status = sdoc.get("status")
    if isinstance(cur_status, str) and cur_status in skip_list:
        return {
            "status": "skipped",
            "error": None,
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "skipped": True,
            "skip_reason": "status_in_skip_list:%s" % cur_status,
            "agent_id": agent_id,
            "message_id": None,
            "run_id": None
        }

    # --- Compute readiness (if required)
    ready = None
    if require_ready:
        ready = True
        node = deps.get(state) or {}
        ups = node.get("upstream") or []
        for u in ups:
            u_key = "cp:wf:%s:state:%s" % (workflow_id, u)
            try:
                udoc = r.json().get(u_key, '$')
                if isinstance(udoc, list) and len(udoc) == 1:
                    udoc = udoc[0]
            except Exception:
                udoc = None
            if not isinstance(udoc, dict) or udoc.get("status") != "done":
                ready = False
                break

        if not ready:
            return {
                "status": "not_ready",
                "error": None,
                "workflow_id": workflow_id,
                "state": state,
                "ready": False,
                "skipped": True,
                "skip_reason": "upstream_incomplete",
                "agent_id": agent_id,
                "message_id": None,
                "run_id": None
            }

    # --- Prepare event payload
    try:
        payload = json.loads(payload_json) if payload_json else None
    except Exception as e:
        return {
            "status": None,
            "error": "Invalid payload_json: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": ready,
            "skipped": True,
            "skip_reason": "payload_invalid",
            "agent_id": agent_id,
            "message_id": None,
            "run_id": None
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    event = {
        "type": "workflow_event",
        "workflow_id": workflow_id,
        "target_state": state,
        "source_state": None,              # This tool is a direct notify; upstream source is implicit
        "reason": reason or "notify_if_ready",
        "payload": payload,
        "ts": now_iso,
        "control_plane": {
            "meta_key": meta_key,
            "state_key": state_key,
            "output_key": "dp:wf:%s:output:%s" % (workflow_id, state)
        }
    }

    # --- Send Letta message
    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
                       token=os.getenv("LETTA_TOKEN"))
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to init Letta client: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": ready,
            "skipped": True,
            "skip_reason": "letta_client_init_failed",
            "agent_id": agent_id,
            "message_id": None,
            "run_id": None
        }

    msg = {
        "role": message_role,
        "content": [{"type": "text", "text": json.dumps(event)}]
    }
    req = {"messages": [msg]}
    if isinstance(max_steps, int):
        req["max_steps"] = max_steps

    message_id = None
    run_id = None
    try:
        if async_message:
            resp = client.agents.messages.create_async(agent_id=agent_id, **req)
            run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
        else:
            resp = client.agents.messages.create(agent_id=agent_id, **req)
            # Best-effort: some SDKs expose the last message id
            try:
                mlist = getattr(resp, "messages", None)
                if isinstance(mlist, list) and mlist:
                    message_id = getattr(mlist[-1], "id", None) or getattr(mlist[-1], "message_id", None)
            except Exception:
                message_id = None
    except Exception as e:
        return {
            "status": None,
            "error": "%s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": ready,
            "skipped": True,
            "skip_reason": "send_failed",
            "agent_id": agent_id,
            "message_id": None,
            "run_id": None
        }

    return {
        "status": "notified",
        "error": None,
        "workflow_id": workflow_id,
        "state": state,
        "ready": ready,
        "skipped": False,
        "skip_reason": None,
        "agent_id": agent_id,
        "message_id": message_id,
        "run_id": run_id
    }
