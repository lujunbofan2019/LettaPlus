"""Dismiss (delete) a Companion agent and clean up resources."""

from typing import Any, Dict, List, Optional
import os
import json

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
SKILL_STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")


def dismiss_companion(
    companion_id: str,
    unload_skills: bool = True,
    detach_shared_blocks: bool = True,
) -> Dict[str, Any]:
    """Dismiss a Companion agent from the session and clean up resources.

    This function:
    1. Optionally unloads any skills currently loaded on the Companion
    2. Optionally detaches shared memory blocks
    3. Deletes the Companion agent

    Args:
        companion_id: Companion agent ID to dismiss.
        unload_skills: Whether to unload skills before deletion (default: True).
        detach_shared_blocks: Whether to detach shared blocks before deletion (default: True).

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "companion_id": str,
            "skills_unloaded": List[str],
            "blocks_detached": List[str],
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
            "companion_id": companion_id,
            "skills_unloaded": [],
            "blocks_detached": [],
            "warnings": [],
        }

    warnings: List[str] = []
    skills_unloaded: List[str] = []
    blocks_detached: List[str] = []

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "companion_id": companion_id,
            "skills_unloaded": [],
            "blocks_detached": [],
            "warnings": [],
        }

    # Verify agent exists
    try:
        agent = client.agents.retrieve(agent_id=companion_id)
        agent_name = getattr(agent, "name", companion_id)
    except Exception as e:
        return {
            "status": None,
            "error": f"Companion not found: {e}",
            "companion_id": companion_id,
            "skills_unloaded": [],
            "blocks_detached": [],
            "warnings": [],
        }

    # Unload skills if requested
    if unload_skills:
        try:
            # Read the skill state block to find loaded skills
            blocks = client.agents.blocks.list(agent_id=companion_id)
            skill_state_block = None
            for block in blocks:
                if getattr(block, "label", "") == SKILL_STATE_BLOCK_LABEL:
                    skill_state_block = block
                    break

            if skill_state_block:
                block_id = getattr(skill_state_block, "id", None) or getattr(skill_state_block, "block_id", None)
                if block_id:
                    full_block = client.blocks.retrieve(block_id=block_id)
                    value = getattr(full_block, "value", "{}")
                    if isinstance(value, str):
                        try:
                            state = json.loads(value)
                        except Exception:
                            state = {}
                    else:
                        state = value if isinstance(value, dict) else {}

                    # Unload each skill
                    from tools.dcf.unload_skill import unload_skill
                    for manifest_id in list(state.keys()):
                        try:
                            result = unload_skill(manifest_id=manifest_id, agent_id=companion_id)
                            if result.get("status"):
                                skills_unloaded.append(manifest_id)
                            else:
                                warnings.append(f"Failed to unload skill {manifest_id}: {result.get('error')}")
                        except Exception as e:
                            warnings.append(f"Error unloading skill {manifest_id}: {e}")
        except Exception as e:
            warnings.append(f"Could not unload skills: {e}")

    # Detach shared blocks if requested
    if detach_shared_blocks:
        try:
            blocks = client.agents.blocks.list(agent_id=companion_id)
            # Identify shared blocks (those that might be attached to other agents)
            # We detach all blocks except core ones like persona, task_context
            core_labels = {"persona", "task_context", SKILL_STATE_BLOCK_LABEL}
            for block in blocks:
                label = getattr(block, "label", "")
                block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                if label not in core_labels and block_id:
                    try:
                        client.agents.blocks.detach(agent_id=companion_id, block_id=block_id)
                        blocks_detached.append(block_id)
                    except Exception as e:
                        warnings.append(f"Failed to detach block {block_id}: {e}")
        except Exception as e:
            warnings.append(f"Could not detach blocks: {e}")

    # Delete the agent
    try:
        client.agents.delete(agent_id=companion_id)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to delete Companion agent: {e}",
            "companion_id": companion_id,
            "skills_unloaded": skills_unloaded,
            "blocks_detached": blocks_detached,
            "warnings": warnings,
        }

    return {
        "status": f"Dismissed Companion '{agent_name}' (id: {companion_id})",
        "error": None,
        "companion_id": companion_id,
        "skills_unloaded": skills_unloaded,
        "blocks_detached": blocks_detached,
        "warnings": warnings,
    }
