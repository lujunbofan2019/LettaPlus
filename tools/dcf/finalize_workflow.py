import os
import json
from datetime import datetime, timezone

def finalize_workflow(workflow_id,
                      redis_url=None,
                      delete_worker_agents=True,
                      preserve_planner=True,
                      close_open_states=True,
                      overall_status=None,
                      finalize_note=None):
    """
    Finalize a workflow execution: clean up worker agents (optional), close open states
    to 'cancelled' (optional), and write final audit/summary metadata.

    This preserves the Redis control-plane/data-plane keys for audit purposes.
    No control-plane or data-plane keys are deleted.

    Args:
      workflow_id (str):
        Workflow UUID string.
      redis_url (str, optional):
        Redis URL, e.g. "redis://localhost:6379/0". Defaults to env REDIS_URL or local.
      delete_worker_agents (bool, optional):
        If True (default), delete all worker agents referenced in meta.agents.
      preserve_planner (bool, optional):
        If True (default), do NOT delete the planner agent even if recorded in meta.planner_agent_id.
      close_open_states (bool, optional):
        If True (default), set any 'pending' or 'running' states to 'cancelled' with 'finished_at' now.
      overall_status (str, optional):
        Force a top-level final status in meta.status (e.g., "succeeded", "failed", "cancelled", "finalized").
        If omitted, status is derived from per-state statuses:
          - if any state == "failed" -> "failed"
          - elif any state in ("pending","running") -> "partial"
          - else -> "succeeded"
      finalize_note (str, optional):
        Optional free-text note recorded into meta.finalize_note.

    Returns:
      dict:
        {
          "status": str or None,              # "finalized"
          "error": str or None,
          "workflow_id": str,
          "summary": {
            "states": {
              "total": int,
              "pending": int,
              "running": int,
              "done": int,
              "failed": int,
              "cancelled": int
            },
            "agents": {
              "to_delete": int,
              "deleted": int,
              "delete_errors": int
            },
            "final_status": str
          },
          "agents": [
            {"state": str, "agent_id": str, "deleted": bool, "error": str or None}
          ],
          "warnings": [str, ...]
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
            "summary": None,
            "agents": [],
            "warnings": ["redis dependency missing"]
        }

    try:
        from letta_client import Letta  # type: ignore
    except Exception as e:
        # We can finalize without deleting agents; degrade gracefully.
        letta_import_error = "Missing dependency: letta_client not importable: %s" % e
        Letta = None
    else:
        letta_import_error = None

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
            "summary": None,
            "agents": [],
            "warnings": []
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "RedisJSON not available (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "summary": None,
            "agents": [],
            "warnings": []
        }

    now_iso = datetime.now(timezone.utc).isoformat()

    # --- Keys ---
    meta_key = "cp:wf:%s:meta" % workflow_id

    # --- Load meta ---
    try:
        meta = r.json().get(meta_key, '$')
        if isinstance(meta, list) and len(meta) == 1:
            meta = meta[0]
        if not isinstance(meta, dict):
            return {
                "status": None,
                "error": "Control-plane meta not found or invalid at %s" % meta_key,
                "workflow_id": workflow_id,
                "summary": None,
                "agents": [],
                "warnings": []
            }
    except Exception as e:
        return {
            "status": None,
            "error": "Failed to read meta: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "summary": None,
            "agents": [],
            "warnings": []
        }

    agents_map = meta.get("agents") or {}
    planner_agent_id = meta.get("planner_agent_id")
    states = meta.get("states") or []
    deps = meta.get("deps") or {}

    # --- Gather state statuses ---
    counts = {"pending": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
    state_docs = {}
    for s in states:
        s_key = "cp:wf:%s:state:%s" % (workflow_id, s)
        try:
            sdoc = r.json().get(s_key, '$')
            if isinstance(sdoc, list) and len(sdoc) == 1:
                sdoc = sdoc[0]
        except Exception:
            sdoc = None
        if isinstance(sdoc, dict):
            state_docs[s] = sdoc
            st = sdoc.get("status")
            if st in counts:
                counts[st] += 1
            else:
                # unknown status; treat as pending for safety
                counts["pending"] += 1
        else:
            # missing state doc; treat as pending
            state_docs[s] = None
            counts["pending"] += 1

    # --- Optionally close open states (pending/running -> cancelled) ---
    closed_now = 0
    if close_open_states:
        pipe = r.pipeline()
        for s, sdoc in state_docs.items():
            st = (sdoc or {}).get("status")
            if st in ("pending", "running"):
                new_doc = dict(sdoc or {})
                new_doc["status"] = "cancelled"
                new_doc["finished_at"] = now_iso
                msg = "finalized: state closed by finalize_workflow"
                if not isinstance(new_doc.get("errors"), list):
                    new_doc["errors"] = []
                new_doc["errors"].append(msg)
                # keep lease as-is (cleared or stale) — audit trail
                s_key = "cp:wf:%s:state:%s" % (workflow_id, s)
                pipe.execute_command('JSON.SET', s_key, '$', json.dumps(new_doc))
                closed_now += 1
        try:
            pipe.execute()
            # refresh counters
            counts["cancelled"] += closed_now
            counts["pending"] = max(0, counts["pending"] - closed_now)
            counts["running"] = max(0, counts["running"] - closed_now)
        except Exception:
            # Non-fatal; continue with best-effort summary
            pass

    # --- Compute final status if not provided ---
    if overall_status is None:
        if counts["failed"] > 0:
            final_status = "failed"
        elif counts["pending"] > 0 or counts["running"] > 0:
            final_status = "partial"
        else:
            final_status = "succeeded"
    else:
        final_status = str(overall_status)

    # --- Optionally delete worker agents ---
    agent_results = []
    delete_errors = 0
    to_delete = 0
    deleted = 0

    if delete_worker_agents and agents_map:
        to_delete = len(agents_map)
        client = None
        if Letta is None:
            delete_errors = to_delete
            for st_name, ag_id in agents_map.items():
                agent_results.append({
                    "state": st_name,
                    "agent_id": ag_id,
                    "deleted": False,
                    "error": letta_import_error or "letta_client not available"
                })
        else:
            try:
                client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
                               token=os.getenv("LETTA_TOKEN"))
            except Exception as e:
                delete_errors = to_delete
                for st_name, ag_id in agents_map.items():
                    agent_results.append({
                        "state": st_name,
                        "agent_id": ag_id,
                        "deleted": False,
                        "error": "Letta init failed: %s: %s" % (e.__class__.__name__, e)
                    })
                client = None

            if client is not None:
                for st_name, ag_id in agents_map.items():
                    if preserve_planner and planner_agent_id and ag_id == planner_agent_id:
                        agent_results.append({
                            "state": st_name,
                            "agent_id": ag_id,
                            "deleted": False,
                            "error": "skipped_planner"
                        })
                        continue
                    try:
                        # Best-effort delete; ignore if already gone
                        client.agents.delete(agent_id=ag_id)
                        agent_results.append({
                            "state": st_name,
                            "agent_id": ag_id,
                            "deleted": True,
                            "error": None
                        })
                        deleted += 1
                    except Exception as e:
                        agent_results.append({
                            "state": st_name,
                            "agent_id": ag_id,
                            "deleted": False,
                            "error": "%s: %s" % (e.__class__.__name__, e)
                        })
                        delete_errors += 1

    # --- Write finalize metadata + audit record ---
    meta_updates = dict(meta)
    meta_updates["finalized_at"] = now_iso
    meta_updates["status"] = final_status
    if finalize_note:
        meta_updates["finalize_note"] = finalize_note

    try:
        r.json().set(meta_key, '$', meta_updates)
    except Exception:
        # non-fatal; continue
        pass

    audit_rec = {
        "type": "finalize",
        "workflow_id": workflow_id,
        "ts": now_iso,
        "final_status": final_status,
        "counts": counts,
        "agents": {
            "to_delete": to_delete,
            "deleted": deleted,
            "delete_errors": delete_errors
        },
        "note": finalize_note or None
    }
    try:
        audit_key = "dp:wf:%s:audit:finalize" % workflow_id
        r.json().set(audit_key, '$', audit_rec)
    except Exception:
        # non-fatal; continue
        pass

    summary = {
        "states": {
            "total": len(states),
            "pending": counts["pending"],
            "running": counts["running"],
            "done": counts["done"],
            "failed": counts["failed"],
            "cancelled": counts["cancelled"]
        },
        "agents": {
            "to_delete": to_delete,
            "deleted": deleted,
            "delete_errors": delete_errors
        },
        "final_status": final_status
    }

    return {
        "status": "finalized",
        "error": None,
        "workflow_id": workflow_id,
        "summary": summary,
        "agents": agent_results,
        "warnings": ([] if not letta_import_error else [letta_import_error])
    }
