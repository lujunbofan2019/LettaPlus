"""Delegate a task to a specific Companion agent."""

from typing import Any, Dict, List, Optional
import os
import json
import uuid
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
DELEGATION_LOG_BLOCK_LABEL = "delegation_log"


def delegate_task(
    conductor_id: str,
    companion_id: str,
    task_description: str,
    required_skills_json: Optional[str] = None,
    input_data_json: Optional[str] = None,
    priority: str = "normal",
    timeout_seconds: int = 300,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Delegate a task to a specific Companion agent.

    This tool performs the complete delegation flow:
    1. Validates the Companion exists and is available
    2. Updates Companion status to "busy"
    3. Records the delegation in the `delegation_log` block (for Strategist)
    4. Updates Companion's `task_context` block with the task
    5. Sends a `task_delegation` message to the Companion via Letta messaging

    The Companion will then:
    1. Load required skills
    2. Execute the task
    3. Report results back using `report_task_result`

    Args:
        conductor_id: Conductor's agent ID (for reply routing).
        companion_id: Target Companion's agent ID.
        task_description: Human-readable task description.
        required_skills_json: JSON array of skill manifest IDs/paths to load.
        input_data_json: JSON object with task inputs.
        priority: Task priority ("low" | "normal" | "high" | "urgent").
        timeout_seconds: Expected task timeout in seconds.
        session_id: Optional session ID for tracking (used if delegation_log lookup needed).

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "task_id": str,
            "conductor_id": str,
            "companion_id": str,
            "message_sent": bool,
            "delegation_logged": bool,
            "run_id": str | None
        }
    """
    # Lazy imports
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "task_id": None,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
            "delegation_logged": False,
            "run_id": None,
        }

    # Parse required skills (handles both string and pre-parsed list from Letta)
    required_skills: List[str] = []
    if required_skills_json:
        if isinstance(required_skills_json, list):
            # Already parsed by Letta
            required_skills = [str(s) for s in required_skills_json if s]
        elif isinstance(required_skills_json, str):
            try:
                parsed = json.loads(required_skills_json)
                if isinstance(parsed, list):
                    required_skills = [str(s) for s in parsed if s]
            except Exception as e:
                return {
                    "status": None,
                    "error": f"Failed to parse required_skills_json: {e}",
                    "task_id": None,
                    "conductor_id": conductor_id,
                    "companion_id": companion_id,
                    "message_sent": False,
                    "delegation_logged": False,
                    "run_id": None,
                }

    # Parse input data (handles both string and pre-parsed dict from Letta)
    input_data: Dict[str, Any] = {}
    if input_data_json:
        if isinstance(input_data_json, dict):
            # Already parsed by Letta
            input_data = input_data_json
        elif isinstance(input_data_json, str):
            try:
                parsed = json.loads(input_data_json)
                if isinstance(parsed, dict):
                    input_data = parsed
            except Exception as e:
                return {
                    "status": None,
                    "error": f"Failed to parse input_data_json: {e}",
                    "task_id": None,
                    "conductor_id": conductor_id,
                    "companion_id": companion_id,
                    "message_sent": False,
                    "delegation_logged": False,
                    "run_id": None,
                }

    # Generate task ID
    task_id = f"task-{str(uuid.uuid4())[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Build task delegation message
    delegation_message = {
        "type": "task_delegation",
        "task_id": task_id,
        "from_conductor": conductor_id,
        "timestamp": now_iso,
        "task": {
            "description": task_description,
            "required_skills": required_skills,
            "input": input_data,
            "priority": priority,
            "timeout_seconds": timeout_seconds,
        },
        "instructions": (
            "Execute this task using the required skills. "
            "Report results back using report_task_result tool."
        ),
    }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
            "delegation_logged": False,
            "run_id": None,
        }

    # Verify Companion exists and get its tags
    try:
        companion = client.agents.retrieve(agent_id=companion_id)
        tags = list(getattr(companion, "tags", []) or [])
    except Exception as e:
        return {
            "status": None,
            "error": f"Companion not found: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
            "delegation_logged": False,
            "run_id": None,
        }

    # Check if Companion is already busy
    current_status = "idle"
    for tag in tags:
        if tag.startswith("status:"):
            current_status = tag[7:]
            break

    if current_status == "busy":
        return {
            "status": None,
            "error": f"Companion is busy (status: {current_status}). Wait or use a different Companion.",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
            "delegation_logged": False,
            "run_id": None,
        }

    # Update Companion status to busy
    try:
        new_tags = [t for t in tags if not t.startswith("status:") and not t.startswith("task:")]
        new_tags.append("status:busy")
        new_tags.append(f"task:{task_id}")
        try:
            client.agents.update(agent_id=companion_id, tags=new_tags)
        except AttributeError:
            client.agents.modify(agent_id=companion_id, tags=new_tags)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to update Companion status: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
            "delegation_logged": False,
            "run_id": None,
        }

    delegation_logged = False

    # Record delegation in delegation_log block (for Strategist analysis)
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

            # Create delegation record
            delegation_record = {
                "task_id": task_id,
                "companion_id": companion_id,
                "companion_name": getattr(companion, "name", "unknown"),
                "skills_assigned": required_skills,
                "task_description": task_description[:200],  # Truncate for storage
                "priority": priority,
                "timeout_seconds": timeout_seconds,
                "status": "pending",
                "delegated_at": now_iso,
                "completed_at": None,
                "duration_s": None,
                "result_status": None,
            }

            # Append to delegations list
            delegations = log_data.get("delegations", [])
            delegations.append(delegation_record)
            # Keep last 100 delegations
            log_data["delegations"] = delegations[-100:]
            log_data["last_delegation_at"] = now_iso

            # Update session_id if provided
            if session_id:
                log_data["session_id"] = session_id

            try:
                client.blocks.modify(block_id=delegation_log_block_id, value=json.dumps(log_data))
                delegation_logged = True
            except AttributeError:
                client.blocks.update(block_id=delegation_log_block_id, value=json.dumps(log_data))
                delegation_logged = True
    except Exception:
        # Non-fatal: continue without logging
        pass

    # Update Companion's task_context block with the new task
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

            # Update with new task (don't move incomplete task to history)
            ctx["current_task"] = delegation_message
            ctx["task_started_at"] = now_iso

            try:
                client.blocks.modify(block_id=task_context_block_id, value=json.dumps(ctx))
            except AttributeError:
                client.blocks.update(block_id=task_context_block_id, value=json.dumps(ctx))
    except Exception:
        # Non-fatal: continue to send message
        pass

    # Send the message to the Companion via Letta's async messaging
    run_id = None
    message_sent = False
    try:
        msg = {
            "role": "system",
            "content": [{"type": "text", "text": json.dumps(delegation_message)}]
        }
        resp = client.agents.messages.create_async(
            agent_id=companion_id,
            messages=[msg]
        )
        run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
        message_sent = True
    except Exception as e:
        # Revert Companion status on failure
        try:
            revert_tags = [t for t in new_tags if not t.startswith("status:") and not t.startswith("task:")]
            revert_tags.append("status:idle")
            try:
                client.agents.update(agent_id=companion_id, tags=revert_tags)
            except AttributeError:
                client.agents.modify(agent_id=companion_id, tags=revert_tags)
        except Exception:
            pass

        return {
            "status": None,
            "error": f"Failed to send delegation message: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
            "delegation_logged": delegation_logged,
            "run_id": None,
        }

    return {
        "status": f"Task '{task_id}' delegated to Companion '{getattr(companion, 'name', companion_id)}'",
        "error": None,
        "task_id": task_id,
        "conductor_id": conductor_id,
        "companion_id": companion_id,
        "message_sent": message_sent,
        "delegation_logged": delegation_logged,
        "run_id": run_id,
    }
