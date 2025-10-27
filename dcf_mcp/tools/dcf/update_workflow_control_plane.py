import os
import json
from datetime import datetime, timezone

def update_workflow_control_plane(workflow_id: str,
                                  state: str,
                                  redis_url: str = None,
                                  new_status: str = None,
                                  lease_token: str = None,
                                  owner_agent_id: str = None,
                                  lease_ttl_s: int = None,
                                  attempts_increment: int = None,
                                  error_message: str = None,
                                  set_started_at: bool = False,
                                  set_finished_at: bool = False,
                                  output_json: str = None,
                                  output_ttl_secs: int = None) -> dict:
    """Atomically update a state's control-plane JSON and optionally write data-plane output.

    Concurrency:
      * Uses WATCH/MULTI/EXEC on cp:wf:{workflow_id}:state:{state}.
      * When `lease_token` is provided, the update is allowed only if the stored token
        is null or matches `lease_token`. This prevents unrelated agents from clobbering
        each other's updates.

    Status normalization:
      * Accepts synonyms and normalizes:
        - "done", "success", "succeed", "succeeded" -> "succeeded"
        - "fail", "failed", "error" -> "failed"
      * Allowed canonical statuses: {"pending", "running", "succeeded", "failed", "skipped"}

    Typical patterns:
      * Move to running with lease:
        new_status="running", lease_token="...", owner_agent_id="...", lease_ttl_s=300, set_started_at=True, attempts_increment=1
      * Mark succeeded and write output:
        new_status="succeeded", lease_token="...", set_finished_at=True, output_json='{"ok": true, ...}'
      * Mark failed with error:
        new_status="failed", lease_token="...", set_finished_at=True, error_message="..."

    Args:
      workflow_id: Workflow UUID.
      state: State name to update.
      redis_url: Optional Redis URL. Defaults to env REDIS_URL or "redis://redis:6379/0".
      new_status: Optional new status.
      lease_token: Optional expected lease token (for ownership).
      owner_agent_id: Optional owner to set on lease when setting/refreshing.
      lease_ttl_s: Optional lease TTL seconds (informational).
      attempts_increment: Optional integer to add to attempts counter.
      error_message: Optional error string to set as last_error.
      set_started_at: If True, set started_at=now (ISO-8601 UTC).
      set_finished_at: If True, set finished_at=now (ISO-8601 UTC).
      output_json: Optional JSON string to write to dp:wf:{workflow_id}:output:{state}.
      output_ttl_secs: Optional TTL for the output key.

    Returns:
      dict: {
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

    r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
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

    # Normalize/validate status (accept common synonyms)
    canonical = None
    if isinstance(new_status, str):
        ns = new_status.strip().lower()
        if ns in ("done", "success", "succeed", "succeeded"):
            canonical = "succeeded"
        elif ns in ("fail", "failed", "error"):
            canonical = "failed"
        elif ns in ("pending", "running", "skipped"):
            canonical = ns
        else:
            return {
                "status": None,
                "error": "Invalid new_status '%s'." % new_status,
                "workflow_id": workflow_id,
                "state": state,
                "updated_state": None,
                "output_written": False
            }

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

        # attempts
        if isinstance(attempts_increment, int) and attempts_increment != 0:
            try:
                next_state["attempts"] = int(next_state.get("attempts", 0)) + int(attempts_increment)
            except Exception:
                next_state["attempts"] = int(attempts_increment)

        # status
        if canonical is not None:
            next_state["status"] = canonical

        # timestamps
        if set_started_at:
            next_state["started_at"] = now_iso
        if set_finished_at:
            next_state["finished_at"] = now_iso

        # error
        if error_message is not None:
            next_state["last_error"] = error_message

        # lease set/refresh
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

        # TX begin
        pipe.multi()
        # JSON.SET (use execute_command for compatibility inside pipeline)
        pipe.execute_command('JSON.SET', state_key, '$', json.dumps(next_state))

        # Optional data-plane output
        if isinstance(output_json, str) and output_json.strip():
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

        pipe.execute()

    except WatchError:
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

    # Read back final state for the caller
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
