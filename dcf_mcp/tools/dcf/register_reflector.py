from typing import Any, Dict
import os
import json

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
REFLECTOR_REGISTRATION_BLOCK_LABEL = "reflector_registration"
REFLECTOR_GUIDELINES_BLOCK_LABEL = "reflector_guidelines"


def register_reflector(
    planner_agent_id: str,
    reflector_agent_id: str,
    initial_guidelines_json: str = None
) -> Dict[str, Any]:
    """Register a Reflector agent as a companion to a Planner agent.

    This establishes the bidirectional memory sharing relationship:
    1. Creates a `reflector_registration` block on the Planner containing the Reflector's ID
    2. Creates a `reflector_guidelines` block on the Planner (readable by both)
    3. Records the Planner's ID in the Reflector's memory for reference

    The Reflector can then:
    - Read the Planner's shared memory blocks via `read_shared_memory_blocks`
    - Update the `reflector_guidelines` block via `update_reflector_guidelines`

    The Planner should:
    - Check `reflector_guidelines` during planning for recommendations
    - Trigger reflection after workflow completion (optional)

    Args:
        planner_agent_id: The Planner agent's UUID.
        reflector_agent_id: The Reflector agent's UUID.
        initial_guidelines_json: Optional initial guidelines JSON to seed the guidelines block.

    Returns:
        dict: {
            "status": str or None,
            "error": str or None,
            "planner_agent_id": str,
            "reflector_agent_id": str,
            "registration_block_id": str or None,
            "guidelines_block_id": str or None,
            "warnings": list
        }
    """
    warnings = []

    # Validate inputs
    if not isinstance(planner_agent_id, str) or not planner_agent_id.strip():
        return {
            "status": None,
            "error": "planner_agent_id must be a non-empty string",
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": reflector_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "warnings": []
        }
    if not isinstance(reflector_agent_id, str) or not reflector_agent_id.strip():
        return {
            "status": None,
            "error": "reflector_agent_id must be a non-empty string",
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": reflector_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "warnings": []
        }

    # Lazy import
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": reflector_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "warnings": []
        }

    try:
        client = Letta(base_url=LETTA_BASE_URL)

        # Verify both agents exist
        try:
            client.agents.retrieve(planner_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Planner agent not found: {e}",
                "planner_agent_id": planner_agent_id,
                "reflector_agent_id": reflector_agent_id,
                "registration_block_id": None,
                "guidelines_block_id": None,
                "warnings": []
            }

        try:
            client.agents.retrieve(reflector_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Reflector agent not found: {e}",
                "planner_agent_id": planner_agent_id,
                "reflector_agent_id": reflector_agent_id,
                "registration_block_id": None,
                "guidelines_block_id": None,
                "warnings": []
            }

        # Check for existing registration on Planner
        planner_blocks = client.agents.blocks.list(agent_id=planner_agent_id)
        existing_reg_block_id = None
        existing_guidelines_block_id = None

        for block in planner_blocks:
            label = getattr(block, "label", "")
            block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
            if label == REFLECTOR_REGISTRATION_BLOCK_LABEL:
                existing_reg_block_id = block_id
            elif label == REFLECTOR_GUIDELINES_BLOCK_LABEL:
                existing_guidelines_block_id = block_id

        # Create or update registration block
        registration_data = {
            "reflector_agent_id": reflector_agent_id,
            "registered_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "planner_agent_id": planner_agent_id
        }
        registration_json = json.dumps(registration_data, indent=2)

        if existing_reg_block_id:
            # Update existing registration
            client.blocks.update(block_id=existing_reg_block_id, value=registration_json)
            registration_block_id = existing_reg_block_id
            warnings.append("Updated existing reflector registration (previous registration overwritten)")
        else:
            # Create new registration block
            reg_block = client.blocks.create(
                label=REFLECTOR_REGISTRATION_BLOCK_LABEL,
                value=registration_json
            )
            registration_block_id = getattr(reg_block, "id", None) or getattr(reg_block, "block_id", None)
            if not registration_block_id:
                raise RuntimeError("Failed to create registration block: no ID returned")
            client.agents.blocks.attach(agent_id=planner_agent_id, block_id=registration_block_id)

        # Create or update guidelines block
        if initial_guidelines_json:
            try:
                guidelines = json.loads(initial_guidelines_json)
            except Exception:
                guidelines = {}
                warnings.append("initial_guidelines_json was invalid JSON; using empty guidelines")
        else:
            guidelines = {}

        # Ensure required structure
        if "last_updated" not in guidelines:
            guidelines["last_updated"] = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
        if "revision" not in guidelines:
            guidelines["revision"] = 1
        if "guidelines" not in guidelines:
            guidelines["guidelines"] = {
                "skill_recommendations": [],
                "workflow_patterns": [],
                "user_intent_tips": [],
                "warnings": []
            }
        if "recent_insights" not in guidelines:
            guidelines["recent_insights"] = []

        guidelines_json = json.dumps(guidelines, indent=2)

        if existing_guidelines_block_id:
            # Update existing guidelines (preserve if not provided initial)
            if initial_guidelines_json:
                client.blocks.update(block_id=existing_guidelines_block_id, value=guidelines_json)
            guidelines_block_id = existing_guidelines_block_id
        else:
            # Create new guidelines block
            guide_block = client.blocks.create(
                label=REFLECTOR_GUIDELINES_BLOCK_LABEL,
                value=guidelines_json
            )
            guidelines_block_id = getattr(guide_block, "id", None) or getattr(guide_block, "block_id", None)
            if not guidelines_block_id:
                raise RuntimeError("Failed to create guidelines block: no ID returned")
            # Attach to Planner
            client.agents.blocks.attach(agent_id=planner_agent_id, block_id=guidelines_block_id)
            # Also attach to Reflector for write access
            client.agents.blocks.attach(agent_id=reflector_agent_id, block_id=guidelines_block_id)

        # Record Planner reference in Reflector's memory
        reflector_blocks = client.agents.blocks.list(agent_id=reflector_agent_id)
        reflector_planner_ref_id = None
        for block in reflector_blocks:
            if getattr(block, "label", "") == "planner_reference":
                reflector_planner_ref_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                break

        planner_ref_data = {
            "planner_agent_id": planner_agent_id,
            "guidelines_block_id": guidelines_block_id,
            "registered_at": registration_data["registered_at"]
        }
        planner_ref_json = json.dumps(planner_ref_data, indent=2)

        if reflector_planner_ref_id:
            client.blocks.update(block_id=reflector_planner_ref_id, value=planner_ref_json)
        else:
            ref_block = client.blocks.create(label="planner_reference", value=planner_ref_json)
            ref_block_id = getattr(ref_block, "id", None) or getattr(ref_block, "block_id", None)
            if ref_block_id:
                client.agents.blocks.attach(agent_id=reflector_agent_id, block_id=ref_block_id)

        return {
            "status": f"Reflector '{reflector_agent_id}' registered as companion to Planner '{planner_agent_id}'",
            "error": None,
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": reflector_agent_id,
            "registration_block_id": registration_block_id,
            "guidelines_block_id": guidelines_block_id,
            "warnings": warnings
        }

    except Exception as e:
        return {
            "status": None,
            "error": f"Registration failed: {e.__class__.__name__}: {e}",
            "planner_agent_id": planner_agent_id,
            "reflector_agent_id": reflector_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "warnings": warnings
        }
