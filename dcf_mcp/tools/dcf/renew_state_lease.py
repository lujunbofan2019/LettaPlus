import os
import json
from datetime import datetime, timezone, timedelta

def renew_state_lease(
    workflow_id: str,
    state: str,
    lease_token: str,
    owner_agent_id: str = None,
    redis_url: str = None,
    lease_ttl_s: int = None,
    reject_if_expired: bool = True,
    touch_only: bool = False
) -> dict:
    """
    Renew (heartbeat) an existing lease for a workflow state in the RedisJSON control-plane.

    Concurrency:
      - Uses WATCH/MULTI/EXEC on "cp:wf:{workflow_id}:state:{state}" to avoid races.
      - Requires that the stored lease.token == lease_token. If not, renewal fails with 'lease_mismatch'.

    Semantics:
      - Always updates lease.ts to now (ISO-8601 UTC).
      - If touch_only=False and lease_ttl_s is provided, updates lease.ttl_s; otherwise preserves current ttl.
      - If reject_if_expired=True (default), renewal fails when the lease appears expired
        (now - ts > ttl_s). Set reject_if_expired=False to allow renewal even if clock drift caused
        soft expiry, but only when token matches.

    Args:
      workflow_id (str): Workflow UUID.
      state (str): Target state name (ASL Task state).
      lease_token (str): The lease token currently held by the worker.
      owner_agent_id (str): If provided, must match stored lease.owner_agent_id.
      redis_url (str): Redis URL (default env REDIS_URL or "redis://redis:6379/0").
      lease_ttl_s (int): New TTL seconds to set (if touch_only is False). If omitted, keeps existing TTL.
      reject_if_expired (bool): If True, fail when lease appears expired. Default True.
      touch_only (bool): If True, only update ts, never ttl_s. Default False.

    Returns:
      dict: {
        "status": "lease_renewed" | None,
        "error": str or None,
        "workflow_id": str,
        "state": str,
        "lease": dict or None,            # Updated lease object (post-commit) or current on failure
        "updated_state": dict or None     # State document after commit (or current on failure)
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

    state_key = f"cp:wf:{workflow_id}:state:{state}"
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
                "error": f"owner_mismatch: lease owner '{cur_owner}' != '{owner_agent_id}'.",
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
                    ts_obj = ts_obj.replace(tzinfo=timezone.utc)
            except Exception:
                ts_obj = None
            if ts_obj is not None and (now - ts_obj) > timedelta(seconds=int(cur_ttl)):
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
                # Preserve current ttl_s if provided value is invalid
                next_lease["ttl_s"] = lease.get("ttl_s")

        next_state["lease"] = next_lease

        pipe.multi()
        # Keep JSON op inside the transaction
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
            "error": f"renew_failed: {e.__class__.__name__}: {e}",
            "workflow_id": workflow_id,
            "state": state,
            "lease": None,
            "updated_state": None
        }

    # Read back the committed doc
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
