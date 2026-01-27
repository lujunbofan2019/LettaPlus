from typing import Any, Dict, List
import os
import json

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")

# Blocks that are considered shareable for reflection
SHAREABLE_BLOCK_LABELS = {
    "persona",           # Agent persona/instructions
    "human",             # User information
    "system",            # System context
    "archival_memory",   # Long-term archival
    "working_context",   # Current working context
    "reflector_guidelines",  # Guidelines block (bidirectional)
    "reflector_registration",  # Registration info
}

# Blocks that should NOT be shared (security/privacy)
EXCLUDED_BLOCK_LABELS = {
    "dcf_active_skills",  # Internal skill tracking
    "secrets",            # Credentials
    "api_keys",           # API keys
}


def read_shared_memory_blocks(
    planner_agent_id: str,
    reflector_agent_id: str = None,
    include_labels: List[str] = None,
    exclude_labels: List[str] = None,
    include_all: bool = False
) -> Dict[str, Any]:
    """Read memory blocks from a Planner agent for reflection analysis.

    This tool allows a Reflector to access the Planner's memory blocks
    for analysis and insight derivation. By default, only shareable blocks
    are returned (persona, archival_memory, working_context, etc.).

    Security: The tool verifies that the caller (reflector_agent_id) is
    registered as the Planner's companion before allowing access.

    Args:
        planner_agent_id: The Planner agent's UUID.
        reflector_agent_id: The Reflector agent's UUID (for verification).
                           If not provided, registration is not verified.
        include_labels: Optional list of specific block labels to include.
                       Overrides default shareable list if provided.
        exclude_labels: Optional list of block labels to exclude.
        include_all: If True, include all blocks except security-excluded ones.
                    Use with caution.

    Returns:
        dict: {
            "status": str or None,
            "error": str or None,
            "planner_agent_id": str,
            "blocks": [
                {
                    "block_id": str,
                    "label": str,
                    "value": str,
                    "created_at": str or None,
                    "char_count": int
                }, ...
            ],
            "block_count": int,
            "warnings": list
        }
    """
    warnings = []

    if not isinstance(planner_agent_id, str) or not planner_agent_id.strip():
        return {
            "status": None,
            "error": "planner_agent_id must be a non-empty string",
            "planner_agent_id": planner_agent_id,
            "blocks": [],
            "block_count": 0,
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
            "blocks": [],
            "block_count": 0,
            "warnings": []
        }

    try:
        client = Letta(base_url=LETTA_BASE_URL)

        # Verify Planner exists
        try:
            client.agents.retrieve(planner_agent_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Planner agent not found: {e}",
                "planner_agent_id": planner_agent_id,
                "blocks": [],
                "block_count": 0,
                "warnings": []
            }

        # Verify Reflector registration if reflector_agent_id provided
        if reflector_agent_id:
            planner_blocks = client.agents.blocks.list(agent_id=planner_agent_id)
            is_registered = False
            for block in planner_blocks:
                if getattr(block, "label", "") == "reflector_registration":
                    block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                    if block_id:
                        full_block = client.blocks.retrieve(block_id=block_id)
                        value = getattr(full_block, "value", "{}")
                        try:
                            reg_data = json.loads(value) if isinstance(value, str) else value
                            if reg_data.get("reflector_agent_id") == reflector_agent_id:
                                is_registered = True
                        except Exception:
                            pass
                    break

            if not is_registered:
                return {
                    "status": None,
                    "error": f"Reflector '{reflector_agent_id}' is not registered with Planner '{planner_agent_id}'",
                    "planner_agent_id": planner_agent_id,
                    "blocks": [],
                    "block_count": 0,
                    "warnings": ["Use register_reflector to establish the companion relationship first"]
                }

        # Determine which labels to include
        if include_labels:
            allowed_labels = set(include_labels)
        elif include_all:
            allowed_labels = None  # Will filter by exclusion only
        else:
            allowed_labels = SHAREABLE_BLOCK_LABELS.copy()

        # Determine exclusions
        exclusions = EXCLUDED_BLOCK_LABELS.copy()
        if exclude_labels:
            exclusions.update(exclude_labels)

        # Fetch blocks
        blocks_list = client.agents.blocks.list(agent_id=planner_agent_id)
        result_blocks = []

        for block in blocks_list:
            label = getattr(block, "label", "")
            block_id = getattr(block, "block_id", None) or getattr(block, "id", None)

            # Skip if in exclusion list
            if label in exclusions:
                continue

            # Skip if not in allowed list (when allowed_labels is defined)
            if allowed_labels is not None and label not in allowed_labels:
                continue

            if not block_id:
                continue

            # Fetch full block content
            try:
                full_block = client.blocks.retrieve(block_id=block_id)
                value = getattr(full_block, "value", "")
                created_at = getattr(full_block, "created_at", None)
                if created_at and hasattr(created_at, "isoformat"):
                    created_at = created_at.isoformat()
                elif created_at:
                    created_at = str(created_at)

                result_blocks.append({
                    "block_id": block_id,
                    "label": label,
                    "value": value if isinstance(value, str) else json.dumps(value),
                    "created_at": created_at,
                    "char_count": len(value) if isinstance(value, str) else len(json.dumps(value))
                })
            except Exception as e:
                warnings.append(f"Failed to read block '{label}' ({block_id}): {e}")

        return {
            "status": f"Retrieved {len(result_blocks)} memory block(s) from Planner '{planner_agent_id}'",
            "error": None,
            "planner_agent_id": planner_agent_id,
            "blocks": result_blocks,
            "block_count": len(result_blocks),
            "warnings": warnings
        }

    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to read memory blocks: {e.__class__.__name__}: {e}",
            "planner_agent_id": planner_agent_id,
            "blocks": [],
            "block_count": 0,
            "warnings": warnings
        }
