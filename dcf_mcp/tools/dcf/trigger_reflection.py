from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def trigger_reflection(
    workflow_id: str,
    planner_agent_id: str,
    final_status: str = None,
    execution_summary_json: str = None,
    redis_url: str = None,
    async_message: bool = True,
    max_steps: int = None
) -> Dict[str, Any]:
    """Trigger the Reflector agent to analyze a completed workflow.

    This tool should be called after workflow finalization to initiate
    the reflection process. It sends a `reflection_event` to the Reflector
    agent registered with the given Planner.

    The reflection event contains:
    - Workflow identification and final status
    - Execution summary (states, durations, outcomes)
    - References to the Planner for memory access

    Args:
        workflow_id: The completed workflow's UUID.
        planner_agent_id: The Planner agent's UUID (to find its registered Reflector).
        final_status: The workflow's final status (succeeded/failed/partial/cancelled).
                     If not provided, will be read from control plane.
        execution_summary_json: Optional JSON string with additional execution details.
        redis_url: Redis URL for reading control plane. Defaults to REDIS_URL env.
        async_message: If True, send asynchronously (default). If False, wait for response.
        max_steps: Optional max_steps hint for the Reflector's processing.

    Returns:
        dict: {
            "status": str or None,
            "error": str or None,
            "workflow_id": str,
            "planner_agent_id": str,
            "reflector_agent_id": str or None,
            "message_sent": bool,
            "run_id": str or None (if async)
        }
    """
    # Lazy imports
    try:
        import redis as redis_lib
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: redis not importable: {e}",
            "workflow_id": workflow_id,
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": None,
            "message_sent": False,
            "run_id": None
        }

    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "workflow_id": workflow_id,
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": None,
            "message_sent": False,
            "run_id": None
        }

    try:
        client = Letta(base_url=LETTA_BASE_URL)

        # Find registered Reflector
        planner_blocks = client.agents.blocks.list(agent_id=planner_agent_id)
        reflector_agent_id = None

        for block in planner_blocks:
            if getattr(block, "label", "") == "reflector_registration":
                block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                if block_id:
                    full_block = client.blocks.retrieve(block_id=block_id)
                    value = getattr(full_block, "value", "{}")
                    try:
                        reg_data = json.loads(value) if isinstance(value, str) else value
                        reflector_agent_id = reg_data.get("reflector_agent_id")
                    except Exception:
                        pass
                break

        if not reflector_agent_id:
            return {
                "status": None,
                "error": f"No Reflector registered with Planner '{planner_agent_id}'",
                "workflow_id": workflow_id,
                "planner_agent_id": planner_agent_id,
                "reflector_agent_id": None,
                "message_sent": False,
                "run_id": None
            }

        # Verify Reflector exists
        try:
            client.agents.retrieve(reflector_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Registered Reflector '{reflector_agent_id}' not found: {e}",
                "workflow_id": workflow_id,
                "planner_agent_id": planner_agent_id,
                "reflector_agent_id": reflector_agent_id,
                "message_sent": False,
                "run_id": None
            }

        # Read workflow status from control plane if not provided
        workflow_name = None
        summary = None

        if not final_status or not execution_summary_json:
            r_url = redis_url or os.getenv("REDIS_URL") or "redis://redis:6379/0"
            try:
                r = redis_lib.Redis.from_url(r_url, decode_responses=True)
                if hasattr(r, "json"):
                    # Read meta
                    meta_key = f"cp:wf:{workflow_id}:meta"
                    meta = r.json().get(meta_key, "$")
                    if isinstance(meta, list) and len(meta) == 1:
                        meta = meta[0]
                    if isinstance(meta, dict):
                        workflow_name = meta.get("workflow_name")
                        if not final_status:
                            final_status = meta.get("status", "unknown")

                        # Compute summary from states
                        states = meta.get("states", [])
                        counts = {"total": len(states), "succeeded": 0, "failed": 0, "cancelled": 0, "pending": 0, "running": 0}
                        for state_name in states:
                            state_key = f"cp:wf:{workflow_id}:state:{state_name}"
                            try:
                                state_doc = r.json().get(state_key, "$")
                                if isinstance(state_doc, list) and len(state_doc) == 1:
                                    state_doc = state_doc[0]
                                if isinstance(state_doc, dict):
                                    st = state_doc.get("status", "pending")
                                    if st in ("succeeded", "done"):
                                        counts["succeeded"] += 1
                                    elif st == "failed":
                                        counts["failed"] += 1
                                    elif st == "cancelled":
                                        counts["cancelled"] += 1
                                    elif st == "running":
                                        counts["running"] += 1
                                    else:
                                        counts["pending"] += 1
                            except Exception:
                                counts["pending"] += 1

                        summary = counts
            except Exception:
                # Non-fatal; continue with what we have
                pass

        # Parse execution summary if provided
        if execution_summary_json:
            try:
                summary = json.loads(execution_summary_json)
            except Exception:
                pass

        # Build reflection event
        now_iso = datetime.now(timezone.utc).isoformat()
        reflection_event = {
            "type": "reflection_event",
            "workflow_id": workflow_id,
            "workflow_name": workflow_name or "unknown",
            "final_status": final_status or "unknown",
            "planner_agent_id": planner_agent_id,
            "summary": summary or {},
            "finalized_at": now_iso,
            "control_plane": {
                "meta_key": f"cp:wf:{workflow_id}:meta",
            }
        }

        # Send message to Reflector
        msg = {"role": "system", "content": [{"type": "text", "text": json.dumps(reflection_event)}]}
        req = {"messages": [msg]}
        if isinstance(max_steps, int):
            req["max_steps"] = max_steps

        try:
            if async_message:
                resp = client.agents.messages.create_async(agent_id=reflector_agent_id, **req)
                run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
                return {
                    "status": f"Reflection triggered for workflow '{workflow_id}' (async)",
                    "error": None,
                    "workflow_id": workflow_id,
                    "planner_agent_id": planner_agent_id,
                    "reflector_agent_id": reflector_agent_id,
                    "message_sent": True,
                    "run_id": run_id
                }
            else:
                resp = client.agents.messages.create(agent_id=reflector_agent_id, **req)
                return {
                    "status": f"Reflection completed for workflow '{workflow_id}'",
                    "error": None,
                    "workflow_id": workflow_id,
                    "planner_agent_id": planner_agent_id,
                    "reflector_agent_id": reflector_agent_id,
                    "message_sent": True,
                    "run_id": None
                }
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to send reflection event: {e.__class__.__name__}: {e}",
                "workflow_id": workflow_id,
                "planner_agent_id": planner_agent_id,
                "reflector_agent_id": reflector_agent_id,
                "message_sent": False,
                "run_id": None
            }

    except Exception as e:
        return {
            "status": None,
            "error": f"Trigger failed: {e.__class__.__name__}: {e}",
            "workflow_id": workflow_id,
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": None,
            "message_sent": False,
            "run_id": None
        }
