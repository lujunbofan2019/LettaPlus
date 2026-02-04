"""Finalize a DCF+ session and clean up resources."""

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timezone

from tools.common.get_agent_tags import get_agent_tags as _get_agent_tags

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def finalize_session(
    session_id: str,
    session_context_block_id: str,
    delete_companions: bool = True,
    delete_session_block: bool = False,
    preserve_wisdom: bool = True,
) -> Dict[str, Any]:
    """Finalize a DCF+ session and clean up resources.

    This function:
    1. Updates session state to "completed"
    2. Optionally collects wisdom from Companions before deletion
    3. Dismisses all Companions in the session
    4. Optionally deletes the session context block

    Args:
        session_id: Session identifier.
        session_context_block_id: The session context block ID.
        delete_companions: Whether to delete Companion agents (default: True).
        delete_session_block: Whether to delete the session context block (default: False).
        preserve_wisdom: Whether to preserve Companion learnings before deletion (default: True).

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "session_id": str,
            "companions_dismissed": List[str],
            "wisdom_preserved": List[dict],
            "session_block_deleted": bool,
            "warnings": List[str]
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
            "companions_dismissed": [],
            "wisdom_preserved": [],
            "session_block_deleted": False,
            "warnings": [],
        }

    warnings: List[str] = []
    companions_dismissed: List[str] = []
    wisdom_preserved: List[Dict[str, Any]] = []

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "session_id": session_id,
            "companions_dismissed": [],
            "wisdom_preserved": [],
            "session_block_deleted": False,
            "warnings": [],
        }

    # Update session state to completing
    try:
        from .update_session_context import update_session_context
        update_session_context(
            session_id=session_id,
            block_id=session_context_block_id,
            state="completing",
            announcement="Session finalizing - collecting results and cleaning up",
        )
    except Exception as e:
        warnings.append(f"Could not update session state: {e}")

    # Find all Companions in session
    session_tag = f"session:{session_id}"
    role_tag = "role:companion"

    try:
        all_agents = client.agents.list()
        companions = []
        for agent in all_agents:
            agent_id = getattr(agent, "id", None)
            if not agent_id:
                continue
            tags = _get_agent_tags(agent_id)
            if session_tag in tags and role_tag in tags:
                companions.append(agent)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to list agents: {e}",
            "session_id": session_id,
            "companions_dismissed": [],
            "wisdom_preserved": [],
            "session_block_deleted": False,
            "warnings": warnings,
        }

    # Preserve wisdom from each Companion before deletion
    if preserve_wisdom:
        for companion in companions:
            companion_id = getattr(companion, "id", None)
            companion_name = getattr(companion, "name", "unknown")
            if not companion_id:
                continue

            try:
                # Extract specialization from tags
                tags = _get_agent_tags(companion_id)
                specialization = "unknown"
                for tag in tags:
                    if tag.startswith("specialization:"):
                        specialization = tag[15:]
                        break

                # Get task history from task_context block
                blocks = client.agents.blocks.list(agent_id=companion_id)
                task_history = []
                for block in blocks:
                    if getattr(block, "label", "") == "task_context":
                        block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                        if block_id:
                            full_block = client.blocks.retrieve(block_id=block_id)
                            value = getattr(full_block, "value", "{}")
                            if isinstance(value, str):
                                try:
                                    ctx = json.loads(value)
                                    task_history = ctx.get("task_history", [])
                                except Exception:
                                    pass
                        break

                wisdom_preserved.append({
                    "companion_id": companion_id,
                    "companion_name": companion_name,
                    "specialization": specialization,
                    "tasks_completed": len(task_history),
                    "task_history": task_history[-10:],  # Keep last 10 tasks
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                warnings.append(f"Could not preserve wisdom from {companion_name}: {e}")

    # Dismiss Companions
    if delete_companions:
        try:
            from .dismiss_companion import dismiss_companion
            for companion in companions:
                companion_id = getattr(companion, "id", None)
                if not companion_id:
                    continue
                try:
                    result = dismiss_companion(
                        companion_id=companion_id,
                        unload_skills=True,
                        detach_shared_blocks=True,
                    )
                    if result.get("status"):
                        companions_dismissed.append(companion_id)
                    else:
                        warnings.append(f"Failed to dismiss {companion_id}: {result.get('error')}")
                except Exception as e:
                    warnings.append(f"Error dismissing {companion_id}: {e}")
        except ImportError as e:
            # Fallback: delete directly
            warnings.append(f"dismiss_companion not available, using direct delete: {e}")
            for companion in companions:
                companion_id = getattr(companion, "id", None)
                if not companion_id:
                    continue
                try:
                    client.agents.delete(agent_id=companion_id)
                    companions_dismissed.append(companion_id)
                except Exception as e:
                    warnings.append(f"Error deleting {companion_id}: {e}")

    # Update session state to completed
    try:
        from .update_session_context import update_session_context
        update_session_context(
            session_id=session_id,
            block_id=session_context_block_id,
            state="completed",
            companion_count=0,
            announcement=f"Session completed - {len(companions_dismissed)} Companions dismissed",
        )
    except Exception as e:
        warnings.append(f"Could not update final session state: {e}")

    # Delete session block if requested
    session_block_deleted = False
    if delete_session_block:
        try:
            client.blocks.delete(block_id=session_context_block_id)
            session_block_deleted = True
        except Exception as e:
            warnings.append(f"Failed to delete session context block: {e}")

    return {
        "status": f"Session '{session_id}' finalized - {len(companions_dismissed)} Companions dismissed",
        "error": None,
        "session_id": session_id,
        "companions_dismissed": companions_dismissed,
        "wisdom_preserved": wisdom_preserved,
        "session_block_deleted": session_block_deleted,
        "warnings": warnings,
    }
