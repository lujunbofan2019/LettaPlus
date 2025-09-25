import os
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4

def acquire_state_lease(workflow_id,
                        state,
                        owner_agent_id,
                        redis_url=None,
                        lease_ttl_s=None,
                        require_ready=True,
                        require_owner_match=True,
                        allow_steal_if_expired=True,
                        set_running_on_acquire=True,
                        attempts_increment=1,
                        lease_token=None):
    """
    Acquire (atomically) a lease on a workflow state in the RedisJSON control-plane.

    Concurrency:
      - Uses WATCH/MULTI/EXEC on "cp:wf:{workflow_id}:state:{state}" to avoid races.
      - If a lease exists:
          * If expired (ts + ttl_s < now) and allow_steal_if_expired=True -> can be taken over.
          * Otherwise, acquisition fails with 'lease_held'.
      - If a lease does not exist (token is null) -> it is created.
      - Optionally verifies readiness (all upstream states 'done') before granting the lease.

    Typical usage:
      - Worker claims a state before starting:
          acquire_state_lease(wf, "Research", "agent_123", lease_ttl_s=300)
      - Returns a token; pass it into subsequent update calls (e.g., update_workflow_control_plane).

    Args:
      workflow_id (str):
        Workflow UUID.
      state (str):
        State name (usually an ASL Task state).
      owner_agent_id (str):
        The agent ID that will own the lease if acquired.
      redis_url (str, optional):
        Redis connection URL (e.g., "redis://localhost:6379/0"). If omitted, uses env REDIS_URL or default.
      lease_ttl_s (int, optional):
        TTL in seconds to store in the lease metadata (informational; external watchdog/renewal recommended).
        If omitted, defaults to 300 seconds.
      require_ready (bool, optional):
        If True, acquisition requires all upstream states to have status == "done".
      require_owner_match (bool, optional):
        If True, checks cp:wf:{id}:meta $.agents[state] equals owner_agent_id.
      allow_steal_if_expired (bool, optional):
        If True, an expired existing lease can be taken over.
      set_running_on_acquire (bool, optional):
        If True and current status == "pending", transition to "running" and set 'started_at' now.
      attempts_increment (int, optional):
        If set_running_on_acquire=True and status==pending, increment 'attempts' by this amount (usually 1).
      lease_token (str, optional):
        Optional precomputed token. If omitted, a new random token is generated.

    Returns:
      dict:
        {
          "status": str or None,
          "error": str or None,
          "workflow_id": str,
          "state": str,
          "ready": bool or None,           # Only set when require_ready=True
          "lease": {                       # The lease after acquisition (or current lease on failure)
            "token": str or None,
            "owner_agent_id": str or None,
            "ts": str or None,            # ISO-8601 UTC
            "ttl_s": int or None
          },
          "updated_state": dict or None    # Updated state doc (post-commit) or current on failure
        }
    """
    try:
        import redis  # type: ignore
        from redis.exceptions import WatchError  # type: ignore
    except Exception as e:
        return {
            "status": None,
            "error": "Missing dependency: install the `redis` package. ImportError: %s" % e,
            "workflow_id": workflow_id,
            "state": state,
            "ready": None,
            "lease": None,
            "updated_state": None
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

    state_key = "cp:wf:%s:state:%s" % (workflow_id, state)
    meta_key = "cp:wf:%s:meta" % workflow_id
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    default_ttl = 300 if lease_ttl_s is None else int(lease_ttl_s)

    # Optional readiness and owner checks require meta
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

    # Compute readiness if requested
    ready = None
    if require_ready:
        ready = False
        if isinstance(meta, dict):
            deps = meta.get("deps") or {}
            ups = []
            if isinstance(deps.get(state), dict) and isinstance(deps[state].get("upstream"), list):
                ups = [u for u in deps[state]["upstream"] if isinstance(u, str)]
            # Read upstream states in one go
            all_ok = True
            for u in ups:
                u_key = "cp:wf:%s:state:%s" % (workflow_id, u)
                try:
                    udoc = r.json().get(u_key, '$')
                    if isinstance(udoc, list) and len(udoc) == 1:
                        udoc = udoc[0]
                except Exception:
                    udoc = None
                if not isinstance(udoc, dict) or udoc.get("status") != "done":
                    all_ok = False
                    break
            # Source states (no upstream) are ready by definition
            if not ups:
                all_ok = True
            ready = all_ok
        else:
            return {
                "status": None,
                "error": "Meta not available; cannot evaluate readiness. Create control-plane first.",
                "workflow_id": workflow_id,
                "state": state,
                "ready": None,
                "lease": None,
                "updated_state": None
            }
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

    # Optional: owner match
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
                "error": "owner_mismatch: meta.agents['%s'] != '%s'." % (state, owner_agent_id),
                "workflow_id": workflow_id,
                "state": state,
                "ready": ready,
                "lease": None,
                "updated_state": None
            }

    # WATCH the state doc and attempt atomic acquisition
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

        # Determine if lease is available or expired
        lease_available = False
        lease_expired = False

        if not cur_token:
            lease_available = True
        else:
            # Evaluate expiry if ttl_s and ts present
            if isinstance(cur_ttl, int) and cur_ts:
                try:
                    ts_obj = datetime.fromisoformat(cur_ts)
                    if ts_obj.tzinfo is None:
                        ts_obj = ts_obj.replace(tzinfo=timezone.utc)
                except Exception:
                    ts_obj = None
                if ts_obj is not None and (now - ts_obj) > timedelta(seconds=int(cur_ttl)):
                    lease_expired = True

        if not lease_available:
            if lease_expired and allow_steal_if_expired:
                lease_available = True
            else:
                # Someone else holds a valid lease
                return {
                    "status": None,
                    "error": "lease_held: existing lease is active.",
                    "workflow_id": workflow_id,
                    "state": state,
                    "ready": ready,
                    "lease": cur_lease,
                    "updated_state": cur
                }

        # Build next state
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

        # Commit JSON in a transaction
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
            "error": "acquire_failed: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "ready": ready,
            "lease": None,
            "updated_state": None
        }

    # Read back the committed doc
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
