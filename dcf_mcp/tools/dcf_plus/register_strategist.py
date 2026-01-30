from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
STRATEGIST_REGISTRATION_BLOCK_LABEL = "strategist_registration"
STRATEGIST_GUIDELINES_BLOCK_LABEL = "strategist_guidelines"
DELEGATION_LOG_BLOCK_LABEL = "delegation_log"
CONDUCTOR_REFERENCE_BLOCK_LABEL = "conductor_reference"


def register_strategist(
    conductor_agent_id: str,
    strategist_agent_id: str,
    initial_guidelines_json: str = None
) -> Dict[str, Any]:
    """Register a Strategist agent as a companion to a Conductor agent.

    This establishes the bidirectional memory sharing relationship for DCF+:
    1. Creates a `strategist_registration` block on the Conductor containing the Strategist's ID
    2. Creates a `strategist_guidelines` block on the Conductor (writable by Strategist)
    3. Creates a `delegation_log` block on the Conductor (readable by Strategist)
    4. Records the Conductor's ID in the Strategist's memory for reference

    The Strategist can then:
    - Read the Conductor's shared memory blocks via `read_shared_memory_blocks`
    - Read session activity via `read_session_activity`
    - Update the `strategist_guidelines` block via `update_conductor_guidelines`

    The Conductor should:
    - Check `strategist_guidelines` before delegating for recommendations
    - Trigger analysis periodically via `trigger_strategist_analysis`

    This is the Phase 2 (DCF+) equivalent of `register_reflector` from Phase 1.

    Args:
        conductor_agent_id: The Conductor agent's UUID.
        strategist_agent_id: The Strategist agent's UUID.
        initial_guidelines_json: Optional initial guidelines JSON to seed the guidelines block.

    Returns:
        dict: {
            "status": str or None,
            "error": str or None,
            "conductor_agent_id": str,
            "strategist_agent_id": str,
            "registration_block_id": str or None,
            "guidelines_block_id": str or None,
            "delegation_log_block_id": str or None,
            "warnings": list
        }
    """
    warnings = []

    # Validate inputs
    if not isinstance(conductor_agent_id, str) or not conductor_agent_id.strip():
        return {
            "status": None,
            "error": "conductor_agent_id must be a non-empty string",
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": strategist_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "delegation_log_block_id": None,
            "warnings": []
        }
    if not isinstance(strategist_agent_id, str) or not strategist_agent_id.strip():
        return {
            "status": None,
            "error": "strategist_agent_id must be a non-empty string",
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": strategist_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "delegation_log_block_id": None,
            "warnings": []
        }

    # Lazy import
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": strategist_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "delegation_log_block_id": None,
            "warnings": []
        }

    try:
        client = Letta(base_url=LETTA_BASE_URL)

        # Verify both agents exist
        try:
            client.agents.retrieve(conductor_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Conductor agent not found: {e}",
                "conductor_agent_id": conductor_agent_id,
                "strategist_agent_id": strategist_agent_id,
                "registration_block_id": None,
                "guidelines_block_id": None,
                "delegation_log_block_id": None,
                "warnings": []
            }

        try:
            client.agents.retrieve(strategist_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Strategist agent not found: {e}",
                "conductor_agent_id": conductor_agent_id,
                "strategist_agent_id": strategist_agent_id,
                "registration_block_id": None,
                "guidelines_block_id": None,
                "delegation_log_block_id": None,
                "warnings": []
            }

        # Check for existing blocks on Conductor
        conductor_blocks = client.agents.blocks.list(agent_id=conductor_agent_id)
        existing_reg_block_id = None
        existing_guidelines_block_id = None
        existing_delegation_log_block_id = None

        for block in conductor_blocks:
            label = getattr(block, "label", "")
            block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
            if label == STRATEGIST_REGISTRATION_BLOCK_LABEL:
                existing_reg_block_id = block_id
            elif label == STRATEGIST_GUIDELINES_BLOCK_LABEL:
                existing_guidelines_block_id = block_id
            elif label == DELEGATION_LOG_BLOCK_LABEL:
                existing_delegation_log_block_id = block_id

        now_iso = datetime.now(timezone.utc).isoformat()

        # Create or update registration block
        registration_data = {
            "strategist_agent_id": strategist_agent_id,
            "registered_at": now_iso,
            "conductor_agent_id": conductor_agent_id
        }
        registration_json = json.dumps(registration_data, indent=2)

        if existing_reg_block_id:
            # Update existing registration
            client.blocks.update(block_id=existing_reg_block_id, value=registration_json)
            registration_block_id = existing_reg_block_id
            warnings.append("Updated existing strategist registration (previous registration overwritten)")
        else:
            # Create new registration block
            reg_block = client.blocks.create(
                label=STRATEGIST_REGISTRATION_BLOCK_LABEL,
                value=registration_json
            )
            registration_block_id = getattr(reg_block, "id", None) or getattr(reg_block, "block_id", None)
            if not registration_block_id:
                raise RuntimeError("Failed to create registration block: no ID returned")
            client.agents.blocks.attach(agent_id=conductor_agent_id, block_id=registration_block_id)

        # Create or update guidelines block
        if initial_guidelines_json:
            try:
                guidelines = json.loads(initial_guidelines_json)
            except Exception:
                guidelines = {}
                warnings.append("initial_guidelines_json was invalid JSON; using empty guidelines")
        else:
            guidelines = {}

        # Ensure required structure for strategist guidelines
        if "last_updated" not in guidelines:
            guidelines["last_updated"] = now_iso
        if "revision" not in guidelines:
            guidelines["revision"] = 1
        if "recommendations" not in guidelines:
            guidelines["recommendations"] = []
        if "skill_preferences" not in guidelines:
            guidelines["skill_preferences"] = {}
        if "companion_scaling" not in guidelines:
            guidelines["companion_scaling"] = {
                "min_companions": 1,
                "max_companions": 5,
                "scale_up_threshold": 3,
                "scale_down_threshold": 0
            }
        if "warnings" not in guidelines:
            guidelines["warnings"] = []

        guidelines_json = json.dumps(guidelines, indent=2)

        if existing_guidelines_block_id:
            # Update existing guidelines (preserve if not provided initial)
            if initial_guidelines_json:
                client.blocks.update(block_id=existing_guidelines_block_id, value=guidelines_json)
            guidelines_block_id = existing_guidelines_block_id
        else:
            # Create new guidelines block
            guide_block = client.blocks.create(
                label=STRATEGIST_GUIDELINES_BLOCK_LABEL,
                value=guidelines_json
            )
            guidelines_block_id = getattr(guide_block, "id", None) or getattr(guide_block, "block_id", None)
            if not guidelines_block_id:
                raise RuntimeError("Failed to create guidelines block: no ID returned")
            # Attach to Conductor (read-only for Conductor)
            client.agents.blocks.attach(agent_id=conductor_agent_id, block_id=guidelines_block_id)
            # Also attach to Strategist for write access
            client.agents.blocks.attach(agent_id=strategist_agent_id, block_id=guidelines_block_id)

        # Create or update delegation_log block
        delegation_log_data = {
            "created_at": now_iso,
            "session_id": None,
            "delegations": []
        }
        delegation_log_json = json.dumps(delegation_log_data, indent=2)

        if existing_delegation_log_block_id:
            # Keep existing delegation log
            delegation_log_block_id = existing_delegation_log_block_id
        else:
            # Create new delegation log block
            log_block = client.blocks.create(
                label=DELEGATION_LOG_BLOCK_LABEL,
                value=delegation_log_json
            )
            delegation_log_block_id = getattr(log_block, "id", None) or getattr(log_block, "block_id", None)
            if not delegation_log_block_id:
                raise RuntimeError("Failed to create delegation_log block: no ID returned")
            # Attach to Conductor (Conductor writes via delegate_task)
            client.agents.blocks.attach(agent_id=conductor_agent_id, block_id=delegation_log_block_id)
            # Also attach to Strategist for read access
            client.agents.blocks.attach(agent_id=strategist_agent_id, block_id=delegation_log_block_id)

        # Record Conductor reference in Strategist's memory
        strategist_blocks = client.agents.blocks.list(agent_id=strategist_agent_id)
        strategist_conductor_ref_id = None
        for block in strategist_blocks:
            if getattr(block, "label", "") == CONDUCTOR_REFERENCE_BLOCK_LABEL:
                strategist_conductor_ref_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                break

        conductor_ref_data = {
            "conductor_agent_id": conductor_agent_id,
            "guidelines_block_id": guidelines_block_id,
            "delegation_log_block_id": delegation_log_block_id,
            "registered_at": now_iso
        }
        conductor_ref_json = json.dumps(conductor_ref_data, indent=2)

        if strategist_conductor_ref_id:
            client.blocks.update(block_id=strategist_conductor_ref_id, value=conductor_ref_json)
        else:
            ref_block = client.blocks.create(label=CONDUCTOR_REFERENCE_BLOCK_LABEL, value=conductor_ref_json)
            ref_block_id = getattr(ref_block, "id", None) or getattr(ref_block, "block_id", None)
            if ref_block_id:
                client.agents.blocks.attach(agent_id=strategist_agent_id, block_id=ref_block_id)

        return {
            "status": f"Strategist '{strategist_agent_id}' registered as companion to Conductor '{conductor_agent_id}'",
            "error": None,
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": strategist_agent_id,
            "registration_block_id": registration_block_id,
            "guidelines_block_id": guidelines_block_id,
            "delegation_log_block_id": delegation_log_block_id,
            "warnings": warnings
        }

    except Exception as e:
        return {
            "status": None,
            "error": f"Registration failed: {e.__class__.__name__}: {e}",
            "conductor_agent_id": conductor_agent_id,
            "strategist_agent_id": strategist_agent_id,
            "registration_block_id": None,
            "guidelines_block_id": None,
            "delegation_log_block_id": None,
            "warnings": warnings
        }
