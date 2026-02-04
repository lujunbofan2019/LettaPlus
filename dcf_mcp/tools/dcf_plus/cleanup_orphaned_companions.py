"""Clean up orphaned Companion agents that were not properly dismissed.

This utility helps clean up Companions left behind due to:
- Test failures before cleanup phase
- Ad-hoc testing without proper finalize_session calls
- Sessions that lost track of their session_context_block_id
"""

from typing import Any, Dict, List, Optional
import os
import json

from tools.common.get_agent_tags import get_agent_tags as _get_agent_tags

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


def cleanup_orphaned_companions(
    session_id: Optional[str] = None,
    name_pattern: Optional[str] = None,
    include_tagless: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Clean up orphaned Companion agents.

    This function finds and optionally deletes Companion agents that match
    the specified criteria. Use dry_run=True (default) to preview what
    would be deleted before actually deleting.

    Args:
        session_id: If provided, only clean up Companions from this session.
                   If None, finds Companions from ALL sessions.
        name_pattern: If provided, only clean up Companions whose name contains
                     this substring (e.g., "test", "e2e", "companion").
        include_tagless: If True, also find agents that look like Companions
                        by name but lack proper tags (e.g., missing role:companion).
        dry_run: If True (default), only report what would be deleted without
                actually deleting. Set to False to perform actual deletion.

    Returns:
        dict: {
            "status": str | None,
            "error": str | None,
            "dry_run": bool,
            "companions_found": List[dict],  # [{id, name, session, tags}]
            "companions_deleted": List[str],  # Only populated if dry_run=False
            "warnings": List[str]
        }

    Examples:
        # Preview orphaned companions from a specific session
        result = cleanup_orphaned_companions(session_id="test-session-001", dry_run=True)

        # Delete all companions with "test" in the name
        result = cleanup_orphaned_companions(name_pattern="test", dry_run=False)

        # Find all companions including those with broken tags
        result = cleanup_orphaned_companions(include_tagless=True, dry_run=True)
    """
    # Lazy imports
    try:
        from letta_client import Letta
    except Exception as e:
        return {
            "status": None,
            "error": f"Missing dependency: letta_client not importable: {e}",
            "dry_run": dry_run,
            "companions_found": [],
            "companions_deleted": [],
            "warnings": [],
        }

    warnings: List[str] = []
    companions_found: List[Dict[str, Any]] = []
    companions_deleted: List[str] = []

    # Initialize Letta client
    try:
        client = Letta(base_url=LETTA_BASE_URL)
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to initialize Letta client: {e}",
            "dry_run": dry_run,
            "companions_found": [],
            "companions_deleted": [],
            "warnings": [],
        }

    # List all agents
    try:
        all_agents = client.agents.list()
    except Exception as e:
        return {
            "status": None,
            "error": f"Failed to list agents: {e}",
            "dry_run": dry_run,
            "companions_found": [],
            "companions_deleted": [],
            "warnings": [],
        }

    # Find matching companions
    for agent in all_agents:
        agent_id = getattr(agent, "id", None)
        agent_name = getattr(agent, "name", "")
        if not agent_id:
            continue

        tags = _get_agent_tags(agent_id)

        # Check if this is a companion by tags
        is_companion_by_tag = "role:companion" in tags

        # Check if this looks like a companion by name
        is_companion_by_name = (
            "companion" in agent_name.lower()
            or agent_name.startswith("e2e-")
            or "-companion" in agent_name.lower()
        )

        # Determine if we should include this agent
        should_include = False

        if is_companion_by_tag:
            # Properly tagged companion
            if session_id:
                # Filter by session
                if f"session:{session_id}" in tags:
                    should_include = True
            else:
                # Include all tagged companions
                should_include = True
        elif include_tagless and is_companion_by_name:
            # Looks like a companion but missing proper tags
            should_include = True
            warnings.append(f"Agent '{agent_name}' looks like a Companion but missing role:companion tag")

        # Apply name pattern filter
        if should_include and name_pattern:
            if name_pattern.lower() not in agent_name.lower():
                should_include = False

        if should_include:
            # Extract session from tags
            agent_session = None
            for tag in tags:
                if tag.startswith("session:"):
                    agent_session = tag[8:]
                    break

            companions_found.append({
                "id": agent_id,
                "name": agent_name,
                "session": agent_session,
                "tags": tags,
            })

    # Delete if not dry run
    if not dry_run and companions_found:
        try:
            from .dismiss_companion import dismiss_companion
            use_dismiss = True
        except ImportError:
            use_dismiss = False
            warnings.append("dismiss_companion not available, using direct delete")

        for companion in companions_found:
            companion_id = companion["id"]
            companion_name = companion["name"]
            try:
                if use_dismiss:
                    result = dismiss_companion(
                        companion_id=companion_id,
                        unload_skills=True,
                        detach_shared_blocks=True,
                    )
                    if result.get("error"):
                        warnings.append(f"Failed to dismiss {companion_name}: {result['error']}")
                    else:
                        companions_deleted.append(companion_id)
                else:
                    client.agents.delete(agent_id=companion_id)
                    companions_deleted.append(companion_id)
            except Exception as e:
                warnings.append(f"Error deleting {companion_name}: {e}")

    # Build status message
    if dry_run:
        status = f"[DRY RUN] Found {len(companions_found)} Companion(s) that would be deleted"
    else:
        status = f"Deleted {len(companions_deleted)}/{len(companions_found)} Companion(s)"

    return {
        "status": status,
        "error": None,
        "dry_run": dry_run,
        "companions_found": companions_found,
        "companions_deleted": companions_deleted,
        "warnings": warnings,
    }
