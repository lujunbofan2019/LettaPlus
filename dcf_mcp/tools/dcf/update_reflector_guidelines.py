from typing import Any, Dict
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
REFLECTOR_GUIDELINES_BLOCK_LABEL = "reflector_guidelines"
MAX_RECENT_INSIGHTS = 10


def update_reflector_guidelines(
    planner_agent_id: str,
    guidelines_json: str = None,
    add_skill_recommendation: str = None,
    add_workflow_pattern: str = None,
    add_user_intent_tip: str = None,
    add_warning: str = None,
    add_insight: str = None,
    merge_mode: bool = True
) -> Dict[str, Any]:
    """Update the reflector_guidelines block for a Planner agent.

    This tool allows the Reflector to provide actionable guidance to the Planner.
    Guidelines can be updated in bulk (via guidelines_json) or incrementally
    (via add_* parameters).

    Guidelines Structure:
    {
        "last_updated": "ISO-8601",
        "revision": N,
        "guidelines": {
            "skill_recommendations": [...],
            "workflow_patterns": [...],
            "user_intent_tips": [...],
            "warnings": [...]
        },
        "recent_insights": [...]
    }

    Args:
        planner_agent_id: The Planner agent's UUID.
        guidelines_json: Full guidelines object to set (if merge_mode=False) or merge (if merge_mode=True).
        add_skill_recommendation: JSON string of a skill recommendation to add.
        add_workflow_pattern: JSON string of a workflow pattern to add.
        add_user_intent_tip: JSON string of a user intent tip to add.
        add_warning: JSON string of a warning to add.
        add_insight: JSON string of a recent insight to add.
        merge_mode: If True, merge with existing guidelines. If False, replace entirely.

    Returns:
        dict: {
            "status": str or None,
            "error": str or None,
            "planner_agent_id": str,
            "guidelines_block_id": str or None,
            "revision": int or None,
            "warnings": list
        }
    """
    warnings = []

    if not isinstance(planner_agent_id, str) or not planner_agent_id.strip():
        return {
            "status": None,
            "error": "planner_agent_id must be a non-empty string",
            "planner_agent_id": planner_agent_id,
            "guidelines_block_id": None,
            "revision": None,
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
            "guidelines_block_id": None,
            "revision": None,
            "warnings": []
        }

    try:
        client = Letta(base_url=LETTA_BASE_URL)

        # Find guidelines block on Planner
        planner_blocks = client.agents.blocks.list(agent_id=planner_agent_id)
        guidelines_block_id = None

        for block in planner_blocks:
            if getattr(block, "label", "") == REFLECTOR_GUIDELINES_BLOCK_LABEL:
                guidelines_block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                break

        if not guidelines_block_id:
            return {
                "status": None,
                "error": f"No reflector_guidelines block found on Planner '{planner_agent_id}'. "
                        "Use register_reflector first to establish the relationship.",
                "planner_agent_id": planner_agent_id,
                "guidelines_block_id": None,
                "revision": None,
                "warnings": []
            }

        # Load existing guidelines
        full_block = client.blocks.retrieve(block_id=guidelines_block_id)
        existing_value = getattr(full_block, "value", "{}")
        try:
            existing = json.loads(existing_value) if isinstance(existing_value, str) else existing_value
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
            warnings.append("Existing guidelines were invalid JSON; starting fresh")

        # Parse new guidelines if provided
        new_guidelines = None
        if guidelines_json:
            try:
                new_guidelines = json.loads(guidelines_json)
                if not isinstance(new_guidelines, dict):
                    new_guidelines = None
                    warnings.append("guidelines_json was not a JSON object; ignored")
            except Exception as e:
                warnings.append(f"guidelines_json parse error: {e}; ignored")

        # Start with existing or new base
        if merge_mode and existing:
            result = existing.copy()
        elif new_guidelines:
            result = new_guidelines.copy()
        else:
            result = {}

        # Ensure structure
        if "guidelines" not in result:
            result["guidelines"] = {}
        guidelines_section = result["guidelines"]
        if "skill_recommendations" not in guidelines_section:
            guidelines_section["skill_recommendations"] = []
        if "workflow_patterns" not in guidelines_section:
            guidelines_section["workflow_patterns"] = []
        if "user_intent_tips" not in guidelines_section:
            guidelines_section["user_intent_tips"] = []
        if "warnings" not in guidelines_section:
            guidelines_section["warnings"] = []
        if "recent_insights" not in result:
            result["recent_insights"] = []

        # Merge new guidelines into existing
        if merge_mode and new_guidelines and "guidelines" in new_guidelines:
            for key in ["skill_recommendations", "workflow_patterns", "user_intent_tips", "warnings"]:
                if key in new_guidelines["guidelines"]:
                    # Add new items, avoid duplicates based on simple string comparison
                    existing_items = [json.dumps(x, sort_keys=True) for x in guidelines_section.get(key, [])]
                    for item in new_guidelines["guidelines"].get(key, []):
                        item_str = json.dumps(item, sort_keys=True)
                        if item_str not in existing_items:
                            guidelines_section[key].append(item)

        # Process incremental additions
        def parse_and_add(json_str, target_list, item_name):
            if not json_str:
                return
            try:
                item = json.loads(json_str)
                target_list.append(item)
            except Exception as e:
                warnings.append(f"Failed to parse {item_name}: {e}")

        parse_and_add(add_skill_recommendation, guidelines_section["skill_recommendations"], "skill_recommendation")
        parse_and_add(add_workflow_pattern, guidelines_section["workflow_patterns"], "workflow_pattern")
        parse_and_add(add_user_intent_tip, guidelines_section["user_intent_tips"], "user_intent_tip")
        parse_and_add(add_warning, guidelines_section["warnings"], "warning")

        # Add insight to recent_insights (rolling window)
        if add_insight:
            try:
                insight = json.loads(add_insight)
                result["recent_insights"].insert(0, insight)
                # Keep only most recent
                result["recent_insights"] = result["recent_insights"][:MAX_RECENT_INSIGHTS]
            except Exception as e:
                warnings.append(f"Failed to parse insight: {e}")

        # Update metadata
        result["last_updated"] = datetime.now(timezone.utc).isoformat()
        result["revision"] = (existing.get("revision", 0) or 0) + 1

        # Write back
        result_json = json.dumps(result, indent=2)
        client.blocks.update(block_id=guidelines_block_id, value=result_json)

        return {
            "status": f"Updated guidelines for Planner '{planner_agent_id}' (revision {result['revision']})",
            "error": None,
            "planner_agent_id": planner_agent_id,
            "guidelines_block_id": guidelines_block_id,
            "revision": result["revision"],
            "warnings": warnings
        }

    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to update guidelines: {e.__class__.__name__}: {e}",
            "planner_agent_id": planner_agent_id,
            "guidelines_block_id": None,
            "revision": None,
            "warnings": warnings
        }
