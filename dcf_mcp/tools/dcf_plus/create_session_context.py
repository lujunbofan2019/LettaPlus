"""Create shared session context block for DCF+ coordination."""

from typing import Any, Dict, List, Optional
import os
import json
import uuid
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def create_session_context(
    session_id: str,
    conductor_id: str,
    objective: Optional[str] = None,
    initial_context_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a shared session context block for cross-agent coordination.

    The session context block is a shared memory block that can be attached
    to multiple agents (Conductor and Companions) for real-time coordination.
    All agents see the same block contents, enabling shared state.

    Args:
        session_id: Unique session identifier.
        conductor_id: Conductor agent ID (will be attached to this block).
        objective: Optional high-level session objective.
        initial_context_json: Optional JSON object with initial context data.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "session_id": str,
            "block_id": str | None,
            "block_label": str
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
            "block_id": None,
            "block_label": "",
        }

    # Parse initial context
    initial_context: Dict[str, Any] = {}
    if initial_context_json:
        try:
            parsed = json.loads(initial_context_json)
            if isinstance(parsed, dict):
                initial_context = parsed
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to parse initial_context_json: {e}",
                "session_id": session_id,
                "block_id": None,
                "block_label": "",
            }

    # Build session context structure
    session_context = {
        "session_id": session_id,
        "conductor_id": conductor_id,
        "objective": objective,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "state": "active",
        "companion_count": 0,
        "active_tasks": [],
        "completed_tasks": [],
        "shared_data": initial_context,
        "announcements": [],
    }

    block_label = f"session_context:{session_id}"

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "session_id": session_id,
            "block_id": None,
            "block_label": block_label,
        }

    # Create the shared block
    try:
        block = client.blocks.create(
            label=block_label,
            value=json.dumps(session_context),
            limit=16000,  # Large limit for session-wide context
        )
        block_id = getattr(block, "id", None)

        if not block_id:
            return {
                "status": None,
                "error": "Block created but no ID returned",
                "session_id": session_id,
                "block_id": None,
                "block_label": block_label,
            }

    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to create session context block: {e}",
            "session_id": session_id,
            "block_id": None,
            "block_label": block_label,
        }

    # Attach block to Conductor
    try:
        client.agents.blocks.attach(agent_id=conductor_id, block_id=block_id)
    except Exception as e:
        # Non-fatal: block exists but couldn't attach
        return {
            "status": f"Created session context but failed to attach to Conductor: {e}",
            "error": None,
            "session_id": session_id,
            "block_id": block_id,
            "block_label": block_label,
        }

    return {
        "status": f"Created session context for session '{session_id}'",
        "error": None,
        "session_id": session_id,
        "block_id": block_id,
        "block_label": block_label,
    }
