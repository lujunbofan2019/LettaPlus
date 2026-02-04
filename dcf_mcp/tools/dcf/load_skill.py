from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")
MAX_TEXT_CONTENT_CHUNK_SIZE = int(os.getenv("SKILL_MAX_TEXT_CHARS", "4900"))


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


ALLOW_PYTHON_SOURCE = _env_flag("ALLOW_PYTHON_SOURCE_SKILLS", default=False)
ALLOW_MCP = _env_flag("ALLOW_MCP_SKILLS", default=True)
REGISTRY_PATH = os.getenv("SKILL_REGISTRY_PATH", "/app/generated/registry.json")


def _init_result() -> Dict[str, Any]:
    return {
        "ok": False,
        "exit_code": 4,
        "status": None,
        "error": None,
        "added": {"memory_block_ids": [], "tool_ids": [], "data_block_ids": []},
        "warnings": [],
    }


def _load_manifest(skill_manifest: str, out: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    candidate = skill_manifest.strip()
    if candidate.startswith("{") or candidate.startswith("["):
        text = skill_manifest
    else:
        if candidate.startswith("file://"):
            path = Path(candidate[7:])
        else:
            path = Path(candidate)
        try:
            text = Path(path).expanduser().read_text(encoding="utf-8")
        except Exception as exc:
            out["error"] = f"Failed to read manifest '{path}': {exc}"
            return None

    try:
        return json.loads(text)
    except Exception as exc:
        out["error"] = f"JSONDecodeError: {exc}"
        return None


def _load_registry() -> Tuple[Dict[str, Any], List[str]]:
    registry: Dict[str, Any] = {"servers": {}}
    warnings: List[str] = []

    if not os.path.exists(REGISTRY_PATH):
        warnings.append(
            f"Registry not found at {REGISTRY_PATH}; logical MCP servers may fail to resolve."
        )
        return registry, warnings

    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
            registry = json.load(fh)
    except Exception as exc:
        warnings.append(f"Registry load failed: {exc}")

    return registry, warnings


def _resolve_logical_server(
    server_id: str,
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    record = (registry.get("servers") or {}).get(server_id) or {}
    transport = (record.get("transport") or "").lower()
    if transport == "ws":
        return {"mode": "ws", "endpoint": record.get("endpoint")}
    if transport == "stdio":
        return {
            "mode": "stdio",
            "command": record.get("command"),
            "args": record.get("args") or [],
        }
    if transport in {"http", "streamable_http"}:
        return {
            "mode": "streamable_http",
            "endpoint": record.get("endpoint"),
            "path": record.get("path") or "/mcp",
            "headers": record.get("headers") or {},
        }
    return {}


def _metadata_for_physical(definition: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    endpoint = (definition.get("endpointUrl") or "").strip()
    if not endpoint:
        return None, "mcp_server definition missing endpointUrl"

    metadata = {
        "transport": "streamable_http",
        "endpoint": endpoint,
        "operationId": definition.get("operationId"),
    }
    if definition.get("openApiSpecUrl"):
        metadata["openApiSpecUrl"] = definition.get("openApiSpecUrl")
    return metadata, None


def _get_mcp_server_tools(client: Any, server_id: str, server_name: str) -> Set[str]:
    """Get tool names from an MCP server by its ID."""
    discovered: Set[str] = set()
    try:
        tools_response = client.mcp_servers.tools.list(server_id)
        for item in tools_response:
            name = getattr(item, "name", None)
            if isinstance(name, str) and name:
                discovered.add(name)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to list tools for MCP server '{server_name}' (id={server_id}): {exc}"
        )
    return discovered


def load_skill(skill_manifest: str, agent_id: str) -> Dict[str, Any]:
    """Load a skill manifest into a Letta agent (JSON string or file path).

    The loader merges the historical ``load_skill`` and ``load_skill_with_resolver``
    behaviours into a single tool while expanding the accepted manifest formats.
    ``skill_manifest`` may now be either the literal JSON content of a manifest
    **or** a filesystem path/URI pointing to the JSON file. When a path is supplied
    it may be absolute, relative to the working directory, or prefixed with ``file://``.

    The following operations mirror the legacy flow so existing planners keep the
    same expectations:

    1. Parse the manifest (and report JSON errors inline) before lazily importing
       the Letta SDK. Agent existence is verified prior to making mutations.
    2. Attach ``skillDirectives`` as a memory block when present.
    3. Attach required tools, supporting ``registered``, ``python_source`` (when
       enabled via ``ALLOW_PYTHON_SOURCE_SKILLS``), and ``mcp_server`` definitions.
       ``mcp_server`` entries may describe either a physical server (via
       ``endpointUrl``) or a logical server reference. Logical references are
       resolved through ``generated/registry.json`` (override with
       ``SKILL_REGISTRY_PATH``) to determine the actual transport/endpoint.
       The registry is generated from ``skills_src/registry.yaml`` by the
       ``yaml_to_registry`` tool.
    4. Attach ``text_content`` data sources chunked according to
       ``SKILL_MAX_TEXT_CHARS``.
    5. Update the per-agent bookkeeping block (labelled by
       ``SKILL_STATE_BLOCK_LABEL``) so we can detect duplicate loads and allow
       later removal flows to reverse the side effects.

    Args:
        skill_manifest: Either the raw JSON manifest string or a path/``file://``
            URI pointing to a manifest file on disk.
        agent_id: Target Letta agent identifier.

    Returns:
        dict: Status payload compatible with the legacy tool::

            {
              "ok": bool,
              "exit_code": int,         # 0 on success, 4 on error
              "status": str | None,
              "error": str | None,
              "added": {
                "memory_block_ids": list[str],
                "tool_ids": list[str],
                "data_block_ids": list[str],
              },
              "warnings": list[str],
            }

    Every failure mode is captured in the response; the function does not raise
    so that planner tool-calls can handle errors deterministically.
    """
    out = _init_result()

    if not isinstance(skill_manifest, str):
        out["error"] = "TypeError: skill_manifest must be a string"
        return out
    if not isinstance(agent_id, str):
        out["error"] = "TypeError: agent_id must be a string"
        return out

    manifest = _load_manifest(skill_manifest, out)
    if manifest is None:
        return out

    try:
        from letta_client import Letta  # type: ignore
    except Exception as exc:
        out["error"] = f"Letta SDK import error: {exc}"
        return out

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        client.agents.retrieve(agent_id)
    except Exception as exc:
        out["error"] = f"Agent retrieval error: {exc}"
        return out

    try:
        existing_blocks = client.agents.blocks.list(agent_id=agent_id)
        baseline_block_labels = {
            getattr(block, "block_id", None) or getattr(block, "id", None): getattr(block, "label", "")
            for block in existing_blocks
            if (getattr(block, "block_id", None) or getattr(block, "id", None))
        }
    except Exception:
        baseline_block_labels = {}

    manifest_id = manifest.get("manifestId")
    skill_name = manifest.get("skillName")
    skill_version = manifest.get("skillVersion")

    if not isinstance(manifest_id, str) or not manifest_id:
        out["error"] = "Manifest missing manifestId"
        return out
    if not isinstance(skill_name, str) or not skill_name:
        out["error"] = "Manifest missing skillName"
        return out
    if not isinstance(skill_version, str) or not skill_version:
        out["error"] = "Manifest missing skillVersion"
        return out

    # 1. Attach directives
    directives = manifest.get("skillDirectives") or ""
    created_memory_labels: Set[str] = set()
    created_data_labels: Set[str] = set()
    if directives:
        label = f"skill_directives_{skill_name}_{manifest_id}"
        try:
            block = client.blocks.create(label=label, value=directives)
            block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
            if not block_id:
                raise RuntimeError("No block id returned")
            client.agents.blocks.attach(agent_id=agent_id, block_id=block_id)
            out["added"]["memory_block_ids"].append(block_id)
            created_memory_labels.add(label)
        except Exception as exc:
            out["error"] = f"Failed to attach directives block: {exc}"
            return out

    # 2. Attach tools
    try:
        attached = client.agents.tools.list(agent_id=agent_id)
        attached_ids = {
            getattr(tool, "id", None) or getattr(tool, "tool_id", None) for tool in attached
        }
    except Exception:
        attached_ids = set()
    baseline_tool_ids = set(attached_ids)

    registry_cache: Optional[Dict[str, Any]] = None
    # Track known MCP servers: name -> server_id mapping
    known_mcp_servers: Dict[str, str] = {}
    try:
        existing_servers = client.mcp_servers.list()
        for srv in existing_servers:
            srv_name = getattr(srv, "server_name", None) or getattr(srv, "name", None)
            srv_id = getattr(srv, "id", None)
            if srv_name and srv_id:
                known_mcp_servers[srv_name] = srv_id
    except Exception:
        pass

    available_mcp_tools: Dict[str, Set[str]] = {}

    for requirement in (manifest.get("requiredTools") or []):
        if not isinstance(requirement, dict):
            continue
        definition = requirement.get("definition") or {}
        tool_name = (
            (requirement.get("toolName") or definition.get("toolName") or "").strip()
        )
        tool_type = (definition.get("type") or "").strip()

        try:
            if tool_type == "registered":
                platform_id = definition.get("platformToolId")
                if not platform_id:
                    raise ValueError("registered tool requires platformToolId")
                tool_obj = client.tools.retrieve(tool_id=platform_id)
                tool_id = getattr(tool_obj, "id", None)
                if tool_id and tool_id not in attached_ids:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                    out["added"]["tool_ids"].append(tool_id)
                    attached_ids.add(tool_id)

            elif tool_type == "python_source":
                if not ALLOW_PYTHON_SOURCE:
                    out["warnings"].append(
                        f"python_source for '{tool_name}' skipped (feature disabled)"
                    )
                    continue
                source = definition.get("sourceCode") or ""
                if not source:
                    raise ValueError("python_source requires sourceCode")
                raise NotImplementedError(
                    "Tool registration from python_source is environment-specific"
                )

            elif tool_type == "mcp_server":
                if not ALLOW_MCP:
                    out["warnings"].append(
                        f"mcp_server for '{tool_name}' skipped (feature disabled)"
                    )
                    continue

                server_id = (definition.get("serverId") or "").strip()
                metadata: Optional[Dict[str, Any]] = None
                server_name: Optional[str] = None

                if server_id:
                    if registry_cache is None:
                        registry_cache, registry_warnings = _load_registry()
                        out["warnings"].extend(registry_warnings)
                    resolved = _resolve_logical_server(server_id, registry_cache or {})
                    if not resolved:
                        out["warnings"].append(
                            f"mcp_server '{server_id}' could not be resolved; skipped"
                        )
                        continue
                    mode = resolved.get("mode")
                    if mode == "ws":
                        endpoint = resolved.get("endpoint")
                        if not endpoint:
                            out["warnings"].append(
                                f"mcp_server '{server_id}' missing ws endpoint; skipped"
                            )
                            continue
                        metadata = {
                            "transport": "ws",
                            "endpoint": endpoint,
                            "serverId": server_id,
                            "toolName": tool_name,
                        }
                    elif mode == "stdio":
                        command = resolved.get("command")
                        if not command:
                            out["warnings"].append(
                                f"mcp_server '{server_id}' missing stdio command; skipped"
                            )
                            continue
                        metadata = {
                            "transport": "stdio",
                            "command": command,
                            "args": resolved.get("args") or [],
                            "serverId": server_id,
                            "toolName": tool_name,
                        }
                    elif mode == "streamable_http":
                        endpoint = resolved.get("endpoint")
                        if not endpoint:
                            out["warnings"].append(
                                f"mcp_server '{server_id}' missing HTTP endpoint; skipped"
                            )
                            continue
                        metadata = {
                            "transport": "streamable_http",
                            "endpoint": endpoint,
                            "path": resolved.get("path") or "/mcp",
                            "headers": resolved.get("headers") or {},
                            "serverId": server_id,
                            "toolName": tool_name,
                        }
                    else:
                        out["warnings"].append(
                            f"mcp_server '{server_id}' uses unsupported transport '{mode}'; skipped"
                        )
                        continue
                    server_name = server_id
                else:
                    metadata, warn = _metadata_for_physical(definition)
                    if warn:
                        out["warnings"].append(f"{warn}; '{tool_name}' skipped")
                        continue
                    metadata["toolName"] = tool_name
                    base_name = (
                        tool_name
                        or definition.get("operationId")
                        or f"endpoint_tool_{len(known_mcp_servers) + 1}"
                    )
                    server_name = definition.get("serverName") or (
                        f"skill_{skill_name}_{base_name}"
                    )

                if not metadata:
                    continue

                transport = metadata.get("transport")
                try:
                    # Build config dict for the new mcp_servers API
                    config: Dict[str, Any] = {}

                    if transport == "streamable_http":
                        endpoint = metadata.get("endpoint") or ""
                        path = metadata.get("path")
                        if path:
                            server_url = urljoin(
                                endpoint.rstrip("/") + "/", path.lstrip("/")
                            )
                        else:
                            server_url = endpoint
                        config = {
                            "mcp_server_type": "streamable_http",
                            "server_url": server_url,
                        }
                        if metadata.get("headers"):
                            config["custom_headers"] = metadata.get("headers")
                    elif transport == "stdio":
                        command = metadata.get("command")
                        if not command:
                            raise ValueError(
                                f"mcp_server '{server_name}' missing command"
                            )
                        config = {
                            "mcp_server_type": "stdio",
                            "command": command,
                            "args": metadata.get("args") or [],
                        }
                    elif transport in {"ws", "sse"}:
                        endpoint = metadata.get("endpoint")
                        if not endpoint:
                            raise ValueError(
                                f"mcp_server '{server_name}' missing SSE endpoint"
                            )
                        config = {
                            "mcp_server_type": "sse",
                            "server_url": endpoint,
                        }
                    else:
                        raise ValueError(
                            f"Unsupported MCP transport '{transport}' for '{tool_name}'"
                        )

                    if not server_name:
                        server_name = f"skill_{skill_name}_{tool_name or 'tool'}"

                    # Create server if not already known
                    server_id = known_mcp_servers.get(server_name)
                    if not server_id:
                        created_server = client.mcp_servers.create(
                            server_name=server_name,
                            config=config,
                        )
                        server_id = getattr(created_server, "id", None)
                        if not server_id:
                            raise RuntimeError(
                                f"MCP server '{server_name}' creation did not return an id"
                            )
                        known_mcp_servers[server_name] = server_id
                        # Discover tools from newly created server
                        discovered = _get_mcp_server_tools(client, server_id, server_name)
                        if discovered:
                            available_mcp_tools[server_name] = discovered

                    # Get tools list if not already available
                    if server_name not in available_mcp_tools and server_id:
                        available_mcp_tools[server_name] = _get_mcp_server_tools(
                            client, server_id, server_name
                        )

                    target_tool_name = metadata.get("toolName") or tool_name
                    if not target_tool_name:
                        raise ValueError(
                            f"mcp_server entry missing toolName for '{server_name}'"
                        )

                    known_tools = available_mcp_tools.get(server_name, set())
                    if known_tools and target_tool_name not in known_tools:
                        raise RuntimeError(
                            f"MCP server '{server_name}' does not expose tool '{target_tool_name}'"
                        )

                    # Find the tool by name in the server's tool list
                    tool_id = None
                    if server_id:
                        tools_list = client.mcp_servers.tools.list(server_id)
                        for t in tools_list:
                            if getattr(t, "name", None) == target_tool_name:
                                tool_id = getattr(t, "id", None)
                                break

                    if not tool_id:
                        raise RuntimeError(
                            f"MCP tool '{target_tool_name}' not found on server '{server_name}'"
                        )

                    if tool_id not in attached_ids:
                        client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                        out["added"]["tool_ids"].append(tool_id)
                        attached_ids.add(tool_id)
                except Exception as exc:
                    out["error"] = f"Failed processing tool '{tool_name}': {exc}"
                    return out

            else:
                out["warnings"].append(
                    f"Unknown tool definition type '{tool_type}' for '{tool_name}'"
                )
        except NotImplementedError as exc:
            out["error"] = f"Failed processing tool '{tool_name}': {exc}"
            return out
        except Exception as exc:
            out["error"] = f"Failed processing tool '{tool_name}': {exc}"
            return out

    # 3. Attach data sources
    for data_source in (manifest.get("requiredDataSources") or []):
        if not isinstance(data_source, dict):
            continue
        source_id = (data_source.get("dataSourceId") or "").strip()
        content = data_source.get("content") or {}
        if content.get("type") != "text_content":
            out["warnings"].append(
                f"Unsupported data source type for {source_id}; only text_content is handled"
            )
            continue
        text = content.get("text") or ""
        if not text:
            continue
        chunks = [
            text[i : i + MAX_TEXT_CONTENT_CHUNK_SIZE]
            for i in range(0, len(text), MAX_TEXT_CONTENT_CHUNK_SIZE)
        ]
        base_label = f"skill_ds_{skill_name}_{source_id}"
        for index, chunk in enumerate(chunks, start=1):
            label = (
                base_label
                if len(chunks) == 1
                else f"{base_label}_chunk_{index}_of_{len(chunks)}"
            )
            try:
                block = client.blocks.create(label=label, value=chunk)
                block_id = getattr(block, "id", None) or getattr(block, "block_id", None)
                if not block_id:
                    raise RuntimeError("No block id returned for data source chunk")
                client.agents.blocks.attach(agent_id=agent_id, block_id=block_id)
                out["added"]["data_block_ids"].append(block_id)
                created_data_labels.add(label)
            except Exception as exc:
                out["error"] = (
                    f"Failed to attach data source '{source_id}' chunk {index}: {exc}"
                )
                return out

    # Refresh tool + block attachments to capture any IDs returned by the platform
    try:
        current_tools = client.agents.tools.list(agent_id=agent_id)
        current_tool_ids = {
            getattr(tool, "id", None) or getattr(tool, "tool_id", None)
            for tool in current_tools
            if getattr(tool, "id", None) or getattr(tool, "tool_id", None)
        }
    except Exception:
        current_tool_ids = set()

    for tool_id in sorted(current_tool_ids - baseline_tool_ids):
        if tool_id not in out["added"]["tool_ids"]:
            out["added"]["tool_ids"].append(tool_id)

    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
    except Exception as exc:
        out["error"] = f"State tracking error: {exc}"
        return out

    new_block_candidates: List[Tuple[str, str]] = []
    for block in blocks:
        block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
        if not block_id:
            continue
        label = getattr(block, "label", "")
        if block_id not in baseline_block_labels:
            new_block_candidates.append((block_id, label))
        baseline_block_labels.setdefault(block_id, label)

    for block_id, label in new_block_candidates:
        if block_id in out["added"]["memory_block_ids"] or block_id in out["added"]["data_block_ids"]:
            continue
        if label == STATE_BLOCK_LABEL:
            continue
        if label in created_memory_labels:
            out["added"]["memory_block_ids"].append(block_id)
            continue
        if label in created_data_labels or label.startswith("skill_ds_"):
            out["added"]["data_block_ids"].append(block_id)
        else:
            out["added"]["memory_block_ids"].append(block_id)

    out["added"]["memory_block_ids"] = list(dict.fromkeys(out["added"]["memory_block_ids"]))
    out["added"]["tool_ids"] = list(dict.fromkeys(out["added"]["tool_ids"]))
    out["added"]["data_block_ids"] = list(dict.fromkeys(out["added"]["data_block_ids"]))

    # 4. Update skill state
    try:
        state: Dict[str, Any] = {}
        state_block_id: Optional[str] = None
        created_state_block_id: Optional[str] = None
        for block in blocks:
            if getattr(block, "label", "") == STATE_BLOCK_LABEL:
                state_block_id = getattr(block, "block_id", None) or getattr(block, "id", None)
                if state_block_id:
                    existing = client.blocks.retrieve(block_id=state_block_id)
                    value = getattr(existing, "value", "{}")
                    if isinstance(value, str):
                        try:
                            state = json.loads(value)
                        except Exception:
                            state = {}
                    elif isinstance(value, dict):
                        state = value
                break
        if manifest_id in state:
            raise ValueError(
                f"Skill '{manifest_id}' already loaded on agent '{agent_id}'."
            )
        state_entry = {
            "skillName": skill_name,
            "skillVersion": skill_version,
            "memoryBlockIds": out["added"]["memory_block_ids"],
            "toolIds": out["added"]["tool_ids"],
            "dataSourceBlockIds": out["added"]["data_block_ids"],
        }
        state[manifest_id] = state_entry
        new_value = json.dumps(state, indent=2)
        if state_block_id:
            client.blocks.update(block_id=state_block_id, value=new_value)
        else:
            state_block = client.blocks.create(label=STATE_BLOCK_LABEL, value=new_value)
            state_block_id = getattr(state_block, "id", None) or getattr(state_block, "block_id", None)
            if not state_block_id:
                raise RuntimeError("Failed to create skill state block")
            client.agents.blocks.attach(agent_id=agent_id, block_id=state_block_id)
            created_state_block_id = state_block_id
            if state_block_id not in state_entry["memoryBlockIds"]:
                state_entry["memoryBlockIds"].append(state_block_id)
            final_value = json.dumps(state, indent=2)
            if final_value != new_value:
                client.blocks.update(block_id=state_block_id, value=final_value)
    except Exception as exc:
        out["error"] = f"State tracking error: {exc}"
        return out

    if created_state_block_id and created_state_block_id not in out["added"]["memory_block_ids"]:
        out["added"]["memory_block_ids"].append(created_state_block_id)

    out["ok"] = True
    out["exit_code"] = 0
    out["status"] = (
        f"Loaded skill '{skill_name}' v{skill_version} (manifest {manifest_id})"
    )
    return out