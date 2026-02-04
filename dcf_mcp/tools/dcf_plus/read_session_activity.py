"""Read session activity for Strategist analysis."""

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timezone

from tools.common.get_agent_tags import get_agent_tags as _get_agent_tags

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
DELEGATION_LOG_BLOCK_LABEL = "delegation_log"


def read_session_activity(
    session_id: str,
    conductor_id: Optional[str] = None,
    session_context_block_id: Optional[str] = None,
    include_companion_details: bool = True,
    include_task_history: bool = True,
    include_skill_metrics: bool = True,
) -> Dict[str, Any]:
    """Read session activity for Strategist analysis and pattern recognition.

    This provides the Strategist with a comprehensive view of session activity:
    - Session state and context
    - Delegation log with task outcomes (from delegation_log block)
    - Companion status and task history
    - Skill usage patterns with success/failure rates
    - Performance metrics

    Args:
        session_id: Session identifier.
        conductor_id: Optional Conductor ID (to read delegation_log directly).
        session_context_block_id: Optional block ID (if known, avoids lookup).
        include_companion_details: Include detailed Companion information.
        include_task_history: Include task history from Companions.
        include_skill_metrics: Calculate skill success rates and metrics.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "session_id": str,
            "session_state": str,
            "session_context": dict,
            "delegations": List[dict],
            "companions": List[dict],
            "skill_metrics": dict,
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
            "delegations": [],
            "companions": [],
            "skill_metrics": {},
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
            "delegations": [],
            "companions": [],
            "skill_metrics": {},
            "metrics": {},
        }

    session_context: Dict[str, Any] = {}
    session_state = "unknown"
    found_conductor_id = conductor_id

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
            if not found_conductor_id:
                found_conductor_id = session_context.get("conductor_id")
        except Exception:
            pass
    else:
        # Try to find session context block by searching blocks
        try:
            blocks = client.blocks.list()
            for block in blocks:
                label = getattr(block, "label", "")
                # Match session_context or session_context:{session_id}
                if label == "session_context" or label == f"session_context:{session_id}":
                    block_id = getattr(block, "id", None)
                    if block_id:
                        full_block = client.blocks.retrieve(block_id=block_id)
                        value = getattr(full_block, "value", "{}")
                        if isinstance(value, str):
                            try:
                                ctx = json.loads(value)
                            except Exception:
                                continue
                        elif isinstance(value, dict):
                            ctx = value
                        else:
                            continue
                        # Verify session_id matches
                        if ctx.get("session_id") == session_id:
                            session_context = ctx
                            session_state = ctx.get("state", "unknown")
                            if not found_conductor_id:
                                found_conductor_id = ctx.get("conductor_id")
                            break
        except Exception:
            pass

    # Read delegation_log from Conductor (primary source of truth)
    delegations: List[Dict[str, Any]] = []
    if found_conductor_id:
        try:
            conductor_blocks = client.agents.blocks.list(agent_id=found_conductor_id)
            for block in conductor_blocks:
                if getattr(block, "label", "") == DELEGATION_LOG_BLOCK_LABEL:
                    block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                    if block_id:
                        full_block = client.blocks.retrieve(block_id=block_id)
                        value = getattr(full_block, "value", "{}")
                        if isinstance(value, str):
                            try:
                                log_data = json.loads(value)
                                delegations = log_data.get("delegations", [])
                            except Exception:
                                pass
                        elif isinstance(value, dict):
                            delegations = value.get("delegations", [])
                    break
        except Exception:
            pass

    # Calculate skill metrics from delegation log
    skill_metrics: Dict[str, Dict[str, Any]] = {}
    total_tasks = 0
    completed_tasks = 0
    failed_tasks = 0
    pending_tasks = 0
    total_duration = 0.0
    tasks_with_duration = 0

    if include_skill_metrics:
        for delegation in delegations:
            total_tasks += 1
            status = delegation.get("status", "pending")
            result_status = delegation.get("result_status")
            duration_s = delegation.get("duration_s")
            skills_assigned = delegation.get("skills_assigned", [])

            if status == "completed":
                if result_status == "succeeded":
                    completed_tasks += 1
                elif result_status == "failed":
                    failed_tasks += 1
                else:
                    completed_tasks += 1  # partial counts as completed

                if duration_s is not None:
                    total_duration += duration_s
                    tasks_with_duration += 1
            else:
                pending_tasks += 1

            # Track per-skill metrics
            for skill in skills_assigned:
                if skill not in skill_metrics:
                    skill_metrics[skill] = {
                        "usage_count": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "pending_count": 0,
                        "total_duration_s": 0.0,
                        "tasks_with_duration": 0,
                        "avg_duration_s": None,
                        "success_rate": None,
                        "failure_modes": [],
                    }

                skill_metrics[skill]["usage_count"] += 1

                if status == "completed":
                    if result_status == "succeeded":
                        skill_metrics[skill]["success_count"] += 1
                    elif result_status == "failed":
                        skill_metrics[skill]["failure_count"] += 1
                        # Track failure mode
                        error_code = delegation.get("error_code")
                        if error_code:
                            modes = skill_metrics[skill]["failure_modes"]
                            found = False
                            for mode in modes:
                                if mode["mode"] == error_code:
                                    mode["count"] += 1
                                    found = True
                                    break
                            if not found:
                                modes.append({"mode": error_code, "count": 1})
                    else:
                        skill_metrics[skill]["success_count"] += 1  # partial

                    if duration_s is not None:
                        skill_metrics[skill]["total_duration_s"] += duration_s
                        skill_metrics[skill]["tasks_with_duration"] += 1
                else:
                    skill_metrics[skill]["pending_count"] += 1

        # Calculate averages and rates
        for skill, metrics_data in skill_metrics.items():
            usage = metrics_data["usage_count"]
            successes = metrics_data["success_count"]
            failures = metrics_data["failure_count"]
            completed = successes + failures

            if completed > 0:
                metrics_data["success_rate"] = round(successes / completed * 100, 1)

            if metrics_data["tasks_with_duration"] > 0:
                metrics_data["avg_duration_s"] = round(
                    metrics_data["total_duration_s"] / metrics_data["tasks_with_duration"], 2
                )

            # Clean up internal tracking fields
            del metrics_data["total_duration_s"]
            del metrics_data["tasks_with_duration"]

    # Find Companions in session
    session_tag = f"session:{session_id}"
    role_tag = "role:companion"
    companions: List[Dict[str, Any]] = []

    try:
        all_agents = client.agents.list()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to list agents: {e}",
            "session_id": session_id,
            "session_state": session_state,
            "session_context": session_context,
            "delegations": delegations,
            "companions": [],
            "skill_metrics": skill_metrics,
            "metrics": {},
        }

    for agent in all_agents:
        companion_id = getattr(agent, "id", None)
        companion_name = getattr(agent, "name", "unknown")
        if not companion_id:
            continue

        tags = _get_agent_tags(companion_id)
        if session_tag not in tags or role_tag not in tags:
            continue

        # Extract metadata from tags
        specialization = "generalist"
        status = "unknown"
        current_task = None

        for tag in tags:
            if tag.startswith("specialization:"):
                specialization = tag[15:]
            elif tag.startswith("status:"):
                status = tag[7:]
            elif tag.startswith("task:"):
                current_task = tag[5:]

        # Count tasks for this Companion from delegation log
        companion_tasks_completed = 0
        companion_tasks_failed = 0
        companion_skills_used: List[str] = []

        for delegation in delegations:
            if delegation.get("companion_id") == companion_id:
                if delegation.get("status") == "completed":
                    if delegation.get("result_status") == "succeeded":
                        companion_tasks_completed += 1
                    elif delegation.get("result_status") == "failed":
                        companion_tasks_failed += 1
                    else:
                        companion_tasks_completed += 1
                for skill in delegation.get("skills_assigned", []):
                    if skill not in companion_skills_used:
                        companion_skills_used.append(skill)

        companion_info: Dict[str, Any] = {
            "companion_id": companion_id,
            "companion_name": companion_name,
            "specialization": specialization,
            "status": status,
            "current_task": current_task,
            "tasks_completed": companion_tasks_completed,
            "tasks_failed": companion_tasks_failed,
            "skills_used": companion_skills_used,
        }

        # Get detailed information if requested
        if include_companion_details:
            try:
                blocks = client.agents.blocks.list(agent_id=companion_id)
                for block in blocks:
                    label = getattr(block, "label", "")

                    # Get task history if requested
                    if label == "task_context" and include_task_history:
                        block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                        if block_id:
                            full_block = client.blocks.retrieve(block_id=block_id)
                            value = getattr(full_block, "value", "{}")
                            if isinstance(value, str):
                                try:
                                    ctx = json.loads(value)
                                    task_history = ctx.get("task_history", [])
                                    companion_info["task_history"] = task_history[-20:]
                                except Exception:
                                    pass

                    # Get currently loaded skills
                    elif label == "dcf_active_skills":
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

    # Calculate overall metrics
    success_rate = (completed_tasks / (completed_tasks + failed_tasks) * 100) if (completed_tasks + failed_tasks) > 0 else 0
    avg_duration = (total_duration / tasks_with_duration) if tasks_with_duration > 0 else None

    metrics = {
        "companion_count": len(companions),
        "idle_companions": sum(1 for c in companions if c.get("status") == "idle"),
        "busy_companions": sum(1 for c in companions if c.get("status") == "busy"),
        "error_companions": sum(1 for c in companions if c.get("status") == "error"),
        "total_delegations": total_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "pending_tasks": pending_tasks,
        "success_rate": round(success_rate, 1),
        "avg_task_duration_s": round(avg_duration, 2) if avg_duration else None,
        "unique_skills_used": len(skill_metrics),
        "top_skills": sorted(
            [(k, v["usage_count"], v.get("success_rate")) for k, v in skill_metrics.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5],
    }

    return {
        "status": f"Activity report for session '{session_id}'",
        "error": None,
        "session_id": session_id,
        "session_state": session_state,
        "session_context": session_context,
        "delegations": delegations[-50:],  # Last 50 delegations
        "companions": companions,
        "skill_metrics": skill_metrics,
        "metrics": metrics,
    }
