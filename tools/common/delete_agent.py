import os
from letta_client import Letta

# 2025.06.03.rc1
def delete_agent(agent_name: str) -> dict:
    """
    Delete a Letta agent by exact name.

    Args:
        agent_name: Exact name of the agent to remove.

    Returns:
        dict: {"deleted_agent_id": str | None, "error": str | None}
    """
    deleted_id: str | None = None
    error_msg: str | None = None
    agent_id_to_delete: str | None = None

    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))

        # --- 1. Find Agent ID ---
        try:
            all_agents = client.agents.list()
            target_agent = next((ag for ag in all_agents if getattr(ag, 'name', None) == agent_name), None)

            if target_agent:
                agent_id_to_delete = getattr(target_agent, 'id', None)
                if not agent_id_to_delete:
                    error_msg = f"Agent '{agent_name}' found but lacks an ID."
        except Exception as e:
            error_msg = f"Error listing/finding agent '{agent_name}': {e.__class__.__name__}"

        # --- 2. Delete Agent (if ID found and no prior error) ---
        if agent_id_to_delete and not error_msg:
            try:
                client.agents.delete(agent_id=agent_id_to_delete)
                deleted_id = agent_id_to_delete # Mark success
            except Exception as e:
                deleted_id = None
                error_msg = f"Error deleting agent ID '{agent_id_to_delete}': {e.__class__.__name__}"

        # --- 3. Set 'Not Found' error if applicable ---
        elif not agent_id_to_delete and not error_msg:
             error_msg = f"Agent '{agent_name}' not found."

    except Exception as e:
        # Catch-all for client initialization or other critical errors
        error_msg = f"Critical error during execution: {e.__class__.__name__}: {e}"
        deleted_id = None # Ensure deletion is marked as failed on critical error

    # --- 4. Return concise result ---
    return {
        "deleted_agent_id": deleted_id,
        "error": error_msg
    }