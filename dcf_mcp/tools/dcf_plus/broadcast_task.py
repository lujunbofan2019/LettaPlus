"""Broadcast a task to all Companions matching criteria."""

from typing import Any, Dict, List, Optional
import os
import json
import uuid
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def broadcast_task(
    conductor_id: str,
    session_id: str,
    task_description: str,
    specialization_filter: Optional[str] = None,
    status_filter: str = "idle",
    required_skills_json: Optional[str] = None,
    input_data_json: Optional[str] = None,
    max_companions: int = 1,
) -> Dict[str, Any]:
    """Broadcast a task to Companions matching the specified criteria.

    This finds Companions in the session matching the filters and delegates
    the task to up to max_companions of them. Useful for:
    - Finding an available Companion for a task
    - Parallel execution across multiple specialists
    - Load balancing when multiple Companions are idle

    Args:
        conductor_id: Conductor's agent ID (for reply routing).
        session_id: Session identifier to filter Companions.
        task_description: Human-readable task description.
        specialization_filter: Only consider Companions with this specialization.
        status_filter: Only consider Companions with this status (default: "idle").
        required_skills_json: JSON array of skill manifest IDs/paths to load.
        input_data_json: JSON object with task inputs.
        max_companions: Maximum number of Companions to delegate to (default: 1).

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "task_id": str,
            "conductor_id": str,
            "session_id": str,
            "companions_assigned": List[str],
            "companions_available": int,
            "delegation_results": List[dict]
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
            "session_id": session_id,
            "companions_assigned": [],
            "companions_available": 0,
            "delegation_results": [],
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
                "session_id": session_id,
                "companions_assigned": [],
                "companions_available": 0,
                "delegation_results": [],
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
                "session_id": session_id,
                "companions_assigned": [],
                "companions_available": 0,
                "delegation_results": [],
            }

    # Generate task ID
    task_id = f"task-{str(uuid.uuid4())[:8]}"

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "session_id": session_id,
            "companions_assigned": [],
            "companions_available": 0,
            "delegation_results": [],
        }

    # Find matching Companions
    session_tag = f"session:{session_id}"
    role_tag = "role:companion"
    status_tag = f"status:{status_filter}" if status_filter else None
    spec_tag = f"specialization:{specialization_filter}" if specialization_filter else None

    try:
        all_agents = client.agents.list()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to list agents: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "session_id": session_id,
            "companions_assigned": [],
            "companions_available": 0,
            "delegation_results": [],
        }

    matching_companions = []
    for agent in all_agents:
        tags = getattr(agent, "tags", []) or []

        # Must have session and role tags
        if session_tag not in tags or role_tag not in tags:
            continue

        # Apply status filter
        if status_tag and status_tag not in tags:
            continue

        # Apply specialization filter
        if spec_tag and spec_tag not in tags:
            continue

        matching_companions.append(agent)

    companions_available = len(matching_companions)

    if not matching_companions:
        return {
            "status": None,
            "error": f"No matching Companions found (session={session_id}, status={status_filter}, specialization={specialization_filter})",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "session_id": session_id,
            "companions_assigned": [],
            "companions_available": 0,
            "delegation_results": [],
        }

    # Delegate to up to max_companions
    companions_to_use = matching_companions[:max_companions]
    companions_assigned: List[str] = []
    delegation_results: List[Dict[str, Any]] = []

    try:
        from .delegate_task import delegate_task
    except ImportError as e:
        return {
            "status": None,
            "error": f"delegate_task not available: {e}",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "session_id": session_id,
            "companions_assigned": [],
            "companions_available": companions_available,
            "delegation_results": [],
        }

    for companion in companions_to_use:
        companion_id = getattr(companion, "id", None)
        if not companion_id:
            continue

        result = delegate_task(
            conductor_id=conductor_id,
            companion_id=companion_id,
            task_description=task_description,
            required_skills_json=required_skills_json,
            input_data_json=input_data_json,
            priority="normal",
            timeout_seconds=300,
        )

        delegation_results.append({
            "companion_id": companion_id,
            "success": result.get("message_sent", False),
            "error": result.get("error"),
        })

        if result.get("message_sent"):
            companions_assigned.append(companion_id)

    if not companions_assigned:
        return {
            "status": None,
            "error": "Failed to delegate to any Companion",
            "task_id": task_id,
            "conductor_id": conductor_id,
            "session_id": session_id,
            "companions_assigned": [],
            "companions_available": companions_available,
            "delegation_results": delegation_results,
        }

    return {
        "status": f"Task '{task_id}' broadcast to {len(companions_assigned)} Companion(s)",
        "error": None,
        "task_id": task_id,
        "conductor_id": conductor_id,
        "session_id": session_id,
        "companions_assigned": companions_assigned,
        "companions_available": companions_available,
        "delegation_results": delegation_results,
    }
