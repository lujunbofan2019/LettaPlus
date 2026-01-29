"""Update a Companion's status and metadata via tags."""

from typing import Any, Dict, List, Optional
import os

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def update_companion_status(
    companion_id: str,
    status: Optional[str] = None,
    specialization: Optional[str] = None,
    current_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a Companion's status tag and optionally other metadata.

    This updates the Companion's tags to reflect its current state.
    Tags are used for filtering and discovery by the Conductor.

    Args:
        companion_id: Companion agent ID.
        status: New status ("idle" | "busy" | "error"). If None, not updated.
        specialization: New specialization. If None, not updated.
        current_task_id: Task ID being worked on (added as tag). Use empty string to clear.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "companion_id": str,
            "updated_tags": List[str],
            "previous_tags": List[str]
        }
    """
    # Lazy imports
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "companion_id": companion_id,
            "updated_tags": [],
            "previous_tags": [],
        }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "companion_id": companion_id,
            "updated_tags": [],
            "previous_tags": [],
        }

    # Retrieve current agent
    try:
        agent = client.agents.retrieve(agent_id=companion_id)
        current_tags = list(getattr(agent, "tags", []) or [])
    except Exception as e:
        return {
            "status": None,
            "error": f"Companion not found: {e}",
            "companion_id": companion_id,
            "updated_tags": [],
            "previous_tags": [],
        }

    previous_tags = list(current_tags)
    new_tags: List[str] = []

    # Process each tag, updating as needed
    for tag in current_tags:
        if tag.startswith("status:") and status is not None:
            # Skip old status tag, we'll add new one
            continue
        elif tag.startswith("specialization:") and specialization is not None:
            # Skip old specialization tag
            continue
        elif tag.startswith("task:") and current_task_id is not None:
            # Skip old task tag
            continue
        else:
            new_tags.append(tag)

    # Add updated tags
    if status is not None:
        new_tags.append(f"status:{status}")
    else:
        # Preserve existing status if not updating
        for tag in current_tags:
            if tag.startswith("status:"):
                new_tags.append(tag)
                break

    if specialization is not None:
        new_tags.append(f"specialization:{specialization}")
    else:
        # Preserve existing specialization if not updating
        for tag in current_tags:
            if tag.startswith("specialization:"):
                new_tags.append(tag)
                break

    if current_task_id is not None and current_task_id:  # Non-empty string
        new_tags.append(f"task:{current_task_id}")
    # If current_task_id is empty string, we've already removed the old task tag

    # Update the agent
    try:
        # The Letta API may require modifying agent settings
        # We use the modify endpoint if available
        client.agents.modify(agent_id=companion_id, tags=new_tags)
    except AttributeError:
        # Some SDK versions use update instead
        try:
            client.agents.update(agent_id=companion_id, tags=new_tags)
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to update agent tags: {e}",
                "companion_id": companion_id,
                "updated_tags": [],
                "previous_tags": previous_tags,
            }
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to update agent tags: {e}",
            "companion_id": companion_id,
            "updated_tags": [],
            "previous_tags": previous_tags,
        }

    changes = []
    if status is not None:
        changes.append(f"status={status}")
    if specialization is not None:
        changes.append(f"specialization={specialization}")
    if current_task_id is not None:
        changes.append(f"task={current_task_id or 'cleared'}")

    return {
        "status": f"Updated Companion: {', '.join(changes)}" if changes else "No changes made",
        "error": None,
        "companion_id": companion_id,
        "updated_tags": new_tags,
        "previous_tags": previous_tags,
    }
