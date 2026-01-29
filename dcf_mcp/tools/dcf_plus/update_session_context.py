"""Update shared session context block for DCF+ coordination."""

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def update_session_context(
    session_id: str,
    block_id: str,
    state: Optional[str] = None,
    objective: Optional[str] = None,
    add_active_task: Optional[str] = None,
    complete_task: Optional[str] = None,
    companion_count: Optional[int] = None,
    announcement: Optional[str] = None,
    shared_data_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Update the shared session context block.

    This updates the session context that is shared across all agents in the session.
    Changes are immediately visible to all agents with this block attached.

    Args:
        session_id: Session identifier (for validation).
        block_id: The session context block ID.
        state: New session state ("active" | "paused" | "completing" | "completed").
        objective: Updated session objective.
        add_active_task: Task ID to add to active tasks list.
        complete_task: Task ID to move from active to completed.
        companion_count: Updated companion count.
        announcement: Message to add to announcements (broadcast to all).
        shared_data_json: JSON object to merge into shared_data.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "session_id": str,
            "block_id": str,
            "updated_fields": List[str]
        }
    """
    # Lazy imports
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "session_id": session_id,
            "block_id": block_id,
            "updated_fields": [],
        }

    # Parse shared data if provided
    shared_data_update: Dict[str, Any] = {}
    if shared_data_json:
        try:
            parsed = json.loads(shared_data_json)
            if isinstance(parsed, dict):
                shared_data_update = parsed
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to parse shared_data_json: {e}",
                "session_id": session_id,
                "block_id": block_id,
                "updated_fields": [],
            }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "session_id": session_id,
            "block_id": block_id,
            "updated_fields": [],
        }

    # Retrieve current block state
    try:
        block = client.blocks.retrieve(block_id=block_id)
        current_value = getattr(block, "value", "{}")
        if isinstance(current_value, str):
            context = json.loads(current_value)
        elif isinstance(current_value, dict):
            context = current_value
        else:
            context = {}
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to retrieve session context block: {e}",
            "session_id": session_id,
            "block_id": block_id,
            "updated_fields": [],
        }

    # Validate session ID matches
    if context.get("session_id") != session_id:
        return {
            "status": None,
            "error": f"Session ID mismatch: block has '{context.get('session_id')}', expected '{session_id}'",
            "session_id": session_id,
            "block_id": block_id,
            "updated_fields": [],
        }

    updated_fields: List[str] = []

    # Apply updates
    if state is not None:
        context["state"] = state
        updated_fields.append("state")

    if objective is not None:
        context["objective"] = objective
        updated_fields.append("objective")

    if companion_count is not None:
        context["companion_count"] = companion_count
        updated_fields.append("companion_count")

    if add_active_task:
        active_tasks = context.get("active_tasks", [])
        if add_active_task not in active_tasks:
            active_tasks.append(add_active_task)
            context["active_tasks"] = active_tasks
            updated_fields.append("active_tasks")

    if complete_task:
        active_tasks = context.get("active_tasks", [])
        completed_tasks = context.get("completed_tasks", [])
        if complete_task in active_tasks:
            active_tasks.remove(complete_task)
            completed_tasks.append(complete_task)
            context["active_tasks"] = active_tasks
            context["completed_tasks"] = completed_tasks
            updated_fields.append("active_tasks")
            updated_fields.append("completed_tasks")

    if announcement:
        announcements = context.get("announcements", [])
        announcements.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": announcement,
        })
        # Keep only last 20 announcements
        context["announcements"] = announcements[-20:]
        updated_fields.append("announcements")

    if shared_data_update:
        shared_data = context.get("shared_data", {})
        shared_data.update(shared_data_update)
        context["shared_data"] = shared_data
        updated_fields.append("shared_data")

    # Update timestamp
    context["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Write back to block
    try:
        client.blocks.modify(block_id=block_id, value=json.dumps(context))
    except AttributeError:
        try:
            client.blocks.update(block_id=block_id, value=json.dumps(context))
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to update session context block: {e}",
                "session_id": session_id,
                "block_id": block_id,
                "updated_fields": [],
            }
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to update session context block: {e}",
            "session_id": session_id,
            "block_id": block_id,
            "updated_fields": [],
        }

    return {
        "status": f"Updated session context: {', '.join(updated_fields)}" if updated_fields else "No changes made",
        "error": None,
        "session_id": session_id,
        "block_id": block_id,
        "updated_fields": list(set(updated_fields)),  # Dedupe
    }
