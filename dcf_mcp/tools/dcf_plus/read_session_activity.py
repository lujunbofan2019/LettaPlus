"""Read session activity for Strategist analysis."""

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def read_session_activity(
    session_id: str,
    session_context_block_id: Optional[str] = None,
    include_companion_details: bool = True,
    include_task_history: bool = True,
) -> Dict[str, Any]:
    """Read session activity for Strategist analysis and pattern recognition.

    This provides the Strategist with a comprehensive view of session activity:
    - Session state and context
    - Companion status and task history
    - Skill usage patterns
    - Performance metrics

    Args:
        session_id: Session identifier.
        session_context_block_id: Optional block ID (if known, avoids lookup).
        include_companion_details: Include detailed Companion information.
        include_task_history: Include task history from Companions.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "session_id": str,
            "session_state": str,
            "session_context": dict,
            "companions": List[dict],
            "skill_usage": dict,
            "metrics": dict
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
            "session_state": "unknown",
            "session_context": {},
            "companions": [],
            "skill_usage": {},
            "metrics": {},
        }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "session_id": session_id,
            "session_state": "unknown",
            "session_context": {},
            "companions": [],
            "skill_usage": {},
            "metrics": {},
        }

    session_context: Dict[str, Any] = {}
    session_state = "unknown"

    # Get session context
    if session_context_block_id:
        try:
            block = client.blocks.retrieve(block_id=session_context_block_id)
            value = getattr(block, "value", "{}")
            if isinstance(value, str):
                session_context = json.loads(value)
            elif isinstance(value, dict):
                session_context = value
            session_state = session_context.get("state", "unknown")
        except Exception:
            pass
    else:
        # Try to find session context block by label
        try:
            blocks = client.blocks.list()
            target_label = f"session_context:{session_id}"
            for block in blocks:
                if getattr(block, "label", "") == target_label:
                    block_id = getattr(block, "id", None)
                    if block_id:
                        full_block = client.blocks.retrieve(block_id=block_id)
                        value = getattr(full_block, "value", "{}")
                        if isinstance(value, str):
                            session_context = json.loads(value)
                        elif isinstance(value, dict):
                            session_context = value
                        session_state = session_context.get("state", "unknown")
                    break
        except Exception:
            pass

    # Find Companions in session
    session_tag = f"session:{session_id}"
    role_tag = "role:companion"
    companions: List[Dict[str, Any]] = []
    skill_usage: Dict[str, int] = {}
    total_tasks = 0
    completed_tasks = 0
    failed_tasks = 0

    try:
        all_agents = client.agents.list()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to list agents: {e}",
            "session_id": session_id,
            "session_state": session_state,
            "session_context": session_context,
            "companions": [],
            "skill_usage": {},
            "metrics": {},
        }

    for agent in all_agents:
        tags = getattr(agent, "tags", []) or []
        if session_tag not in tags or role_tag not in tags:
            continue

        companion_id = getattr(agent, "id", None)
        companion_name = getattr(agent, "name", "unknown")
        if not companion_id:
            continue

        # Extract metadata from tags
        specialization = "unknown"
        status = "unknown"
        current_task = None

        for tag in tags:
            if tag.startswith("specialization:"):
                specialization = tag[15:]
            elif tag.startswith("status:"):
                status = tag[7:]
            elif tag.startswith("task:"):
                current_task = tag[5:]

        companion_info: Dict[str, Any] = {
            "companion_id": companion_id,
            "companion_name": companion_name,
            "specialization": specialization,
            "status": status,
            "current_task": current_task,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "skills_used": [],
            "task_history": [],
        }

        # Get detailed information if requested
        if include_companion_details or include_task_history:
            try:
                blocks = client.agents.blocks.list(agent_id=companion_id)
                for block in blocks:
                    label = getattr(block, "label", "")

                    # Get task context for history
                    if label == "task_context" and include_task_history:
                        block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                        if block_id:
                            full_block = client.blocks.retrieve(block_id=block_id)
                            value = getattr(full_block, "value", "{}")
                            if isinstance(value, str):
                                try:
                                    ctx = json.loads(value)
                                    task_history = ctx.get("task_history", [])
                                    companion_info["task_history"] = task_history[-20:]  # Last 20

                                    # Count completed/failed
                                    for task in task_history:
                                        total_tasks += 1
                                        if isinstance(task, dict):
                                            task_status = task.get("result", {}).get("status", "")
                                            if task_status == "succeeded":
                                                completed_tasks += 1
                                                companion_info["tasks_completed"] += 1
                                            elif task_status == "failed":
                                                failed_tasks += 1
                                                companion_info["tasks_failed"] += 1

                                            # Track skill usage
                                            skills = task.get("task", {}).get("required_skills", [])
                                            for skill in skills:
                                                skill_usage[skill] = skill_usage.get(skill, 0) + 1
                                                if skill not in companion_info["skills_used"]:
                                                    companion_info["skills_used"].append(skill)
                                except Exception:
                                    pass

                    # Get currently loaded skills
                    elif label == "dcf_active_skills" and include_companion_details:
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
            except Exception:
                pass

        companions.append(companion_info)

    # Calculate metrics
    metrics = {
        "companion_count": len(companions),
        "idle_companions": sum(1 for c in companions if c.get("status") == "idle"),
        "busy_companions": sum(1 for c in companions if c.get("status") == "busy"),
        "total_tasks_tracked": total_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "success_rate": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        "unique_skills_used": len(skill_usage),
        "most_used_skills": sorted(skill_usage.items(), key=lambda x: x[1], reverse=True)[:5],
    }

    return {
        "status": f"Activity report for session '{session_id}'",
        "error": None,
        "session_id": session_id,
        "session_state": session_state,
        "session_context": session_context,
        "companions": companions,
        "skill_usage": skill_usage,
        "metrics": metrics,
    }
