from typing import Any, Dict
import os
from letta_client import Letta

# 2025.06.03.rc1
def resolve_agent_name_to_id(agent_name: str) -> Dict[str, Any]:
    """
    Resolve an agent's name to its unique agent Id, often as a prerequisite for the agent to call other tools.

    Args:
        agent_name: The name of the agent to look up (case-sensitive).

    Returns:
        dict: {"agent_id": str | None, "error": str | None}
    """
    agent_id_result: str | None = None
    error_msg: str | None = None
    agents_list: list = []

    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://letta:8283"))

        # --- 1. List all agents ---
        try:
            fetched_agents = client.agents.list()
            if hasattr(fetched_agents, '__iter__') and not isinstance(fetched_agents, str):
                 agents_list = list(fetched_agents)
            else:
                 error_msg = f"API did not return an iterable list of agents (type: {type(fetched_agents).__name__})."

        except Exception as e:
            error_msg = f"Failed to list agents from Letta server: {e.__class__.__name__}: {e}"

        # --- 2. Find agent by name using iteration and 'next' ---
        if not error_msg:
            try:
                matching_agent = next(
                    (agent for agent in agents_list if getattr(agent, 'name', None) == agent_name),
                    None
                )

                if matching_agent:
                    current_agent_id = getattr(matching_agent, 'id', None)
                    if current_agent_id and isinstance(current_agent_id, str):
                        agent_id_result = current_agent_id # Store the valid ID
                    else:
                        error_msg = f"Agent named '{agent_name}' found, but its ID is missing or invalid (ID found: {current_agent_id})."
            except Exception as e:
                 error_msg = f"Error occurred during agent search process: {e.__class__.__name__}"


    except Exception as e:
        error_msg = f"Critical error during execution: {e.__class__.__name__}: {e}"
        agent_id_result = None

    # --- 3. Return result ---
    if error_msg is not None:
        agent_id_result = None

    return {
        "agent_id": agent_id_result,
        "error": error_msg
    }
