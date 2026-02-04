"""Utility to get agent tags via HTTP API.

The letta_client library doesn't properly parse the 'tags' field from API responses,
returning empty lists even when agents have tags. This utility provides a workaround
by fetching tags directly via the HTTP API.
"""

from typing import List
import os
import json
import urllib.request
import urllib.error

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def get_agent_tags(agent_id: str, base_url: str = None) -> List[str]:
    """Get agent tags via HTTP API (letta_client doesn't parse tags correctly).

    Args:
        agent_id: The agent's UUID.
        base_url: Optional Letta API base URL. Defaults to LETTA_BASE_URL env var.

    Returns:
        List of tag strings. Returns empty list on error.

    Example:
        >>> tags = get_agent_tags("agent-abc123...")
        >>> print(tags)
        ['role:companion', 'session:test-001', 'status:idle']
    """
    url_base = base_url or LETTA_BASE_URL
    try:
        url = f"{url_base}/v1/agents/{agent_id}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
            return data.get("tags", []) or []
    except urllib.error.URLError:
        return []
    except Exception:
        return []
