from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
STRATEGIST_REGISTRATION_BLOCK_LABEL = "strategist_registration"


def trigger_strategist_analysis(
    session_id: str,
    conductor_agent_id: str,
    trigger_reason: str = "periodic",
    tasks_since_last_analysis: int = None,
    recent_failures: int = None,
    include_full_history: bool = False,
    async_message: bool = True,
    max_steps: int = None
) -> Dict[str, Any]:
    """Trigger the Strategist agent to analyze session activity.

    This tool should be called periodically (every 3-5 task completions) or
    on significant events to initiate the analysis process. It sends an
    `analysis_event` to the Strategist agent registered with the given Conductor.

    The analysis event contains:
    - Session identification
    - Trigger reason and context
    - References to the Conductor for memory access

    This is the Phase 2 (DCF+) equivalent of `trigger_reflection` from Phase 1,
    but can be called during an active session (not just after completion).

    Args:
        session_id: The current session's UUID.
        conductor_agent_id: The Conductor agent's UUID (to find its registered Strategist).
        trigger_reason: Why analysis was triggered:
            - "periodic": Regular analysis every 3-5 tasks
            - "milestone": Significant event (error spike, scaling decision)
            - "on_demand": Conductor explicitly requests analysis
            - "task_completed": After each task (for continuous mode)
        tasks_since_last_analysis: Number of tasks completed since last analysis.
        recent_failures: Number of recent task failures (for context).
        include_full_history: If True, include complete session history in event.
        async_message: If True, send asynchronously (default). If False, wait for response.
        max_steps: Optional max_steps hint for the Strategist's processing.

    Returns:
        dict: {
            "status": str or None,
            "error": str or None,
            "session_id": str,
            "conductor_agent_id": str,
            "strategist_agent_id": str or None,
            "message_sent": bool,
            "run_id": str or None (if async)
        }
    """
    # Validate trigger_reason
    valid_reasons = {"periodic", "milestone", "on_demand", "task_completed"}
    if trigger_reason not in valid_reasons:
        trigger_reason = "periodic"

    # Lazy import
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "session_id": session_id,
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": None,
            "message_sent": False,
            "run_id": None
        }

    try:
        client = Letta(base_url=LETTA_BASE_URL)

        # Find registered Strategist
        conductor_blocks = client.agents.blocks.list(agent_id=conductor_agent_id)
        strategist_agent_id = None

        for block in conductor_blocks:
            if getattr(block, "label", "") == STRATEGIST_REGISTRATION_BLOCK_LABEL:
                block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                if block_id:
                    full_block = client.blocks.retrieve(block_id=block_id)
                    value = getattr(full_block, "value", "{}")
                    try:
                        reg_data = json.loads(value) if isinstance(value, str) else value
                        strategist_agent_id = reg_data.get("strategist_agent_id")
                    except Exception:
                        pass
                break

        if not strategist_agent_id:
            return {
                "status": None,
                "error": f"No Strategist registered with Conductor '{conductor_agent_id}'",
                "session_id": session_id,
                "conductor_agent_id": conductor_agent_id,
                "strategist_agent_id": None,
                "message_sent": False,
                "run_id": None
            }

        # Verify Strategist exists
        try:
            client.agents.retrieve(strategist_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Registered Strategist '{strategist_agent_id}' not found: {e}",
                "session_id": session_id,
                "conductor_agent_id": conductor_agent_id,
                "strategist_agent_id": strategist_agent_id,
                "message_sent": False,
                "run_id": None
            }

        # Build analysis event
        now_iso = datetime.now(timezone.utc).isoformat()
        analysis_event = {
            "type": "analysis_event",
            "session_id": session_id,
            "conductor_id": conductor_agent_id,
            "trigger_reason": trigger_reason,
            "context": {
                "tasks_since_last_analysis": tasks_since_last_analysis,
                "recent_failures": recent_failures,
                "include_full_history": include_full_history
            },
            "triggered_at": now_iso
        }

        # Extract AMSP metrics from delegation_log (v1.1.0)
        amsp_metrics = None
        for block in conductor_blocks:
            if getattr(block, "label", "") == "delegation_log":
                block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                if block_id:
                    try:
                        full_block = client.blocks.retrieve(block_id=block_id)
                        value = getattr(full_block, "value", "{}")
                        log_data = json.loads(value) if isinstance(value, str) else value
                        delegations = log_data.get("delegations", [])

                        # Compute AMSP summary from recent delegations
                        tier_counts = {"0": 0, "1": 0, "2": 0, "3": 0}
                        total_fcs = 0
                        delegations_with_model = 0

                        for d in delegations[-20:]:  # Last 20 delegations
                            ms = d.get("model_selection")
                            if ms:
                                tier = str(ms.get("tier", 0))
                                tier_counts[tier] = tier_counts.get(tier, 0) + 1
                                if ms.get("fcs"):
                                    total_fcs += ms["fcs"]
                                delegations_with_model += 1

                        if delegations_with_model > 0:
                            amsp_metrics = {
                                "delegations_analyzed": delegations_with_model,
                                "tier_distribution": tier_counts,
                                "avg_fcs": round(total_fcs / delegations_with_model, 2),
                            }
                    except Exception:
                        pass
                break

        if amsp_metrics:
            analysis_event["amsp_metrics"] = amsp_metrics

        # Optionally include session context summary
        if include_full_history:
            # Read session_context block if available
            for block in conductor_blocks:
                if getattr(block, "label", "") == "session_context":
                    block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                    if block_id:
                        try:
                            full_block = client.blocks.retrieve(block_id=block_id)
                            value = getattr(full_block, "value", "{}")
                            session_context = json.loads(value) if isinstance(value, str) else value
                            analysis_event["session_context_snapshot"] = session_context
                        except Exception:
                            pass
                    break

        # Send message to Strategist
        msg = {"role": "system", "content": [{"type": "text", "text": json.dumps(analysis_event)}]}
        req = {"messages": [msg]}
        if isinstance(max_steps, int):
            req["max_steps"] = max_steps

        try:
            if async_message:
                resp = client.agents.messages.create_async(agent_id=strategist_agent_id, **req)
                run_id = getattr(resp, "id", None) or getattr(resp, "run_id", None)
                return {
                    "status": f"Analysis triggered for session '{session_id}' (async, reason: {trigger_reason})",
                    "error": None,
                    "session_id": session_id,
                    "conductor_agent_id": conductor_agent_id,
                    "strategist_agent_id": strategist_agent_id,
                    "message_sent": True,
                    "run_id": run_id
                }
            else:
                resp = client.agents.messages.create(agent_id=strategist_agent_id, **req)
                return {
                    "status": f"Analysis completed for session '{session_id}' (reason: {trigger_reason})",
                    "error": None,
                    "session_id": session_id,
                    "conductor_agent_id": conductor_agent_id,
                    "strategist_agent_id": strategist_agent_id,
                    "message_sent": True,
                    "run_id": None
                }
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to send analysis event: {e.__class__.__name__}: {e}",
                "session_id": session_id,
                "conductor_agent_id": conductor_agent_id,
                "strategist_agent_id": strategist_agent_id,
                "message_sent": False,
                "run_id": None
            }

    except Exception as e:
        return {
            "status": None,
            "error": f"Trigger failed: {e.__class__.__name__}: {e}",
            "session_id": session_id,
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": None,
            "message_sent": False,
            "run_id": None
        }
