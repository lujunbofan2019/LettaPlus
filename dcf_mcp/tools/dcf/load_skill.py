from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
STATE_BLOCK_LABEL = os.getenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")
MAX_TEXT_CONTENT_CHUNK_SIZE = int(os.getenv("SKILL_MAX_TEXT_CHARS", "4900"))

ALLOW_PYTHON_SOURCE = os.getenv("ALLOW_PYTHON_SOURCE_SKILLS", "0") == "1"
ALLOW_MCP = os.getenv("ALLOW_MCP_SKILLS", "0") == "1"
REGISTRY_PATH = os.getenv("SKILL_REGISTRY_PATH", "skills_src/registry.json")


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


def load_skill(skill_manifest: str, agent_id: str) -> Dict[str, Any]:
    """Load a skill manifest (JSON string or file path) into a Letta agent."""
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
    if directives:
        label = f"skill_directives_{skill_name}_{manifest_id}"
        try:
            block = client.blocks.create(label=label, value=directives)
            block_id = getattr(block, "id", None)
            if not block_id:
                raise RuntimeError("No block id returned")
            client.agents.blocks.attach(agent_id=agent_id, block_id=block_id)
            out["added"]["memory_block_ids"].append(block_id)
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

    registry_cache: Optional[Dict[str, Any]] = None

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
                description = f"MCP {tool_name}" if tool_name else "MCP tool"

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
                    tool_internal_name = f"mcp:{server_id}:{tool_name or 'tool'}"
                else:
                    metadata, warn = _metadata_for_physical(definition)
                    if warn:
                        out["warnings"].append(f"{warn}; '{tool_name}' skipped")
                        continue
                    tool_internal_name = (
                        f"mcp:endpoint:{tool_name or definition.get('operationId') or 'tool'}"
                    )
                    metadata["toolName"] = tool_name

                tool = client.tools.create(
                    name=tool_internal_name,
                    description=description,
                    source_type="mcp_server",
                    metadata_=metadata,
                )
                tool_id = getattr(tool, "id", None)
                if tool_id and tool_id not in attached_ids:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                    out["added"]["tool_ids"].append(tool_id)
                    attached_ids.add(tool_id)

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
                block_id = getattr(block, "id", None)
                if not block_id:
                    raise RuntimeError("No block id returned for data source chunk")
                client.agents.blocks.attach(agent_id=agent_id, block_id=block_id)
                out["added"]["data_block_ids"].append(block_id)
            except Exception as exc:
                out["error"] = (
                    f"Failed to attach data source '{source_id}' chunk {index}: {exc}"
                )
                return out

    # 4. Update skill state
    try:
        state: Dict[str, Any] = {}
        state_block_id: Optional[str] = None
        blocks = client.agents.blocks.list(agent_id=agent_id)
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
        state[manifest_id] = {
            "skillName": skill_name,
            "skillVersion": skill_version,
            "memoryBlockIds": out["added"]["memory_block_ids"],
            "toolIds": out["added"]["tool_ids"],
            "dataSourceBlockIds": out["added"]["data_block_ids"],
        }
        new_value = json.dumps(state, indent=2)
        if state_block_id:
            client.blocks.modify(block_id=state_block_id, value=new_value)
        else:
            state_block = client.blocks.create(label=STATE_BLOCK_LABEL, value=new_value)
            state_block_id = getattr(state_block, "id", None)
            if not state_block_id:
                raise RuntimeError("Failed to create skill state block")
            client.agents.blocks.attach(agent_id=agent_id, block_id=state_block_id)
    except Exception as exc:
        out["error"] = f"State tracking error: {exc}"
        return out

    out["ok"] = True
    out["exit_code"] = 0
    out["status"] = (
        f"Loaded skill '{skill_name}' v{skill_version} (manifest {manifest_id})"
    )
    return out
