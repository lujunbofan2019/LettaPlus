"""List all Companion agents in a session with their current state."""

from typing import Any, Dict, List, Optional
import os
import json

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
SKILL_STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")


def list_session_companions(
    session_id: str,
    include_status: bool = True,
    specialization_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """List all Companion agents in a session with their current state.

    Args:
        session_id: Session identifier to filter by.
        include_status: Include detailed status info for each Companion (default: True).
        specialization_filter: Optional filter by specialization (e.g., "research", "analysis").

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "session_id": str,
            "companions": [
                {
                    "companion_id": str,
                    "companion_name": str,
                    "specialization": str,
                    "status": str,  # "idle" | "busy" | "error"
                    "conductor_id": str | None,
                    "loaded_skills": List[str],
                    "tags": List[str]
                }
            ],
            "count": int
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
            "companions": [],
            "count": 0,
        }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "session_id": session_id,
            "companions": [],
            "count": 0,
        }

    # List all agents and filter by session tag
    try:
        all_agents = client.agents.list()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to list agents: {e}",
            "session_id": session_id,
            "companions": [],
            "count": 0,
        }

    session_tag = f"session:{session_id}"
    role_tag = "role:companion"

    companions: List[Dict[str, Any]] = []

    for agent in all_agents:
        tags = getattr(agent, "tags", []) or []

        # Must have both session and role tags
        if session_tag not in tags or role_tag not in tags:
            continue

        agent_id = getattr(agent, "id", None)
        agent_name = getattr(agent, "name", None)

        if not agent_id:
            continue

        # Extract metadata from tags
        specialization = "unknown"
        status = "unknown"
        conductor_id = None

        for tag in tags:
            if tag.startswith("specialization:"):
                specialization = tag[15:]
            elif tag.startswith("status:"):
                status = tag[7:]
            elif tag.startswith("conductor:"):
                conductor_id = tag[10:]

        # Apply specialization filter if specified
        if specialization_filter and specialization != specialization_filter:
            continue

        companion_info: Dict[str, Any] = {
            "companion_id": agent_id,
            "companion_name": agent_name,
            "specialization": specialization,
            "status": status,
            "conductor_id": conductor_id,
            "loaded_skills": [],
            "tags": tags,
        }

        # Optionally get detailed status including loaded skills
        if include_status:
            try:
                blocks = client.agents.blocks.list(agent_id=agent_id)
                for block in blocks:
                    if getattr(block, "label", "") == SKILL_STATE_BLOCK_LABEL:
                        block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                        if block_id:
                            full_block = client.blocks.retrieve(block_id=block_id)
                            value = getattr(full_block, "value", "{}")
                            if isinstance(value, str):
                                try:
                                    state = json.loads(value)
                                    companion_info["loaded_skills"] = list(state.keys())
                                except Exception:
                                    pass
                            elif isinstance(value, dict):
                                companion_info["loaded_skills"] = list(value.keys())
                        break
            except Exception:
                # Non-fatal: continue without skill info
                pass

        companions.append(companion_info)

    return {
        "status": f"Found {len(companions)} Companion(s) in session '{session_id}'",
        "error": None,
        "session_id": session_id,
        "companions": companions,
        "count": len(companions),
    }
