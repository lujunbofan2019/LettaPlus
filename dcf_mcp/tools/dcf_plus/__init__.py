"""DCF+ Tools for Delegated Execution Pattern.

This module provides tools for the Conductor, Companion, and Strategist agents
in the DCF+ (Dynamic Capabilities Framework Plus) architecture.

Agent Roles:
- Conductor: Orchestrates session, manages Companions, delegates tasks
- Companion: Executes delegated tasks using loaded skills
- Strategist: Observes patterns, provides optimization recommendations

Tool Categories:
1. Companion Management:
   - create_companion: Create session-scoped Companion agents
   - dismiss_companion: Remove Companion agents with cleanup
   - list_session_companions: List all Companions in a session
   - update_companion_status: Update Companion status tags

2. Session Management:
   - create_session_context: Create shared session context block
   - update_session_context: Update shared session state
   - finalize_session: Clean up session resources

3. Task Delegation & Reporting:
   - delegate_task: Delegate task to specific Companion (Conductor)
   - broadcast_task: Delegate to Companions matching criteria (Conductor)
   - report_task_result: Report task completion back to Conductor (Companion)

4. Strategist Integration:
   - register_strategist: Register Strategist as Conductor's companion
   - trigger_strategist_analysis: Trigger Strategist to analyze session

5. Strategist Observation:
   - read_session_activity: Get session activity for analysis
   - update_conductor_guidelines: Publish recommendations to Conductor
"""

from .create_companion import create_companion
from .dismiss_companion import dismiss_companion
from .list_session_companions import list_session_companions
from .update_companion_status import update_companion_status
from .create_session_context import create_session_context
from .update_session_context import update_session_context
from .finalize_session import finalize_session
from .delegate_task import delegate_task
from .broadcast_task import broadcast_task
from .report_task_result import report_task_result
from .register_strategist import register_strategist
from .trigger_strategist_analysis import trigger_strategist_analysis
from .read_session_activity import read_session_activity
from .update_conductor_guidelines import update_conductor_guidelines

__all__ = [
    # Companion Management
    "create_companion",
    "dismiss_companion",
    "list_session_companions",
    "update_companion_status",
    # Session Management
    "create_session_context",
    "update_session_context",
    "finalize_session",
    # Task Delegation & Reporting
    "delegate_task",
    "broadcast_task",
    "report_task_result",
    # Strategist Integration
    "register_strategist",
    "trigger_strategist_analysis",
    # Strategist Observation
    "read_session_activity",
    "update_conductor_guidelines",
]
