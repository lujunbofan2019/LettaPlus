import os
import json
from datetime import datetime, timezone

def notify_if_ready(
    workflow_id: str,
    state: str,
    redis_url: str = None,
    reason: str = None,
    payload_json: str = None,
    require_ready: bool = True,
    skip_if_status_in_json: str = None,
    message_role: str = "system",
    async_message: bool = False,
    max_steps: int = None,
) -> dict:
    """Notify a single target state's worker agent IFF the state is ready (or unconditionally if require_ready=False).

    Ready := every upstream dependency (from meta.deps[state].upstream) has status == "done".
             Source states (no upstream) are considered ready by default.

    This function is choreography-friendly: it does not acquire leases or mutate state.

    Args:
      workflow_id: Workflow UUID.
      state: Target state name (usually an ASL Task).
      redis_url: Redis URL (defaults to REDIS_URL or "redis://redis:6379/0").
      reason: Reason string for the event (e.g., "initial", "upstream_done", "retry").
      payload_json: Optional JSON string included in the event payload.
      require_ready: If True (default), only notify when upstream deps are satisfied.
      skip_if_status_in_json: JSON array string of statuses that should cause a skip
                              (default: ["running","done","failed"]).
      message_role: Letta message role (default "system").
      async_message: If True, use async endpoint; else sync.
      max_steps: Optional Letta max_steps hint.

    Returns:
      dict: {
        "status": str | None,
        "error": str | None,
        "workflow_id": str,
        "state": str,
        "ready": bool | None,
        "skipped": bool,
        "skip_reason": str | None,
        "agent_id": str | None,
        "message_id": str | None,
        "run_id": str | None
      }
    """
    # Dependencies
    try:
        import redis  # type: ignore
    except Exception as e:
        return {"status": None, "error": f"Missing dependency: redis import error: {e}", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "dependency_missing", "agent_id": None, "message_id": None, "run_id": None}
    try:
        from letta_client import Letta  # type: ignore
    except Exception as e:
        return {"status": None, "error": f"Missing dependency: letta_client import error: {e}", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "dependency_missing", "agent_id": None, "message_id": None, "run_id": None}

    # Redis
    r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {"status": None, "error": f"Failed to connect Redis {r_url}: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "redis_unreachable", "agent_id": None, "message_id": None, "run_id": None}
    if not hasattr(r, "json"):
        return {"status": None, "error": "RedisJSON not available (r.json()).", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "redisjson_missing", "agent_id": None, "message_id": None, "run_id": None}

    meta_key = f"cp:wf:{workflow_id}:meta"
    state_key = f"cp:wf:{workflow_id}:state:{state}"

    # Meta
    try:
        meta = r.json().get(meta_key, "$")
        if isinstance(meta, list) and len(meta) == 1:
            meta = meta[0]
        if not isinstance(meta, dict):
            return {"status": None, "error": f"Control-plane meta missing/invalid at {meta_key}", "workflow_id": workflow_id, "state": state,
                    "ready": None, "skipped": True, "skip_reason": "meta_missing", "agent_id": None, "message_id": None, "run_id": None}
    except Exception as e:
        return {"status": None, "error": f"Failed to read meta: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "meta_read_error", "agent_id": None, "message_id": None, "run_id": None}

    deps = meta.get("deps") or {}
    agents_map = meta.get("agents") or {}
    agent_id = agents_map.get(state)
    if not agent_id:
        return {"status": None, "error": f"No agent assigned for state '{state}' (meta.agents).", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "no_agent_assigned", "agent_id": None, "message_id": None, "run_id": None}

    # Current state doc (for skip policy)
    try:
        sdoc = r.json().get(state_key, "$")
        if isinstance(sdoc, list) and len(sdoc) == 1:
            sdoc = sdoc[0]
        if not isinstance(sdoc, dict):
            return {"status": None, "error": f"State doc missing/invalid at {state_key}", "workflow_id": workflow_id, "state": state,
                    "ready": None, "skipped": True, "skip_reason": "state_missing", "agent_id": agent_id, "message_id": None, "run_id": None}
    except Exception as e:
        return {"status": None, "error": f"Failed to read state doc: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "state": state,
                "ready": None, "skipped": True, "skip_reason": "state_read_error", "agent_id": agent_id, "message_id": None, "run_id": None}

    # Skip list
    default_skip = ["running", "done", "failed"]
    try:
        skip_list = json.loads(skip_if_status_in_json) if skip_if_status_in_json else default_skip
        if not isinstance(skip_list, list):
            skip_list = default_skip
    except Exception:
        skip_list = default_skip

    cur_status = sdoc.get("status")
    if isinstance(cur_status, str) and cur_status in skip_list:
        return {"status": "skipped", "error": None, "workflow_id": workflow_id, "state": state, "ready": None, "skipped": True,
                "skip_reason": f"status_in_skip_list:{cur_status}", "agent_id": agent_id, "message_id": None, "run_id": None}

    # Readiness
    ready = None
    if require_ready:
        ready = True
        ups = ((deps.get(state) or {}).get("upstream") or [])
        for u in ups:
            u_key = f"cp:wf:{workflow_id}:state:{u}"
            try:
                udoc = r.json().get(u_key, "$")
                if isinstance(udoc, list) and len(udoc) == 1:
                    udoc = udoc[0]
            except Exception:
                udoc = None
            if not isinstance(udoc, dict) or udoc.get("status") != "done":
                ready = False
                break
        if not ready:
            return {"status": "not_ready", "error": None, "workflow_id": workflow_id, "state": state, "ready": False, "skipped": True,
                    "skip_reason": "upstream_incomplete", "agent_id": agent_id, "message_id": None, "run_id": None}

    # Payload
    try:
        payload = json.loads(payload_json) if payload_json else None
    except Exception as e:
        return {"status": None, "error": f"Invalid payload_json: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "state": state,
                "ready": ready, "skipped": True, "skip_reason": "payload_invalid", "agent_id": agent_id, "message_id": None, "run_id": None}

    # Send
    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://letta:8283"), token=os.getenv("LETTA_TOKEN"))
    except Exception as e:
        return {"status": None, "error": f"Letta init failed: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "state": state,
                "ready": ready, "skipped": True, "skip_reason": "letta_client_init_failed", "agent_id": agent_id, "message_id": None, "run_id": None}

    now_iso = datetime.now(timezone.utc).isoformat()
    event = {
        "type": "workflow_event",
        "workflow_id": workflow_id,
        "target_state": state,
        "source_state": None,
        "reason": reason or "notify_if_ready",
        "payload": payload,
        "ts": now_iso,
        "control_plane": {
            "meta_key": meta_key,
            "state_key": state_key,
            "output_key": f"dp:wf:{workflow_id}:output:{state}"
        }
    }

    msg = {"role": message_role, "content": [{"type": "text", "text": json.dumps(event)}]}
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
            try:
                mlist = getattr(resp, "messages", None)
                if isinstance(mlist, list) and mlist:
                    message_id = getattr(mlist[-1], "id", None) or getattr(mlist[-1], "message_id", None)
            except Exception:
                message_id = None
    except Exception as e:
        return {"status": None, "error": f"{e.__class__.__name__}: {e}", "workflow_id": workflow_id, "state": state, "ready": ready,
                "skipped": True, "skip_reason": "send_failed", "agent_id": agent_id, "message_id": None, "run_id": None}

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
