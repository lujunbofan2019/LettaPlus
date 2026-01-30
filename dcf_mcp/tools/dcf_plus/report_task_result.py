"""Report task result from Companion to Conductor."""

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
DELEGATION_LOG_BLOCK_LABEL = "delegation_log"


def report_task_result(
    companion_id: str,
    task_id: str,
    conductor_id: str,
    status: str,
    summary: str,
    output_data_json: Optional[str] = None,
    artifacts_json: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    metrics_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Report task result from Companion to Conductor.

    This tool performs the complete result reporting flow:
    1. Updates Companion's `task_context` with structured result
    2. Updates Companion status back to "idle" (or "error" on failure)
    3. Updates `delegation_log` with completion status and metrics (for Strategist)
    4. Sends structured `task_result` message to Conductor

    This is the Companion's counterpart to `delegate_task`.

    Args:
        companion_id: This Companion's agent ID.
        task_id: The task ID from the delegation message.
        conductor_id: The Conductor's agent ID (from task_delegation.from_conductor).
        status: Result status ("succeeded" | "failed" | "partial").
        summary: Human-readable 1-2 sentence summary of results.
        output_data_json: JSON object with structured output data.
        artifacts_json: JSON array of artifacts [{type, value, note}].
        error_code: Error code if status is "failed" (e.g., "skill_load_error").
        error_message: Error message if status is "failed".
        metrics_json: JSON object with execution metrics {duration_s, tool_calls, etc.}.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "task_id": str,
            "companion_id": str,
            "conductor_id": str,
            "message_sent": bool,
            "delegation_log_updated": bool,
            "run_id": str | None
        }
    """
    # Validate status
    valid_statuses = {"succeeded", "failed", "partial"}
    if status not in valid_statuses:
        return {
            "status": None,
            "error": f"Invalid status '{status}'. Must be one of: {valid_statuses}",
            "task_id": task_id,
            "companion_id": companion_id,
            "conductor_id": conductor_id,
            "message_sent": False,
            "delegation_log_updated": False,
            "run_id": None,
        }

    # Lazy imports
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "task_id": task_id,
            "companion_id": companion_id,
            "conductor_id": conductor_id,
            "message_sent": False,
            "delegation_log_updated": False,
            "run_id": None,
        }

    # Parse output data (handles both string and pre-parsed dict from Letta)
    output_data: Dict[str, Any] = {}
    if output_data_json:
        if isinstance(output_data_json, dict):
            output_data = output_data_json
        elif isinstance(output_data_json, str):
            try:
                parsed = json.loads(output_data_json)
                if isinstance(parsed, dict):
                    output_data = parsed
            except Exception:
                pass

    # Parse artifacts (handles both string and pre-parsed list from Letta)
    artifacts: List[Dict[str, Any]] = []
    if artifacts_json:
        if isinstance(artifacts_json, list):
            artifacts = artifacts_json
        elif isinstance(artifacts_json, str):
            try:
                parsed = json.loads(artifacts_json)
                if isinstance(parsed, list):
                    artifacts = parsed
            except Exception:
                pass

    # Parse metrics (handles both string and pre-parsed dict from Letta)
    metrics: Dict[str, Any] = {}
    if metrics_json:
        if isinstance(metrics_json, dict):
            metrics = metrics_json
        elif isinstance(metrics_json, str):
            try:
                parsed = json.loads(metrics_json)
                if isinstance(parsed, dict):
                    metrics = parsed
            except Exception:
                pass

    now_iso = datetime.now(timezone.utc).isoformat()

    # Build task result message
    result_message: Dict[str, Any] = {
        "type": "task_result",
        "task_id": task_id,
        "status": status,
        "output": {
            "summary": summary,
            "data": output_data,
            "artifacts": artifacts,
        },
        "metrics": metrics,
        "companion_id": companion_id,
        "completed_at": now_iso,
    }

    # Add error info if failed
    if status == "failed":
        result_message["error"] = {
            "code": error_code or "unknown_error",
            "message": error_message or "Task failed without specific error message",
        }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "task_id": task_id,
            "companion_id": companion_id,
            "conductor_id": conductor_id,
            "message_sent": False,
            "delegation_log_updated": False,
            "run_id": None,
        }

    # Calculate duration from task_context if available
    duration_s = metrics.get("duration_s")
    skills_used: List[str] = []

    # Update Companion's task_context with result
    try:
        companion_blocks = client.agents.blocks.list(agent_id=companion_id)
        task_context_block_id = None
        for block in companion_blocks:
            if getattr(block, "label", "") == "task_context":
                task_context_block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                break

        if task_context_block_id:
            # Get current context
            full_block = client.blocks.retrieve(block_id=task_context_block_id)
            value = getattr(full_block, "value", "{}")
            if isinstance(value, str):
                try:
                    ctx = json.loads(value)
                except Exception:
                    ctx = {}
            else:
                ctx = value if isinstance(value, dict) else {}

            # Calculate duration if not provided
            if duration_s is None and ctx.get("task_started_at"):
                try:
                    started = datetime.fromisoformat(ctx["task_started_at"].replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    duration_s = (now - started).total_seconds()
                    result_message["metrics"]["duration_s"] = round(duration_s, 2)
                except Exception:
                    pass

            # Get skills from current task
            current_task = ctx.get("current_task", {})
            if isinstance(current_task, dict):
                skills_used = current_task.get("task", {}).get("required_skills", [])
                result_message["metrics"]["skills_used"] = skills_used

            # Move current task to history with result
            task_history = ctx.get("task_history", [])
            completed_task = {
                "task": current_task,
                "result": result_message,
                "completed_at": now_iso,
            }
            task_history.append(completed_task)
            ctx["task_history"] = task_history[-50:]  # Keep last 50

            # Clear current task
            ctx["current_task"] = None
            ctx["task_started_at"] = None

            try:
                client.blocks.modify(block_id=task_context_block_id, value=json.dumps(ctx))
            except AttributeError:
                client.blocks.update(block_id=task_context_block_id, value=json.dumps(ctx))
    except Exception:
        # Non-fatal: continue
        pass

    # Update Companion status
    new_status = "idle" if status != "failed" else "error"
    try:
        companion = client.agents.retrieve(agent_id=companion_id)
        tags = list(getattr(companion, "tags", []) or [])
        new_tags = [t for t in tags if not t.startswith("status:") and not t.startswith("task:")]
        new_tags.append(f"status:{new_status}")
        try:
            client.agents.update(agent_id=companion_id, tags=new_tags)
        except AttributeError:
            client.agents.modify(agent_id=companion_id, tags=new_tags)
    except Exception:
        # Non-fatal: continue
        pass

    # Update delegation_log on Conductor (for Strategist analysis)
    delegation_log_updated = False
    try:
        conductor_blocks = client.agents.blocks.list(agent_id=conductor_id)
        delegation_log_block_id = None
        for block in conductor_blocks:
            if getattr(block, "label", "") == DELEGATION_LOG_BLOCK_LABEL:
                delegation_log_block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                break

        if delegation_log_block_id:
            # Get current log
            full_block = client.blocks.retrieve(block_id=delegation_log_block_id)
            value = getattr(full_block, "value", "{}")
            if isinstance(value, str):
                try:
                    log_data = json.loads(value)
                except Exception:
                    log_data = {"delegations": []}
            else:
                log_data = value if isinstance(value, dict) else {"delegations": []}

            # Find and update the delegation record
            delegations = log_data.get("delegations", [])
            for delegation in delegations:
                if delegation.get("task_id") == task_id:
                    delegation["status"] = "completed"
                    delegation["completed_at"] = now_iso
                    delegation["result_status"] = status
                    if duration_s is not None:
                        delegation["duration_s"] = round(duration_s, 2)
                    if error_code:
                        delegation["error_code"] = error_code
                    break

            log_data["delegations"] = delegations

            try:
                client.blocks.modify(block_id=delegation_log_block_id, value=json.dumps(log_data))
                delegation_log_updated = True
            except AttributeError:
                client.blocks.update(block_id=delegation_log_block_id, value=json.dumps(log_data))
                delegation_log_updated = True
    except Exception:
        # Non-fatal: continue to send message
        pass

    # Send the result message to the Conductor
    run_id = None
    message_sent = False
    try:
        msg = {
            "role": "system",
            "content": [{"type": "text", "text": json.dumps(result_message)}]
        }
        resp = client.agents.messages.create_async(
            agent_id=conductor_id,
            messages=[msg]
        )
        run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
        message_sent = True
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to send result message to Conductor: {e}",
            "task_id": task_id,
            "companion_id": companion_id,
            "conductor_id": conductor_id,
            "message_sent": False,
            "delegation_log_updated": delegation_log_updated,
            "run_id": None,
        }

    return {
        "status": f"Task '{task_id}' result ({status}) reported to Conductor",
        "error": None,
        "task_id": task_id,
        "companion_id": companion_id,
        "conductor_id": conductor_id,
        "message_sent": message_sent,
        "delegation_log_updated": delegation_log_updated,
        "run_id": run_id,
    }
