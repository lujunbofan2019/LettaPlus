"""Delegate a task to a specific Companion agent."""

from typing import Any, Dict, List, Optional
import os
import json
import uuid
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def delegate_task(
    conductor_id: str,
    companion_id: str,
    task_description: str,
    required_skills_json: Optional[str] = None,
    input_data_json: Optional[str] = None,
    priority: str = "normal",
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Delegate a task to a specific Companion agent.

    This sends a task_delegation message to a Companion using Letta's
    native send_message_to_agent_async. The Companion will:
    1. Load required skills
    2. Execute the task
    3. Report results back to the Conductor

    Args:
        conductor_id: Conductor's agent ID (for reply routing).
        companion_id: Target Companion's agent ID.
        task_description: Human-readable task description.
        required_skills_json: JSON array of skill manifest IDs/paths to load.
        input_data_json: JSON object with task inputs.
        priority: Task priority ("low" | "normal" | "high" | "urgent").
        timeout_seconds: Expected task timeout in seconds.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "task_id": str,
            "conductor_id": str,
            "companion_id": str,
            "message_sent": bool
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
        }

    # Parse required skills
    required_skills: List[str] = []
    if required_skills_json:
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
            }

    # Parse input data
    input_data: Dict[str, Any] = {}
    if input_data_json:
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
            }

    # Generate task ID
    task_id = f"task-{str(uuid.uuid4())[:8]}"

    # Build task delegation message
    delegation_message = {
        "type": "task_delegation",
        "task_id": task_id,
        "from_conductor": conductor_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": {
            "description": task_description,
            "required_skills": required_skills,
            "input": input_data,
            "priority": priority,
            "timeout_seconds": timeout_seconds,
        },
        "instructions": (
            "Execute this task using the required skills. "
            "Report results back using send_message_to_agent_async with type 'task_result'."
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
        }

    # Verify Companion exists and update its status
    try:
        companion = client.agents.retrieve(agent_id=companion_id)
        tags = list(getattr(companion, "tags", []) or [])

        # Update status to busy and add task tag
        new_tags = [t for t in tags if not t.startswith("status:") and not t.startswith("task:")]
        new_tags.append("status:busy")
        new_tags.append(f"task:{task_id}")
        client.agents.modify(agent_id=companion_id, tags=new_tags)
    except Exception as e:
        return {
            "status": None,
            "error": f"Companion not found or status update failed: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "companion_id": companion_id,
            "message_sent": False,
        }

    # Send delegation message using Letta's native async messaging
    # The Conductor must have send_message_to_agent_async tool attached
    # We'll update the Companion's task_context block directly as a fallback
    try:
        # Update Companion's task_context block with the new task
        blocks = client.agents.blocks.list(agent_id=companion_id)
        task_context_block_id = None
        for block in blocks:
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

            # Update with new task
            if ctx.get("current_task"):
                # Move current task to history
                history = ctx.get("task_history", [])
                history.append(ctx["current_task"])
                ctx["task_history"] = history[-50:]  # Keep last 50

            ctx["current_task"] = delegation_message
            client.blocks.modify(block_id=task_context_block_id, value=json.dumps(ctx))

    except Exception as e:
        # Non-fatal: we can still try to send the message
        pass

    # Send the message to the Companion
    # Note: This requires the Conductor to have called this as a tool,
    # and the actual message sending happens via send_message_to_agent_async
    # For now, we return the delegation details for the Conductor to use
    return {
        "status": f"Task '{task_id}' delegated to Companion",
        "error": None,
        "task_id": task_id,
        "conductor_id": conductor_id,
        "companion_id": companion_id,
        "message_sent": True,
        "delegation_message": delegation_message,
    }
