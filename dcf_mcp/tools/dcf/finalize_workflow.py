from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

def finalize_workflow(
    workflow_id: str,
    redis_url: str = None,
    delete_worker_agents: bool = True,
    preserve_planner: bool = True,
    close_open_states: bool = True,
    overall_status: str = None,
    finalize_note: str = None
) -> Dict[str, Any]:
    """
    Finalize a workflow execution: optionally delete worker agents, close open states, and write final audit/summary metadata.
    Control-plane / data-plane keys are preserved for audit. No Redis keys are deleted.

    Args:
      workflow_id: Workflow UUID string.
      redis_url: Redis URL (e.g., "redis://redis:6379/0"). Defaults to env REDIS_URL or "redis://redis:6379/0".
      delete_worker_agents: If True, delete all worker agents referenced in meta.agents.
      preserve_planner: If True, do NOT delete the planner agent (meta.planner_agent_id).
      close_open_states: If True, set any 'pending'/'running' states to 'cancelled' and stamp 'finished_at'.
      overall_status: Optional final meta.status override ("succeeded"|"failed"|"cancelled"|"finalized"|...).
      finalize_note: Optional free-text note recorded into meta.finalize_note.

    Returns:
      {
        "status": "finalized"|None,
        "error": str|None,
        "workflow_id": str,
        "summary": {
          "states": {"total": int,"pending": int,"running": int,"done": int,"failed": int,"cancelled": int},
          "agents": {"to_delete": int,"deleted": int,"delete_errors": int},
          "final_status": str
        },
        "agents": [{"state": str, "agent_id": str, "deleted": bool, "error": str|None}],
        "warnings": [str, ...]
      }
    """
    # --- Dependencies ---
    try:
        import redis  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: install the `redis` package. ImportError: {e}",
            "workflow_id": workflow_id,
            "summary": None,
            "agents": [],
            "warnings": ["redis dependency missing"]
        }

    # Letta SDK is optional for finalize (we may still close states without it)
    letta_import_error = None
    Letta = None  # sentinel for availability
    try:
        from letta_client import Letta  # type: ignore
    except Exception as e:
        letta_import_error = f"Missing dependency: letta_client not importable: {e}"

    # --- Redis connection ---
    r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to connect to Redis at {r_url}: {e.__class__.__name__}: {e}",
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

    # --- Load meta ---
    meta_key = f"cp:wf:{workflow_id}:meta"
    try:
        meta = r.json().get(meta_key, '$')
        if isinstance(meta, list) and len(meta) == 1:
            meta = meta[0]
        if not isinstance(meta, dict):
            return {
                "status": None,
                "error": f"Control-plane meta not found or invalid at {meta_key}",
                "workflow_id": workflow_id,
                "summary": None,
                "agents": [],
                "warnings": []
            }
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to read meta: {e.__class__.__name__}: {e}",
            "workflow_id": workflow_id,
            "summary": None,
            "agents": [],
            "warnings": []
        }

    agents_map = meta.get("agents") or {}
    planner_agent_id = meta.get("planner_agent_id")
    states = meta.get("states") or []

    # --- Gather state statuses ---
    counts = {"pending": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
    state_docs = {}
    for s in states:
        s_key = f"cp:wf:{workflow_id}:state:{s}"
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
                counts["pending"] += 1
        else:
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
                # Keep lease as-is for audit; only update last_error with a clear reason
                new_doc["last_error"] = "finalized: state closed by finalize_workflow"
                s_key = f"cp:wf:{workflow_id}:state:{s}"
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
            # Some states remained open but were not force-closed
            final_status = "partial"
        else:
            # All states are done or cancelled without failures
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
                client = Letta(
                    base_url=os.getenv("LETTA_BASE_URL", "http://letta:8283"),
                    api_key=os.getenv("LETTA_API_KEY")
                )
            except Exception as e:
                delete_errors = to_delete
                for st_name, ag_id in agents_map.items():
                    agent_results.append({
                        "state": st_name,
                        "agent_id": ag_id,
                        "deleted": False,
                        "error": f"Letta init failed: {e.__class__.__name__}: {e}"
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
                            "error": f"{e.__class__.__name__}: {e}"
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
        # non-fatal
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
        audit_key = f"dp:wf:{workflow_id}:audit:finalize"
        r.json().set(audit_key, '$', audit_rec)
    except Exception:
        # non-fatal
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
