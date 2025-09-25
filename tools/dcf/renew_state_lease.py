import os
import json
from datetime import datetime, timezone, timedelta

def renew_state_lease(workflow_id,
                      state,
                      lease_token,
                      owner_agent_id=None,
                      redis_url=None,
                      lease_ttl_s=None,
                      reject_if_expired=True,
                      touch_only=False):
    """
    Renew (heartbeat) an existing lease for a workflow state in the RedisJSON control-plane.

    Concurrency:
      - Uses WATCH/MULTI/EXEC on "cp:wf:{workflow_id}:state:{state}" to avoid races.
      - Requires that the stored lease.token == lease_token. If not, renewal fails with 'lease_mismatch'.

    Semantics:
      - Updates lease.ts to now (ISO-8601 UTC).
      - If touch_only=False and lease_ttl_s is provided, update lease.ttl_s; otherwise preserves current ttl.
      - If reject_if_expired=True (default), renewal fails when the lease appears expired
        (now - ts > ttl_s). Set reject_if_expired=False to allow renewal even if clock drift caused
        soft expiry, but only when token matches.

    Typical usage:
      - A worker holding the lease sends periodic renewals (e.g., every 1/3 of ttl) to indicate liveness.

    Args:
      workflow_id (str): Workflow UUID.
      state (str): State name (ASL Task state).
      lease_token (str): The lease token currently held by the worker.
      owner_agent_id (str, optional): If provided, must match stored lease.owner_agent_id.
      redis_url (str, optional): Redis URL (default env REDIS_URL or redis://localhost:6379/0).
      lease_ttl_s (int, optional): New TTL to set (if touch_only=False). If omitted, keeps existing TTL.
      reject_if_expired (bool, optional): If True, fail when lease appears expired. Default True.
      touch_only (bool, optional): If True, only update ts, never ttl_s. Default False.

    Returns:
      dict: {
        "status": str or None,            # "lease_renewed" on success
        "error": str or None,
        "workflow_id": str,
        "state": str,
        "lease": dict or None,            # Updated lease object
        "updated_state": dict or None     # Updated state document (post-commit)
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
            "lease": None,
            "updated_state": None
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "RedisJSON not available (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "state": state,
            "lease": None,
            "updated_state": None
        }

    state_key = "cp:wf:%s:state:%s" % (workflow_id, state)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

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
                "lease": None,
                "updated_state": None
            }

        lease = cur.get("lease") or {}
        cur_token = lease.get("token")
        cur_owner = lease.get("owner_agent_id")
        cur_ts = lease.get("ts")
        cur_ttl = lease.get("ttl_s")

        if not cur_token:
            return {
                "status": None,
                "error": "no_lease: cannot renew a missing lease.",
                "workflow_id": workflow_id,
                "state": state,
                "lease": lease,
                "updated_state": cur
            }

        if cur_token != lease_token:
            return {
                "status": None,
                "error": "lease_mismatch: stored token differs from provided token.",
                "workflow_id": workflow_id,
                "state": state,
                "lease": lease,
                "updated_state": cur
            }

        if owner_agent_id is not None and cur_owner and cur_owner != owner_agent_id:
            return {
                "status": None,
                "error": "owner_mismatch: lease owner '%s' != '%s'." % (cur_owner, owner_agent_id),
                "workflow_id": workflow_id,
                "state": state,
                "lease": lease,
                "updated_state": cur
            }

        # Expiry check
        if reject_if_expired and isinstance(cur_ttl, int) and cur_ts:
            try:
                ts_obj = datetime.fromisoformat(cur_ts)
                if ts_obj.tzinfo is None:
                    from datetime import timezone as _tz
                    ts_obj = ts_obj.replace(tzinfo=_tz.utc)
            except Exception:
                ts_obj = None
            if ts_obj is not None and now - ts_obj > timedelta(seconds=int(cur_ttl)):
                return {
                    "status": None,
                    "error": "lease_expired",
                    "workflow_id": workflow_id,
                    "state": state,
                    "lease": lease,
                    "updated_state": cur
                }

        next_state = dict(cur)
        next_lease = dict(lease)
        next_lease["ts"] = now_iso
        if not touch_only and lease_ttl_s is not None:
            try:
                next_lease["ttl_s"] = int(lease_ttl_s)
            except Exception:
                next_lease["ttl_s"] = lease.get("ttl_s")

        next_state["lease"] = next_lease

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
            "error": "renew_failed: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "lease": None,
            "updated_state": None
        }

    # Read back
    try:
        updated = r.json().get(state_key, '$')
        if isinstance(updated, list) and len(updated) == 1:
            updated = updated[0]
        lease_out = updated.get("lease")
    except Exception:
        updated = next_state
        lease_out = next_lease

    return {
        "status": "lease_renewed",
        "error": None,
        "workflow_id": workflow_id,
        "state": state,
        "lease": lease_out,
        "updated_state": updated
    }
