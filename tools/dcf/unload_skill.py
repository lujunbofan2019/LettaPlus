import os
import json

from letta_client import Letta

# --- Constants ---
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
# Use the same env var name as the loader tool for consistency
STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")


def unload_skill(manifest_id: str, agent_id: str) -> dict:
    """Unload a previously loaded skill from a Letta agent.
         - Idempotent: if the state block or manifest entry is missing, returns success with a descriptive status and no error.
         - This expects the loader tool to have tracked resources in a JSON block labeled by SKILL_STATE_BLOCK_LABEL (default: "dcf_active_skills").

    Args:
        manifest_id (str):
            The `manifestId` of the skill to unload (must match the key used in the
            skill state block on the agent).
        agent_id (str):
            The target Letta agent ID.

    Returns:
        dict: Result object:
            {
              "status": str or None,   # Success summary (includes warning counts if any)
              "error": str or None     # Error string on failure; None on success
            }
    """
    status = None
    error_message = None
    warnings = []

    # Basic runtime type checks for clearer errors in tool-call contexts
    if not isinstance(manifest_id, str) or not manifest_id.strip():
        return {"status": None, "error": "TypeError: manifest_id must be a non-empty string"}
    if not isinstance(agent_id, str) or not agent_id.strip():
        return {"status": None, "error": "TypeError: agent_id must be a non-empty string"}

    try:
        # 0) Client + agent existence
        client = Letta(base_url=LETTA_BASE_URL)
        _ = client.agents.retrieve(agent_id)

        # 1) Load current state
        state = {}
        state_block_id = None

        try:
            blocks = client.agents.blocks.list(agent_id=agent_id)
            state_ref = next((b for b in blocks if getattr(b, "label", "") == STATE_BLOCK_LABEL), None)
            if state_ref:
                state_block_id = getattr(state_ref, "block_id", None) or getattr(state_ref, "id", None)
                if state_block_id:
                    sb_full = client.blocks.retrieve(block_id=state_block_id)
                    sb_val = getattr(sb_full, "value", "{}")
                    try:
                        state = json.loads(sb_val) if isinstance(sb_val, str) else (sb_val or {})
                        if not isinstance(state, dict):
                            warnings.append("State block value was not a dict; treating as empty.")
                            state = {}
                    except Exception:
                        warnings.append("Failed to decode state block JSON; treating as empty.")
                        state = {}
        except Exception as ex:
            # If we can't read state, we can't reliably unload
            raise RuntimeError("Failed to retrieve or parse skill state: %s" % ex)

        if not state_block_id:
            # Idempotent: nothing to do
            status = ("No skill state block ('%s') found on agent '%s'. "
                      "Assuming nothing to unload for manifest '%s'.") % (STATE_BLOCK_LABEL, agent_id, manifest_id)
            return {"status": status, "error": None}

        entry = state.get(manifest_id)
        if not entry:
            # Idempotent: nothing to do
            status = ("Manifest '%s' not recorded on agent '%s'. "
                      "Assuming already unloaded.") % (manifest_id, agent_id)
            return {"status": status, "error": None}

        # 2) Detach resources (best effort)
        skill_name = entry.get("skillName", "Unknown Skill")

        # Tools: support both shapes ("toolIds" preferred; fallback to "toolPlatformIds")
        tool_ids = (entry.get("toolIds") or entry.get("toolPlatformIds") or [])
        for tid in tool_ids:
            try:
                client.agents.tools.detach(agent_id=agent_id, tool_id=tid)
            except Exception as ex:
                warnings.append("Failed to detach tool %s: %s" % (tid, ex))

        # Data source blocks
        for bid in (entry.get("dataSourceBlockIds") or []):
            try:
                client.agents.blocks.detach(agent_id=agent_id, block_id=bid)
            except Exception as ex:
                warnings.append("Failed to detach data block %s: %s" % (bid, ex))
            try:
                client.blocks.delete(block_id=bid)
            except Exception:
                # Non-fatal: orphan block in platform; still proceed
                pass

        # Directive/memory blocks
        for bid in (entry.get("memoryBlockIds") or []):
            try:
                client.agents.blocks.detach(agent_id=agent_id, block_id=bid)
            except Exception as ex:
                warnings.append("Failed to detach memory block %s: %s" % (bid, ex))
            try:
                client.blocks.delete(block_id=bid)
            except Exception:
                pass

        # 3) Update or remove the state block
        try:
            # Remove this manifest entry
            if manifest_id in state:
                del state[manifest_id]

            if state:
                client.blocks.modify(block_id=state_block_id, value=json.dumps(state, indent=2))
            else:
                # No skills left → remove state block entirely
                try:
                    client.agents.blocks.detach(agent_id=agent_id, block_id=state_block_id)
                except Exception:
                    # If already detached, ignore
                    pass
                try:
                    client.blocks.delete(block_id=state_block_id)
                except Exception:
                    # If delete fails, keep it as dangling; warn but still succeed
                    warnings.append("Failed to delete empty state block %s" % state_block_id)
        except Exception as ex:
            warnings.append("Failed to update skill state: %s" % ex)

        # 4) Compose success status
        status = "Successfully unloaded skill '%s' (manifest %s) from agent %s." % (skill_name, manifest_id, agent_id)
        if warnings:
            status += " Warnings: %d." % len(warnings)
        return {"status": status, "error": None}

    except Exception as e:
        error_message = ("Failed to unload skill (manifest '%s') from agent '%s': %s: %s"
                         % (manifest_id, agent_id, e.__class__.__name__, e))
        if warnings:
            error_message += "\nAdditional warnings during cleanup:\n- " + "\n- ".join(warnings)
        return {"status": status, "error": error_message}
