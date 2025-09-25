import os
import json
from datetime import datetime, timezone
from uuid import uuid4

def update_workflow_control_plane(workflow_id, state, redis_url=None, new_status=None, lease_token=None, owner_agent_id=None, lease_ttl_s=None, attempts_increment=None, error_message=None, set_started_at=False, set_finished_at=False, output_json=None, output_ttl_secs=None):
    """
    Atomically update a state's control-plane JSON (and optionally write data-plane output).

    Concurrency:
      - Uses WATCH/MULTI/EXEC on 'cp:wf:{id}:state:{state}' to avoid races.
      - If lease_token is provided, it must match the stored lease.token (or the stored token must be null).
        This prevents unrelated agents from overwriting each other's updates.

    Allowed patterns (examples):
      - Transition to 'running' with lease:
          new_status="running", lease_token="...", owner_agent_id="...", lease_ttl_s=300, set_started_at=True, attempts_increment=1
      - Mark done + write output:
          new_status="done", lease_token="...", set_finished_at=True, output_json='{"ok": true, "summary": "...", "data": {...}}'
      - Mark failed with error:
          new_status="failed", lease_token="...", set_finished_at=True, error_message="reason..."

    Args:
      workflow_id (str):
        The workflow UUID.
      state (str):
        The state name to update (e.g., an ASL Task state).
      redis_url (str, optional):
        Redis connection URL (e.g., "redis://localhost:6379/0"). If not provided,
        uses env REDIS_URL or "redis://localhost:6379/0".
      new_status (str, optional):
        One of {"pending", "running", "done", "failed"}. If omitted, status is left unchanged.
      lease_token (str, optional):
        Expected current lease token. If provided, the update will fail when the stored token
        is non-null and different from this value. If the stored token is null, the provided token
        is set together with owner_agent_id/ttl (when provided).
      owner_agent_id (str, optional):
        Owner ID to store into lease.owner_agent_id when setting or refreshing a lease.
      lease_ttl_s (int, optional):
        Lease TTL seconds stored in lease.ttl_s (informational; watchdog/renewal handled elsewhere).
      attempts_increment (int, optional):
        Number to add to 'attempts'. Use 1 when you move to 'running' for the first time.
      error_message (str, optional):
        Value for 'last_error'.
      set_started_at (bool, optional):
        If True, set 'started_at' to now (ISO-8601 UTC).
      set_finished_at (bool, optional):
        If True, set 'finished_at' to now (ISO-8601 UTC).
      output_json (str, optional):
        If provided, writes/overwrites data-plane key:
          dp:wf:{workflow_id}:output:{state}
        The JSON should conform to 'schemas/data-plane-output-1.0.0.json'.
      output_ttl_secs (int, optional):
        Optional TTL for the output key.

    Returns:
      dict:
        {
          "status": str or None,
          "error": str or None,
          "workflow_id": str,
          "state": str,
          "updated_state": dict or None,
          "output_written": bool
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
            "updated_state": None,
            "output_written": False
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
            "updated_state": None,
            "output_written": False
        }

    if not hasattr(r, "json"):
        return {
            "status": None,
            "error": "Redis connection does not expose RedisJSON (r.json()). Ensure RedisJSON is enabled.",
            "workflow_id": workflow_id,
            "state": state,
            "updated_state": None,
            "output_written": False
        }

    state_key = "cp:wf:%s:state:%s" % (workflow_id, state)
    now_iso = datetime.now(timezone.utc).isoformat()
    output_written = False

    # Validate new_status (if any)
    if new_status is not None and new_status not in ("pending", "running", "done", "failed"):
        return {
            "status": None,
            "error": "Invalid new_status '%s'." % new_status,
            "workflow_id": workflow_id,
            "state": state,
            "updated_state": None,
            "output_written": False
        }

    # WATCH loop (single attempt; the caller can retry on WatchError)
    pipe = r.pipeline()
    try:
        pipe.watch(state_key)

        current = r.json().get(state_key, '$')
        if isinstance(current, list) and len(current) == 1:
            current = current[0]
        if not isinstance(current, dict):
            return {
                "status": None,
                "error": "State key not found or not a JSON object: %s" % state_key,
                "workflow_id": workflow_id,
                "state": state,
                "updated_state": None,
                "output_written": False
            }

        # Lease check / fill
        cur_lease = current.get("lease") or {}
        cur_token = cur_lease.get("token")
        if lease_token is not None:
            # If there is a stored token different from the provided one -> reject
            if cur_token and cur_token != lease_token:
                return {
                    "status": None,
                    "error": "lease_mismatch: stored token differs from provided token.",
                    "workflow_id": workflow_id,
                    "state": state,
                    "updated_state": current,
                    "output_written": False
                }
        # Prepare next state
        next_state = dict(current)

        # Update attempts
        if isinstance(attempts_increment, int) and attempts_increment != 0:
            try:
                next_state["attempts"] = int(next_state.get("attempts", 0)) + attempts_increment
            except Exception:
                next_state["attempts"] = int(attempts_increment)

        # Update status
        if new_status is not None:
            next_state["status"] = new_status

        # Update timestamps
        if set_started_at:
            next_state["started_at"] = now_iso
        if set_finished_at:
            next_state["finished_at"] = now_iso

        # Update error
        if error_message is not None:
            next_state["last_error"] = error_message

        # Update lease contents if a lease_token is provided (set or refresh)
        if lease_token is not None:
            lease_obj = dict(next_state.get("lease") or {})
            lease_obj["token"] = lease_token
            if owner_agent_id is not None:
                lease_obj["owner_agent_id"] = owner_agent_id
            lease_obj["ts"] = now_iso
            if lease_ttl_s is not None:
                try:
                    lease_obj["ttl_s"] = int(lease_ttl_s)
                except Exception:
                    lease_obj["ttl_s"] = None
            next_state["lease"] = lease_obj

        # Begin transaction
        pipe.multi()
        # JSON.SET state
        pipe.execute_command('JSON.SET', state_key, '$', json.dumps(next_state))

        # Optional: write data-plane output
        if output_json:
            try:
                out_doc = json.loads(output_json)
            except Exception as e:
                pipe.reset()
                return {
                    "status": None,
                    "error": "Invalid output_json: %s: %s" % (e.__class__.__name__, e),
                    "workflow_id": workflow_id,
                    "state": state,
                    "updated_state": None,
                    "output_written": False
                }
            out_key = "dp:wf:%s:output:%s" % (workflow_id, state)
            pipe.execute_command('JSON.SET', out_key, '$', json.dumps(out_doc))
            if isinstance(output_ttl_secs, int) and output_ttl_secs > 0:
                pipe.execute_command('EXPIRE', out_key, int(output_ttl_secs))
            output_written = True

        # Commit
        pipe.execute()

    except redis.exceptions.WatchError:  # type: ignore
        return {
            "status": None,
            "error": "conflict: state modified concurrently; please retry.",
            "workflow_id": workflow_id,
            "state": state,
            "updated_state": None,
            "output_written": False
        }
    except Exception as e:
        try:
            pipe.reset()
        except Exception:
            pass
        return {
            "status": None,
            "error": "Update failed: %s: %s" % (e.__class__.__name__, e),
            "workflow_id": workflow_id,
            "state": state,
            "updated_state": None,
            "output_written": False
        }

    # Return latest state (post-commit)
    try:
        updated = r.json().get(state_key, '$')
        if isinstance(updated, list) and len(updated) == 1:
            updated = updated[0]
    except Exception:
        updated = next_state

    return {
        "status": "Updated state '%s' for workflow '%s'." % (state, workflow_id),
        "error": None,
        "workflow_id": workflow_id,
        "state": state,
        "updated_state": updated,
        "output_written": bool(output_written)
    }
