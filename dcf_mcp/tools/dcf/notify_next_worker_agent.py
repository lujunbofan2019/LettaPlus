from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

def notify_next_worker_agent(
    workflow_id: str,
    source_state: str = None,
    reason: str = None,
    payload_json: str = None,
    redis_url: str = None,
    include_only_ready: bool = True,
    message_role: str = "system",
    async_message: bool = False,
    max_steps: int = None,
) -> Dict[str, Any]:
    """Notify downstream (or initial) worker agent(s) for a workflow state machine.

    Steps:
      1) Read control-plane meta (RedisJSON: cp:wf:{workflow_id}:meta).
      2) Choose targets:
         - If source_state is provided => deps[source_state].downstream
         - Else => states with no upstream (initial kickoff).
      3) If include_only_ready=True, filter to targets whose upstream deps are all 'done'.
      4) Resolve agent_id via meta.agents[target].
      5) Send a Letta message to each target with a workflow-event envelope.

    Args:
      workflow_id: Workflow UUID.
      source_state: Triggering state name (completed or firing). If None, notifies source states (no upstream deps).
      reason: Short reason for the event (e.g., "initial", "upstream_done").
      payload_json: Optional JSON string to include as event payload.
      redis_url: Redis URL (e.g., "redis://redis:6379/0"). Defaults to REDIS_URL env or "redis://redis:6379/0".
      include_only_ready: When True, only notify targets whose upstream states are all status == "done".
      message_role: Letta message role (default "system").
      async_message: If True, use async messaging (background run). Otherwise sync.
      max_steps: Optional Letta max_steps hint for the recipient run.

    Returns:
      dict: {
        "status": str | None,
        "error": str | None,
        "workflow_id": str,
        "source_state": str | None,
        "targets": [
          {
            "state": str,
            "agent_id": str | None,
            "sent": bool,
            "skipped_not_ready": bool,
            "reason": str | None,
            "message_id": str | None,
            "run_id": str | None,
            "error": str | None
          }, ...
        ]
      }
    """
    # Dependencies
    try:
        import redis  # type: ignore
    except Exception as e:
        return {"status": None, "error": f"Missing dependency: redis import error: {e}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}
    try:
        from letta_client import Letta  # type: ignore
    except Exception as e:
        return {"status": None, "error": f"Missing dependency: letta_client import error: {e}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}

    # Redis
    r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {"status": None, "error": f"Failed to connect Redis {r_url}: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}
    if not hasattr(r, "json"):
        return {"status": None, "error": "RedisJSON not available (r.json()).", "workflow_id": workflow_id, "source_state": source_state, "targets": []}

    # Meta
    meta_key = f"cp:wf:{workflow_id}:meta"
    try:
        meta = r.json().get(meta_key, "$")
        if isinstance(meta, list) and len(meta) == 1:
            meta = meta[0]
        if not isinstance(meta, dict):
            return {"status": None, "error": f"Control-plane meta missing/invalid at {meta_key}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}
    except Exception as e:
        return {"status": None, "error": f"Failed to read meta: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}

    deps = meta.get("deps") or {}
    agents_map = meta.get("agents") or {}
    all_states = meta.get("states") or []

    # Targets
    targets: list[str] = []
    if source_state:
        node = deps.get(source_state) or {}
        for t in (node.get("downstream") or []):
            if isinstance(t, str):
                targets.append(t)
    else:
        # initial kickoff: states with no upstream
        for s in all_states:
            ups = ((deps.get(s) or {}).get("upstream") or [])
            if not ups:
                targets.append(s)

    # Parse payload once
    try:
        payload = json.loads(payload_json) if payload_json else None
    except Exception as e:
        return {"status": None, "error": f"Invalid payload_json: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}

    # Letta client
    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://letta:8283"), token=os.getenv("LETTA_TOKEN"))
    except Exception as e:
        return {"status": None, "error": f"Failed to init Letta client: {e.__class__.__name__}: {e}", "workflow_id": workflow_id, "source_state": source_state, "targets": []}

    now_iso = datetime.now(timezone.utc).isoformat()
    reason_text = reason or ("initial" if source_state is None else "upstream_done")

    results = []
    for t_state in targets:
        # Optional readiness filter: evaluate inline (no helper defs)
        skipped_not_ready = False
        if include_only_ready:
            ups = ((deps.get(t_state) or {}).get("upstream") or [])
            if ups:
                # Must have all upstream 'done'
                all_done = True
                for u in ups:
                    u_key = f"cp:wf:{workflow_id}:state:{u}"
                    try:
                        udoc = r.json().get(u_key, "$")
                        if isinstance(udoc, list) and len(udoc) == 1:
                            udoc = udoc[0]
                    except Exception:
                        udoc = None
                    if not isinstance(udoc, dict) or udoc.get("status") != "done":
                        all_done = False
                        break
                if not all_done:
                    skipped_not_ready = True

        agent_id = agents_map.get(t_state)

        if skipped_not_ready:
            results.append({"state": t_state, "agent_id": agent_id, "sent": False, "skipped_not_ready": True,
                            "reason": "not_ready", "message_id": None, "run_id": None, "error": None})
            continue

        if not agent_id:
            results.append({"state": t_state, "agent_id": None, "sent": False, "skipped_not_ready": False,
                            "reason": "no_agent_assigned", "message_id": None, "run_id": None,
                            "error": f"No agent_id in meta.agents for state '{t_state}'."})
            continue

        event = {
            "type": "workflow_event",
            "workflow_id": workflow_id,
            "target_state": t_state,
            "source_state": source_state,
            "reason": reason_text,
            "payload": payload,
            "ts": now_iso,
            "control_plane": {
                "meta_key": meta_key,
                "state_key": f"cp:wf:{workflow_id}:state:{t_state}",
                "output_key": f"dp:wf:{workflow_id}:output:{t_state}"
            }
        }
        msg = {"role": message_role, "content": [{"type": "text", "text": json.dumps(event)}]}
        req = {"messages": [msg]}
        if isinstance(max_steps, int):
            req["max_steps"] = max_steps

        try:
            if async_message:
                resp = client.agents.messages.create_async(agent_id=agent_id, **req)
                run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
                results.append({"state": t_state, "agent_id": agent_id, "sent": True, "skipped_not_ready": False,
                                "reason": reason_text, "message_id": None, "run_id": run_id, "error": None})
            else:
                resp = client.agents.messages.create(agent_id=agent_id, **req)
                msg_id = None
                try:
                    mlist = getattr(resp, "messages", None)
                    if isinstance(mlist, list) and mlist:
                        msg_id = getattr(mlist[-1], "id", None) or getattr(mlist[-1], "message_id", None)
                except Exception:
                    msg_id = None
                results.append({"state": t_state, "agent_id": agent_id, "sent": True, "skipped_not_ready": False,
                                "reason": reason_text, "message_id": msg_id, "run_id": None, "error": None})
        except Exception as e:
            results.append({"state": t_state, "agent_id": agent_id, "sent": False, "skipped_not_ready": False,
                            "reason": reason_text, "message_id": None, "run_id": None,
                            "error": f"{e.__class__.__name__}: {e}"})

    return {
        "status": f"Notified {len(results)} target(s) for workflow '{workflow_id}'.",
        "error": None,
        "workflow_id": workflow_id,
        "source_state": source_state,
        "targets": results
    }
