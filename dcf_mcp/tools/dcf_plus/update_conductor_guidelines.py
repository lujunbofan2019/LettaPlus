"""Update Conductor guidelines based on Strategist analysis."""

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timezone

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
GUIDELINES_BLOCK_LABEL = os.getenv("GUIDELINES_BLOCK_LABEL", "strategist_guidelines")


def update_conductor_guidelines(
    conductor_id: str,
    guidelines_json: Any = None,  # Accepts str or dict (Letta auto-parses)
    recommendation: Optional[str] = None,
    skill_preferences_json: Any = None,  # Accepts str or dict (Letta auto-parses)
    companion_scaling_json: Any = None,  # Accepts str or dict (Letta auto-parses)
    model_selection_json: Any = None,  # AMSP v1.1.0: Accepts str or dict
    clear_guidelines: bool = False,
) -> Dict[str, Any]:
    """Update Conductor guidelines based on Strategist analysis.

    The Strategist uses this to publish recommendations and best practices
    to the Conductor. Guidelines are stored in a dedicated memory block
    attached to the Conductor.

    Args:
        conductor_id: Conductor's agent ID.
        guidelines_json: Full guidelines object to set (replaces existing).
        recommendation: Single recommendation to append to guidelines.
        skill_preferences_json: JSON object mapping task types to preferred skills.
        companion_scaling_json: JSON object with companion scaling recommendations.
        model_selection_json: AMSP v1.1.0 - JSON object with model selection recommendations:
            {
                "default_tier": 0-3,
                "task_type_tiers": {"research": 1, "analysis": 2, ...},
                "skill_tier_overrides": {"skill://...": 2, ...},
                "escalation_threshold": 0.15,
                "cost_optimization": "balanced" | "performance" | "economy"
            }
        clear_guidelines: If True, clear all existing guidelines.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "conductor_id": str,
            "guidelines_block_id": str | None,
            "updated_fields": List[str]
        }
    """
    # Lazy imports
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "conductor_id": conductor_id,
            "guidelines_block_id": None,
            "updated_fields": [],
        }

    # Parse input JSONs (handles both string and pre-parsed dict from Letta)
    guidelines_data: Optional[Dict[str, Any]] = None
    if guidelines_json:
        if isinstance(guidelines_json, dict):
            guidelines_data = guidelines_json
        elif isinstance(guidelines_json, str):
            try:
                parsed = json.loads(guidelines_json)
                if isinstance(parsed, dict):
                    guidelines_data = parsed
            except Exception as e:
                return {
                    "status": None,
                    "error": f"Failed to parse guidelines_json: {e}",
                    "conductor_id": conductor_id,
                    "guidelines_block_id": None,
                    "updated_fields": [],
                }

    skill_preferences: Optional[Dict[str, Any]] = None
    if skill_preferences_json:
        if isinstance(skill_preferences_json, dict):
            skill_preferences = skill_preferences_json
        elif isinstance(skill_preferences_json, str):
            try:
                parsed = json.loads(skill_preferences_json)
                if isinstance(parsed, dict):
                    skill_preferences = parsed
            except Exception as e:
                return {
                    "status": None,
                    "error": f"Failed to parse skill_preferences_json: {e}",
                "conductor_id": conductor_id,
                "guidelines_block_id": None,
                "updated_fields": [],
            }

    companion_scaling: Optional[Dict[str, Any]] = None
    if companion_scaling_json:
        if isinstance(companion_scaling_json, dict):
            companion_scaling = companion_scaling_json
        elif isinstance(companion_scaling_json, str):
            try:
                parsed = json.loads(companion_scaling_json)
                if isinstance(parsed, dict):
                    companion_scaling = parsed
            except Exception as e:
                return {
                    "status": None,
                    "error": f"Failed to parse companion_scaling_json: {e}",
                    "conductor_id": conductor_id,
                    "guidelines_block_id": None,
                    "updated_fields": [],
                }

    # AMSP v1.1.0: Parse model selection guidelines
    model_selection: Optional[Dict[str, Any]] = None
    if model_selection_json:
        if isinstance(model_selection_json, dict):
            model_selection = model_selection_json
        elif isinstance(model_selection_json, str):
            try:
                parsed = json.loads(model_selection_json)
                if isinstance(parsed, dict):
                    model_selection = parsed
            except Exception as e:
                return {
                    "status": None,
                    "error": f"Failed to parse model_selection_json: {e}",
                    "conductor_id": conductor_id,
                    "guidelines_block_id": None,
                    "updated_fields": [],
                }

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "conductor_id": conductor_id,
            "guidelines_block_id": None,
            "updated_fields": [],
        }

    # Find or create guidelines block
    guidelines_block_id = None
    current_guidelines: Dict[str, Any] = {
        "recommendations": [],
        "skill_preferences": {},
        "companion_scaling": {
            "min_companions": 1,
            "max_companions": 5,
            "scale_up_threshold": 3,  # pending tasks
            "scale_down_threshold": 0,  # idle companions
        },
        "model_selection": {  # AMSP v1.1.0
            "default_tier": 0,
            "task_type_tiers": {},
            "skill_tier_overrides": {},
            "escalation_threshold": 0.15,
            "cost_optimization": "balanced",
        },
        "updated_at": None,
        "update_count": 0,
    }

    try:
        blocks = client.agents.blocks.list(agent_id=conductor_id)
        for block in blocks:
            if getattr(block, "label", "") == GUIDELINES_BLOCK_LABEL:
                guidelines_block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                if guidelines_block_id:
                    full_block = client.blocks.retrieve(block_id=guidelines_block_id)
                    value = getattr(full_block, "value", "{}")
                    if isinstance(value, str):
                        try:
                            current_guidelines = json.loads(value)
                        except Exception:
                            pass
                    elif isinstance(value, dict):
                        current_guidelines = value
                break
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to access Conductor blocks: {e}",
            "conductor_id": conductor_id,
            "guidelines_block_id": None,
            "updated_fields": [],
        }

    # Create block if it doesn't exist
    if not guidelines_block_id:
        try:
            block = client.blocks.create(
                label=GUIDELINES_BLOCK_LABEL,
                value=json.dumps(current_guidelines),
                limit=8000,
            )
            guidelines_block_id = getattr(block, "id", None)

            # Attach to Conductor
            if guidelines_block_id:
                client.agents.blocks.attach(agent_id=conductor_id, block_id=guidelines_block_id)
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to create guidelines block: {e}",
                "conductor_id": conductor_id,
                "guidelines_block_id": None,
                "updated_fields": [],
            }

    updated_fields: List[str] = []

    # Apply updates
    if clear_guidelines:
        current_guidelines = {
            "recommendations": [],
            "skill_preferences": {},
            "companion_scaling": current_guidelines.get("companion_scaling", {}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "update_count": current_guidelines.get("update_count", 0) + 1,
        }
        updated_fields.append("cleared")

    elif guidelines_data:
        # Replace with provided guidelines
        current_guidelines = {
            **guidelines_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "update_count": current_guidelines.get("update_count", 0) + 1,
        }
        updated_fields.append("guidelines")

    else:
        # Incremental updates
        if recommendation:
            recommendations = current_guidelines.get("recommendations", [])
            recommendations.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "text": recommendation,
            })
            # Keep last 20 recommendations
            current_guidelines["recommendations"] = recommendations[-20:]
            updated_fields.append("recommendations")

        if skill_preferences:
            existing_prefs = current_guidelines.get("skill_preferences", {})
            existing_prefs.update(skill_preferences)
            current_guidelines["skill_preferences"] = existing_prefs
            updated_fields.append("skill_preferences")

        if companion_scaling:
            existing_scaling = current_guidelines.get("companion_scaling", {})
            existing_scaling.update(companion_scaling)
            current_guidelines["companion_scaling"] = existing_scaling
            updated_fields.append("companion_scaling")

        # AMSP v1.1.0: Update model selection guidelines
        if model_selection:
            existing_model_sel = current_guidelines.get("model_selection", {})
            existing_model_sel.update(model_selection)
            current_guidelines["model_selection"] = existing_model_sel
            updated_fields.append("model_selection")

        current_guidelines["updated_at"] = datetime.now(timezone.utc).isoformat()
        current_guidelines["update_count"] = current_guidelines.get("update_count", 0) + 1

    # Write back to block
    try:
        client.blocks.modify(block_id=guidelines_block_id, value=json.dumps(current_guidelines))
    except AttributeError:
        try:
            client.blocks.update(block_id=guidelines_block_id, value=json.dumps(current_guidelines))
        except Exception as e:
            return {
                "status": None,
                "error": f"Failed to update guidelines block: {e}",
                "conductor_id": conductor_id,
                "guidelines_block_id": guidelines_block_id,
                "updated_fields": [],
            }
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to update guidelines block: {e}",
            "conductor_id": conductor_id,
            "guidelines_block_id": guidelines_block_id,
            "updated_fields": [],
        }

    return {
        "status": f"Updated Conductor guidelines: {', '.join(updated_fields)}" if updated_fields else "No changes made",
        "error": None,
        "conductor_id": conductor_id,
        "guidelines_block_id": guidelines_block_id,
        "updated_fields": updated_fields,
    }
