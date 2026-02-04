"""Create a session-scoped Companion agent for DCF+ Delegated Execution."""

from typing import Any, Dict, List, Optional
import os
import json
import uuid
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
DEFAULT_MODEL = os.getenv("DCF_DEFAULT_MODEL", "openai/gpt-4o-mini")


def create_companion(
    session_id: str,
    conductor_id: str,
    specialization: str = "generalist",
    shared_block_ids_json: Optional[str] = None,
    initial_skills_json: Optional[str] = None,
    companion_name: Optional[str] = None,
    persona_override: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a session-scoped Companion agent with standard DCF+ configuration.

    The Companion is created with:
    - Standard memory blocks (persona, task_context, dcf_active_skills)
    - Shared blocks attached (session_context, etc.) if provided
    - Tags for session membership, role, and specialization
    - The send_message_to_agent_async tool for reporting results to Conductor

    Args:
        session_id: Unique session identifier for tagging.
        conductor_id: Conductor's agent ID (stored in persona for result reporting).
        specialization: Initial specialization ("generalist", "research", "analysis", "writing", etc.).
        shared_block_ids_json: Optional JSON array of block IDs to attach (e.g., session_context block).
        initial_skills_json: Optional JSON array of skill manifest paths/URIs to pre-load.
        companion_name: Optional custom name. If not provided, auto-generated.
        persona_override: Optional custom persona text. If not provided, uses default.
        model: LLM model to use (e.g., "openai/gpt-4o-mini"). Defaults to DCF_DEFAULT_MODEL env var.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "companion_id": str,
            "companion_name": str,
            "tags": List[str],
            "shared_blocks_attached": List[str],
            "skills_loaded": List[str],
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
            "companion_id": None,
            "companion_name": None,
            "tags": [],
            "shared_blocks_attached": [],
            "skills_loaded": [],
            "warnings": [],
        }

    warnings: List[str] = []
    shared_blocks_attached: List[str] = []
    skills_loaded: List[str] = []

    # Parse shared block IDs
    shared_block_ids: List[str] = []
    if shared_block_ids_json:
        try:
            parsed = json.loads(shared_block_ids_json)
            if isinstance(parsed, list):
                shared_block_ids = [str(b) for b in parsed if b]
        except Exception as e:
            warnings.append(f"Failed to parse shared_block_ids_json: {e}")

    # Parse initial skills
    initial_skills: List[str] = []
    if initial_skills_json:
        try:
            parsed = json.loads(initial_skills_json)
            if isinstance(parsed, list):
                initial_skills = [str(s) for s in parsed if s]
        except Exception as e:
            warnings.append(f"Failed to parse initial_skills_json: {e}")

    # Generate companion name with consistent convention:
    # Format: companion-{specialization}-{session_prefix}-{uuid}
    # Examples: companion-research-e2e-test-a1b2c3d4
    #           companion-generalist-prod-sess-f9e8d7c6
    short_uuid = str(uuid.uuid4())[:8]
    session_prefix = session_id[:8] if len(session_id) >= 8 else session_id

    if companion_name:
        # If custom name provided, ensure it follows convention
        # Accept if it starts with "companion-" or normalize it
        if not companion_name.startswith("companion-"):
            name = f"companion-{companion_name}"
        else:
            name = companion_name
    else:
        # Auto-generate with consistent pattern
        name = f"companion-{specialization}-{session_prefix}-{short_uuid}"

    # Build persona
    default_persona = f"""You are a Companion agent in the DCF+ framework.

Role: Execute tasks delegated by the Conductor and report results.
Session: {session_id}
Conductor ID: {conductor_id}
Specialization: {specialization}

Guidelines:
1. Wait for task_delegation messages from the Conductor
2. Load required skills for each task
3. Execute tasks according to skill directives
4. Report results back to the Conductor using send_message_to_agent_async
5. Unload skills after task completion to free context

When reporting results, use this format:
{{
    "type": "task_result",
    "task_id": "<from delegation>",
    "status": "succeeded" | "failed",
    "output": {{ ... }},
    "metrics": {{ "duration_s": N, "tool_calls": N }}
}}
"""
    persona_text = persona_override or default_persona

    # Build tags
    tags = [
        "role:companion",
        f"session:{session_id}",
        f"specialization:{specialization}",
        "status:idle",
        f"conductor:{conductor_id}",
    ]

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "companion_id": None,
            "companion_name": None,
            "tags": [],
            "shared_blocks_attached": [],
            "skills_loaded": [],
            "warnings": warnings,
        }

    # Check if send_message_to_agent_async tool exists, find its ID
    async_message_tool_id = None
    try:
        tools = client.tools.list()
        for tool in tools:
            tool_name = getattr(tool, "name", None)
            if tool_name == "send_message_to_agent_async":
                async_message_tool_id = getattr(tool, "id", None)
                break
    except Exception as e:
        warnings.append(f"Could not list tools to find send_message_to_agent_async: {e}")

    # Build memory blocks
    memory_blocks = [
        {
            "label": "persona",
            "value": persona_text,
            "limit": 4000,
        },
        {
            "label": "task_context",
            "description": "Current task details and inputs. Updated when a new task is delegated.",
            "value": json.dumps({
                "current_task": None,
                "task_history": [],
            }),
            "limit": 8000,
        },
    ]

    # Create the agent
    try:
        # Use provided model or default
        agent_model = model or DEFAULT_MODEL

        create_kwargs = {
            "name": name,
            "model": agent_model,
            "memory_blocks": memory_blocks,
            "tags": tags,
        }

        # Attach async message tool if found
        if async_message_tool_id:
            create_kwargs["tool_ids"] = [async_message_tool_id]

        agent = client.agents.create(**create_kwargs)
        companion_id = getattr(agent, "id", None)
        companion_name_actual = getattr(agent, "name", name)

        if not companion_id:
            return {
                "status": None,
                "error": "Agent created but no ID returned",
                "companion_id": None,
                "companion_name": None,
                "tags": [],
                "shared_blocks_attached": [],
                "skills_loaded": [],
                "warnings": warnings,
            }

    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to create Companion agent: {e}",
            "companion_id": None,
            "companion_name": None,
            "tags": [],
            "shared_blocks_attached": [],
            "skills_loaded": [],
            "warnings": warnings,
        }

    # Attach shared blocks
    for block_id in shared_block_ids:
        try:
            client.agents.blocks.attach(agent_id=companion_id, block_id=block_id)
            shared_blocks_attached.append(block_id)
        except Exception as e:
            warnings.append(f"Failed to attach shared block {block_id}: {e}")

    # Load initial skills if provided
    if initial_skills:
        try:
            from tools.dcf.load_skill import load_skill
            for skill_path in initial_skills:
                result = load_skill(skill_manifest=skill_path, agent_id=companion_id)
                if result.get("ok"):
                    skills_loaded.append(skill_path)
                else:
                    warnings.append(f"Failed to load skill {skill_path}: {result.get('error')}")
        except Exception as e:
            warnings.append(f"Could not load skills: {e}")

    return {
        "status": f"Created Companion '{companion_name_actual}' for session '{session_id}'",
        "error": None,
        "companion_id": companion_id,
        "companion_name": companion_name_actual,
        "tags": tags,
        "shared_blocks_attached": shared_blocks_attached,
        "skills_loaded": skills_loaded,
        "warnings": warnings,
    }
