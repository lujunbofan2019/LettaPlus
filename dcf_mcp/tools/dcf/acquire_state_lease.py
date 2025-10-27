import os
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4

def acquire_state_lease(
    workflow_id: str,
    state: str,
    owner_agent_id: str,
    redis_url: str = None,
    lease_ttl_s: int = None,
    require_ready: bool = True,
    require_owner_match: bool = True,
    allow_steal_if_expired: bool = True,
    set_running_on_acquire: bool = True,
    attempts_increment: int = 1,
    lease_token: str = None
) -> dict:
    """
    Atomically acquire a lease on a workflow state in the RedisJSON control-plane.

    Concurrency:
      - Uses WATCH/MULTI/EXEC on "cp:wf:{workflow_id}:state:{state}" to avoid races.
      - If a lease exists:
          * If expired (ts + ttl_s < now) and allow_steal_if_expired=True -> takeover.
          * Else, if caller already holds the lease (same owner & token) -> "lease_already_held".
          * Else -> "lease_held" error.
      - If no lease -> create one.
      - Optionally enforces readiness (all upstream states "done") and owner match.

    Args:
      workflow_id (str): The workflow UUID.
      state (str): The state name (usually an ASL Task) to lock.
      owner_agent_id (str): The agent ID that will own the lease if acquired.
      redis_url (str): Redis URL (e.g., "redis://redis:6379/0"). Defaults to REDIS_URL env or "redis://redis:6379/0".
      lease_ttl_s (int): Lease TTL seconds to store in the state (informational). Default 300 if omitted.
      require_ready (bool): If True, require all upstream dependencies to be status == "done". Default True.
      require_owner_match (bool): If True, require meta.agents[state] == owner_agent_id (when present). Default True.
      allow_steal_if_expired (bool): If True, allow takeover when an existing lease is expired. Default True.
      set_running_on_acquire (bool): If True and current status == "pending", set status="running" and started_at=now. Default True.
      attempts_increment (int): Amount to add to attempts when transitioning to running. Default 1.
      lease_token (str): Optional precomputed token to set/use. If omitted, a random token is generated.

    Returns:
      dict: {
        "status": "lease_acquired" | "lease_already_held" | None,
        "error": str or None,
        "workflow_id": str,
        "state": str,
        "ready": bool or None,     # Only populated when require_ready=True
        "lease": {                 # Lease info after acquisition (or current on failure)
          "token": str or None,
          "owner_agent_id": str or None,
          "ts": str or None,      # ISO-8601 UTC
          "ttl_s": int or None
        } or None,
        "updated_state": dict or None  # Updated state doc (post-commit) or current on failure
      }
    """
    try:
        import redis  # type: ignore
        from redis.exceptions import WatchError  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: install the `redis` package. ImportError: {e}",
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "lease": None,
            "updated_state": None
        }

    r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
    try:
        r = redis.Redis.from_url(r_url, decode_responses=True)
        r.ping()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to connect to Redis at {r_url}: {e.__class__.__name__}: {e}",
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "lease": None,
            "updated_state": None
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "Redis connection does not expose RedisJSON (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "lease": None,
            "updated_state": None
        }

    state_key = f"cp:wf:{workflow_id}:state:{state}"
    meta_key = f"cp:wf:{workflow_id}:meta"
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    default_ttl = 300 if lease_ttl_s is None else int(lease_ttl_s)

    # Load meta if needed
    meta = None
    if require_ready or require_owner_match:
        try:
            meta = r.json().get(meta_key, '$')
            if isinstance(meta, list) and len(meta) == 1:
                meta = meta[0]
            if not isinstance(meta, dict):
                meta = None
        except Exception:
            meta = None

    # Readiness check
    ready = None
    if require_ready:
        if not isinstance(meta, dict):
            return {
                "status": None,
                "error": "Meta not available; cannot evaluate readiness. Create control-plane first.",
                "workflow_id": workflow_id,
                "state": state,
                "ready": None,
                "lease": None,
                "updated_state": None
            }
        deps = meta.get("deps") or {}
        ups = []
        if isinstance(deps.get(state), dict) and isinstance(deps[state].get("upstream"), list):
            ups = [u for u in deps[state]["upstream"] if isinstance(u, str)]
        all_ok = True
        for u in ups:
            u_key = f"cp:wf:{workflow_id}:state:{u}"
            try:
                udoc = r.json().get(u_key, '$')
                if isinstance(udoc, list) and len(udoc) == 1:
                    udoc = udoc[0]
            except Exception:
                udoc = None
            if not isinstance(udoc, dict) or udoc.get("status") != "done":
                all_ok = False
                break
        if not ups:
            all_ok = True
        ready = all_ok
        if not ready:
            return {
                "status": None,
                "error": "not_ready: upstream dependencies not satisfied.",
                "workflow_id": workflow_id,
                "state": state,
                "ready": False,
                "lease": None,
                "updated_state": None
            }

    # Owner match check
    if require_owner_match:
        if not isinstance(meta, dict) or not isinstance(meta.get("agents"), dict):
            return {
                "status": None,
                "error": "Meta.agents not available; cannot verify ownership.",
                "workflow_id": workflow_id,
                "state": state,
                "ready": ready,
                "lease": None,
                "updated_state": None
            }
        assigned = meta["agents"].get(state)
        if assigned and assigned != owner_agent_id:
            return {
                "status": None,
                "error": f"owner_mismatch: meta.agents['{state}'] != '{owner_agent_id}'.",
                "workflow_id": workflow_id,
                "state": state,
                "ready": ready,
                "lease": None,
                "updated_state": None
            }

    pipe = r.pipeline()
    try:
        pipe.watch(state_key)

        cur = r.json().get(state_key, '$')
        if isinstance(cur, list) and len(cur) == 1:
            cur = cur[0]
        if not isinstance(cur, dict):
            return {
                "status": None,
                "error": "State doc missing or not a JSON object.",
                "workflow_id": workflow_id,
                "state": state,
                "ready": ready,
                "lease": None,
                "updated_state": None
            }

        cur_lease = cur.get("lease") or {}
        cur_token = cur_lease.get("token")
        cur_owner = cur_lease.get("owner_agent_id")
        cur_ts = cur_lease.get("ts")
        cur_ttl = cur_lease.get("ttl_s")

        # Parse stored ts (robust to 'Z')
        ts_obj = None
        if isinstance(cur_ts, str) and cur_ts:
            ts_s = cur_ts.replace("Z", "+00:00")
            try:
                ts_obj = datetime.fromisoformat(ts_s)
                if ts_obj.tzinfo is None:
                    ts_obj = ts_obj.replace(tzinfo=timezone.utc)
            except Exception:
                ts_obj = None

        lease_available = False
        lease_expired = False

        if not cur_token:
            lease_available = True
        else:
            if isinstance(cur_ttl, int) and ts_obj is not None:
                if (now - ts_obj) > timedelta(seconds=int(cur_ttl)):
                    lease_expired = True
            # Caller already holds the lease with same token
            if (not lease_expired) and cur_owner == owner_agent_id and (lease_token is None or lease_token == cur_token):
                return {
                    "status": "lease_already_held",
                    "error": None,
                    "workflow_id": workflow_id,
                    "state": state,
                    "ready": ready,
                    "lease": cur_lease,
                    "updated_state": cur
                }

        if not lease_available:
            if lease_expired and allow_steal_if_expired:
                lease_available = True
            else:
                return {
                    "status": None,
                    "error": "lease_held: existing lease is active.",
                    "workflow_id": workflow_id,
                    "state": state,
                    "ready": ready,
                    "lease": cur_lease,
                    "updated_state": cur
                }

        # Build next state + lease
        next_state = dict(cur)
        next_lease = dict(cur_lease) if isinstance(cur_lease, dict) else {}
        next_lease["token"] = lease_token or ("lease-" + str(uuid4()))
        next_lease["owner_agent_id"] = owner_agent_id
        next_lease["ts"] = now_iso
        next_lease["ttl_s"] = int(default_ttl)
        next_state["lease"] = next_lease

        if set_running_on_acquire and next_state.get("status") == "pending":
            next_state["status"] = "running"
            next_state["started_at"] = now_iso
            if isinstance(attempts_increment, int) and attempts_increment != 0:
                try:
                    next_state["attempts"] = int(next_state.get("attempts", 0)) + attempts_increment
                except Exception:
                    next_state["attempts"] = int(attempts_increment)

        # Commit atomically
        pipe.multi()
        pipe.execute_command('JSON.SET', state_key, '$', json.dumps(next_state))
        pipe.execute()

    except WatchError:
        try:
            pipe.reset()
        except Exception:
            pass
        return {
            "status": None,
            "error": "conflict: state modified concurrently; please retry.",
            "workflow_id": workflow_id,
            "state": state,
            "ready": ready,
            "lease": None,
            "updated_state": None
        }
    except Exception as e:
        try:
            pipe.reset()
        except Exception:
            pass
        return {
            "status": None,
            "error": f"acquire_failed: {e.__class__.__name__}: {e}",
            "workflow_id": workflow_id,
            "state": state,
            "ready": ready,
            "lease": None,
            "updated_state": None
        }

    # Read-back post-commit
    try:
        updated = r.json().get(state_key, '$')
        if isinstance(updated, list) and len(updated) == 1:
            updated = updated[0]
        lease_out = updated.get("lease") if isinstance(updated, dict) else None
    except Exception:
        updated = next_state
        lease_out = next_state.get("lease")

    return {
        "status": "lease_acquired",
        "error": None,
        "workflow_id": workflow_id,
        "state": state,
        "ready": ready,
        "lease": lease_out,
        "updated_state": updated
    }
