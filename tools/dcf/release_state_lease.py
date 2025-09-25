import os
import json
from datetime import datetime, timezone

def release_state_lease(workflow_id,
                        state,
                        lease_token,
                        owner_agent_id=None,
                        redis_url=None,
                        force=False,
                        clear_owner=True):
    """
    Release a held lease on a workflow state in the RedisJSON control-plane.

    Concurrency:
      - Uses WATCH/MULTI/EXEC on "cp:wf:{workflow_id}:state:{state}" to avoid races.
      - By default, requires that stored lease.token == lease_token (and, if provided,
        lease.owner_agent_id == owner_agent_id). Set force=True to clear the lease even if tokens
        or owner do not match (use sparingly; intended for administrative recovery).

    Semantics:
      - Clears lease.token and updates lease.ts to now (ISO-8601 UTC).
      - If clear_owner=True (default), also clears lease.owner_agent_id.
      - Does NOT change the state's 'status'. Typically you call release AFTER marking state
        'done' or 'failed'. If you need to revert, do so explicitly via update_workflow_control_plane.

    Typical usage:
      - A worker completes or aborts its task and releases its lease so others (or retries) may proceed.

    Args:
      workflow_id (str): Workflow UUID.
      state (str): State name (ASL Task state).
      lease_token (str): The lease token currently held by the worker.
      owner_agent_id (str, optional): If provided, must match stored lease.owner_agent_id unless force=True.
      redis_url (str, optional): Redis URL (default env REDIS_URL or redis://localhost:6379/0).
      force (bool, optional): If True, clear lease regardless of token/owner mismatch. Default False.
      clear_owner (bool, optional): If True, set lease.owner_agent_id to null when releasing. Default True.

    Returns:
      dict: {
        "status": str or None,            # "lease_released" on success
        "error": str or None,
        "workflow_id": str,
        "state": str,
        "lease": dict or None,            # Lease object after release
        "updated_state": dict or None
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
    now_iso = datetime.now(timezone.utc).isoformat()

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

        if not cur_token:
            return {
                "status": None,
                "error": "no_lease: nothing to release.",
                "workflow_id": workflow_id,
                "state": state,
                "lease": lease,
                "updated_state": cur
            }

        if not force:
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

        next_state = dict(cur)
        next_lease = dict(lease)
        next_lease["token"] = None
        if clear_owner:
            next_lease["owner_agent_id"] = None
        next_lease["ts"] = now_iso
        # keep ttl_s as informational; expiry based on ts+ttl_s will read as expired anyway
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
            "error": "release_failed: %s: %s" % (e.__class__.__name__, e),
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
        "status": "lease_released",
        "error": None,
        "workflow_id": workflow_id,
        "state": state,
        "lease": lease_out,
        "updated_state": updated
    }
