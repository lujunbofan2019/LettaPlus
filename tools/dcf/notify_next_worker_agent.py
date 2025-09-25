import os
import json
from datetime import datetime, timezone

def notify_next_worker_agent(workflow_id,
                             source_state=None,
                             reason=None,
                             payload_json=None,
                             redis_url=None,
                             include_only_ready=True,
                             message_role="system",
                             async_message=False,
                             max_steps=None):
    """
    Notify downstream (or initial) worker agent(s) for a workflow state machine.

    This function:
      1) Reads the control-plane meta doc (RedisJSON: cp:wf:{workflow_id}:meta)
      2) Determines targets:
         - If `source_state` is provided: targets = deps[source_state].downstream
         - If omitted: targets = "source states" (no upstream) — useful for initial kickoff
      3) (Optional) Filters to targets that are READY (all upstream states have status == "done")
      4) Looks up each target's assigned agent_id via meta.agents[target]
      5) Sends a Letta agent message (role=system by default) to each target agent
         containing an event envelope: {type, workflow_id, target_state, source_state, reason, payload, ts}
      6) Returns a per-target result list (success / failure)

    Args:
      workflow_id (str):
        Workflow UUID (string).
      source_state (str, optional):
        Name of the completed (or triggering) state. If omitted, will notify all "source" Task states
        (i.e., states with no upstream dependencies) — for initial kickoff.
      reason (str, optional):
        A short reason for the notification (e.g., "initial", "upstream_done").
      payload_json (str, optional):
        Optional JSON string with additional event payload for the target worker(s).
      redis_url (str, optional):
        Redis connection URL (e.g., "redis://localhost:6379/0"). Default from REDIS_URL or localhost.
      include_only_ready (bool, optional):
        If True (default), only notify targets whose upstream dependencies are satisfied (status == "done").
      message_role (str, optional):
        Message role to use when sending to the agent. Default "system". Consider "system" for event semantics.
      async_message (bool, optional):
        If True, uses the Letta async message API (background run). Default False (synchronous message).
      max_steps (int, optional):
        Optional Letta max_steps hint when creating the agent message.

    Returns:
      dict:
        {
          "status": str or None,
          "error": str or None,
          "workflow_id": str,
          "source_state": str or None,
          "targets": [
            {
              "state": str,
              "agent_id": str or None,
              "sent": bool,
              "skipped_not_ready": bool,
              "reason": str or None,
              "message_id": str or None,
              "run_id": str or None,
              "error": str or None
            },
            ...
          ]
        }
    """
    # --- Dependencies ---
    try:
        import redis  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: install the `redis` package. ImportError: %s" % e,
            "workflow_id": workflow_id,
            "source_state": source_state,
            "targets": []
        }

    try:
        from letta_client import Letta  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: letta_client not importable: %s" % e,
            "workflow_id": workflow_id,
            "source_state": source_state,
            "targets": []
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
            "source_state": source_state,
            "targets": []
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "RedisJSON not available (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "source_state": source_state,
            "targets": []
        }

    # --- Load meta ---
    meta_key = "cp:wf:%s:meta" % workflow_id
    try:
        meta = r.json().get(meta_key, '$')
        if isinstance(meta, list) and len(meta) == 1:
            meta = meta[0]
        if not isinstance(meta, dict):
            return {
                "status": None,
                "error": "Control-plane meta not found or invalid at %s" % meta_key,
                "workflow_id": workflow_id,
                "source_state": source_state,
                "targets": []
            }
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to read meta: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "source_state": source_state,
            "targets": []
        }

    deps = meta.get("deps") or {}
    agents_map = meta.get("agents") or {}
    all_states = meta.get("states") or []

    # --- Decide targets ---
    targets = []
    if source_state:
        node = deps.get(source_state) or {}
        downstream = node.get("downstream") or []
        for t in downstream:
            if isinstance(t, str):
                targets.append(t)
    else:
        # "Source" states: those with no upstream deps
        for s in all_states:
            node = deps.get(s) or {}
            ups = node.get("upstream") or []
            if not ups:
                targets.append(s)

    # --- Optional readiness filter ---
    def _is_ready(state_name):
        node = deps.get(state_name) or {}
        upstream = node.get("upstream") or []
        if not upstream:
            return True
        for u in upstream:
            u_key = "cp:wf:%s:state:%s" % (workflow_id, u)
            try:
                udoc = r.json().get(u_key, '$')
                if isinstance(udoc, list) and len(udoc) == 1:
                    udoc = udoc[0]
            except Exception:
                udoc = None
            if not isinstance(udoc, dict) or udoc.get("status") != "done":
                return False
        return True

    effective_targets = []
    for t in targets:
        if include_only_ready and not _is_ready(t):
            effective_targets.append((t, True))   # mark skipped_not_ready
        else:
            effective_targets.append((t, False))

    # --- Letta client ---
    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
                       token=os.getenv("LETTA_TOKEN"))
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to init Letta client: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "source_state": source_state,
            "targets": []
        }

    # --- Prepare payload template ---
    try:
        payload = json.loads(payload_json) if payload_json else None
    except Exception as e:
        return {
            "status": None,
            "error": "Invalid payload_json: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "source_state": source_state,
            "targets": []
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    reason_text = reason or ("initial" if source_state is None else "upstream_done")

    # --- Send messages ---
    results = []
    for (t_state, skipped_not_ready) in effective_targets:
        agent_id = agents_map.get(t_state)

        if skipped_not_ready:
            results.append({
                "state": t_state,
                "agent_id": agent_id,
                "sent": False,
                "skipped_not_ready": True,
                "reason": "not_ready",
                "message_id": None,
                "run_id": None,
                "error": None
            })
            continue

        if not agent_id:
            results.append({
                "state": t_state,
                "agent_id": None,
                "sent": False,
                "skipped_not_ready": False,
                "reason": "no_agent_assigned",
                "message_id": None,
                "run_id": None,
                "error": "No agent_id in meta.agents for state '%s'." % t_state
            })
            continue

        # Event envelope (use role=system for workflow events)
        event = {
            "type": "workflow_event",
            "workflow_id": workflow_id,
            "target_state": t_state,
            "source_state": source_state,
            "reason": reason_text,
            "payload": payload,
            "ts": now_iso,
            "control_plane": {
                "meta_key": "cp:wf:%s:meta" % workflow_id,
                "state_key": "cp:wf:%s:state:%s" % (workflow_id, t_state),
                "output_key": "dp:wf:%s:output:%s" % (workflow_id, t_state)
            }
        }

        # Build Letta message request: messages=[{role, content=[{type:"text", text:...}]}]
        msg = {
            "role": message_role,
            "content": [
                {"type": "text", "text": json.dumps(event)}
            ]
        }
        req = {"messages": [msg]}
        if isinstance(max_steps, int):
            req["max_steps"] = max_steps

        # Call sync or async message endpoint via SDK
        try:
            if async_message:
                # Asynchronous background run (fetchable by run_id)
                # API: POST /agents/{agent_id}/messages/async
                # SDK: client.agents.messages.create_async(...)
                resp = client.agents.messages.create_async(agent_id=agent_id, **req)
                run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
                results.append({
                    "state": t_state,
                    "agent_id": agent_id,
                    "sent": True,
                    "skipped_not_ready": False,
                    "reason": reason_text,
                    "message_id": None,
                    "run_id": run_id,
                    "error": None
                })
            else:
                # Synchronous message (returns agent's response messages)
                # API: POST /agents/{agent_id}/messages
                # SDK: client.agents.messages.create(...)
                resp = client.agents.messages.create(agent_id=agent_id, **req)
                # Some SDK builds return a wrapper with "messages" (list); capture a synthetic id if present
                msg_id = None
                try:
                    mlist = getattr(resp, "messages", None)
                    if isinstance(mlist, list) and mlist:
                        msg_id = getattr(mlist[-1], "id", None) or getattr(mlist[-1], "message_id", None)
                except Exception:
                    msg_id = None

                results.append({
                    "state": t_state,
                    "agent_id": agent_id,
                    "sent": True,
                    "skipped_not_ready": False,
                    "reason": reason_text,
                    "message_id": msg_id,
                    "run_id": None,
                    "error": None
                })
        except Exception as e:
            results.append({
                "state": t_state,
                "agent_id": agent_id,
                "sent": False,
                "skipped_not_ready": False,
                "reason": reason_text,
                "message_id": None,
                "run_id": None,
                "error": "%s: %s" % (e.__class__.__name__, e)
            })

    return {
        "status": "Notified %d target(s) for workflow '%s'." % (len(results), workflow_id),
        "error": None,
        "workflow_id": workflow_id,
        "source_state": source_state,
        "targets": results
    }
