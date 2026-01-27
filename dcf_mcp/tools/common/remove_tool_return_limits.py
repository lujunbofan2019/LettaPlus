from typing import Any, Dict
import os
from letta_client import Letta

# 2025.06.03.rc1
def remove_tool_return_limits(agent_id: str) -> Dict[str, Any]:
    """
    Sets the return_char_limit to 60,000 for all tools attached to a specific Letta agent.

    Args:
        agent_id: The identifier of the Letta agent whose tools to update.

    Returns:
        dict: {"updated_count": int | None, "error": str | None}
    """
    updated_count: int = 0
    error_msg: str | None = None
    agent_tools: list = []

    try:
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://letta:8283"))

        # --- 1. List tools registered to the agent ---
        try:
            fetched_tools = client.agents.tools.list(agent_id=agent_id)
            if hasattr(fetched_tools, '__iter__') and not isinstance(fetched_tools, str):
                 agent_tools = list(fetched_tools)
            else:
                 error_msg = f"API did not return an iterable list of tools for agent '{agent_id}' (type: {type(fetched_tools).__name__})."

        except Exception as e:
            error_msg = f"Failed to list tools for agent '{agent_id}': {e.__class__.__name__}: {e}"

        # --- 2. Iterate and modify each tool's limit ---
        if not error_msg:
            if not agent_tools:
                 pass
            else:
                 for tool in agent_tools:
                      tool_id = None
                      try:
                           tool_id = getattr(tool, 'id', None) or getattr(tool, 'tool_id', None)
                           if not tool_id or not isinstance(tool_id, str):
                                raise ValueError(f"Missing or invalid tool ID for tool entry: {str(tool)[:100]}...")
                           client.tools.update(
                               tool_id=tool_id,
                               return_char_limit=60000
                           )
                           updated_count += 1
                      except Exception as e:
                           error_msg = f"Error processing tool (ID: '{tool_id or 'unknown'}'): {e.__class__.__name__}: {e}"
                           break

    except Exception as e:
        error_msg = f"Critical error during execution: {e.__class__.__name__}: {e}"
        updated_count = None

    # --- 3. Return result ---
    final_count_to_return = updated_count if error_msg is None else None

    if error_msg is not None:
         final_count_to_return = None

    return {
        "updated_count": final_count_to_return,
        "error": error_msg
    }
