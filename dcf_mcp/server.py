# server.py
import os
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from tools.common.delete_agent import delete_agent as _delete_agent
from tools.common.remove_tool_return_limits import remove_tool_return_limits as _remove_tool_return_limits
from tools.common.resolve_agent_name_to_id import resolve_agent_name_to_id as _resolve_agent_name_to_id
from tools.dcf.acquire_state_lease import acquire_state_lease as _acquire_state_lease
from tools.dcf.create_workflow_control_plane import create_workflow_control_plane as _create_workflow_control_plane
from tools.dcf.create_worker_agents import create_worker_agents as _create_worker_agents
from tools.dcf.yaml_to_manifests import yaml_to_manifests as _yaml_to_manifests
from tools.dcf.yaml_to_stub_config import yaml_to_stub_config as _yaml_to_stub_config
from tools.dcf.finalize_workflow import finalize_workflow as _finalize_workflow
from tools.dcf.get_skillset import get_skillset as _get_skillset
from tools.dcf.get_skillset_from_catalog import (
    get_skillset_from_catalog as _get_skillset_from_catalog,
)
from tools.dcf.load_skill import load_skill as _load_skill
from tools.dcf.notify_if_ready import notify_if_ready as _notify_if_ready
from tools.dcf.notify_next_worker_agent import notify_next_worker_agent as _notify_next_worker_agent
from tools.dcf.read_workflow_control_plane import read_workflow_control_plane as _read_workflow_control_plane
from tools.dcf.release_state_lease import release_state_lease as _release_state_lease
from tools.dcf.renew_state_lease import renew_state_lease as _renew_state_lease
from tools.dcf.unload_skill import unload_skill as _unload_skill
from tools.dcf.update_workflow_control_plane import update_workflow_control_plane as _update_workflow_control_plane
from tools.dcf.validate_skill_manifest import validate_skill_manifest as _validate_skill_manifest
from tools.dcf.validate_workflow import validate_workflow as _validate_workflow
from tools.dcf.register_reflector import register_reflector as _register_reflector
from tools.dcf.read_shared_memory_blocks import read_shared_memory_blocks as _read_shared_memory_blocks
from tools.dcf.update_reflector_guidelines import update_reflector_guidelines as _update_reflector_guidelines
from tools.dcf.trigger_reflection import trigger_reflection as _trigger_reflection

# DCF+ Tools (Delegated Execution Pattern)
from tools.dcf_plus.create_companion import create_companion as _create_companion
from tools.dcf_plus.dismiss_companion import dismiss_companion as _dismiss_companion
from tools.dcf_plus.list_session_companions import list_session_companions as _list_session_companions
from tools.dcf_plus.update_companion_status import update_companion_status as _update_companion_status
from tools.dcf_plus.create_session_context import create_session_context as _create_session_context
from tools.dcf_plus.update_session_context import update_session_context as _update_session_context
from tools.dcf_plus.finalize_session import finalize_session as _finalize_session
from tools.dcf_plus.delegate_task import delegate_task as _delegate_task
from tools.dcf_plus.broadcast_task import broadcast_task as _broadcast_task
from tools.dcf_plus.report_task_result import report_task_result as _report_task_result
from tools.dcf_plus.register_strategist import register_strategist as _register_strategist
from tools.dcf_plus.trigger_strategist_analysis import trigger_strategist_analysis as _trigger_strategist_analysis
from tools.dcf_plus.read_session_activity import read_session_activity as _read_session_activity
from tools.dcf_plus.update_conductor_guidelines import update_conductor_guidelines as _update_conductor_guidelines

from tools.redis_json.json_append import json_append as _json_append
from tools.redis_json.json_copy import json_copy as _json_copy
from tools.redis_json.json_create import json_create as _json_create
from tools.redis_json.json_delete import json_delete as _json_delete
from tools.redis_json.json_ensure import json_ensure as _json_ensure
from tools.redis_json.json_increment import json_increment as _json_increment
from tools.redis_json.json_merge import json_merge as _json_merge
from tools.redis_json.json_move import json_move as _json_move
from tools.redis_json.json_read import json_read as _json_read
from tools.redis_json.json_set import json_set as _json_set
from tools.file_system.create_directory import create_directory as _create_directory
from tools.file_system.delete_path import delete_path as _delete_path
from tools.file_system.list_directory import list_directory as _list_directory
from tools.file_system.move_path import move_path as _move_path
from tools.file_system.read_file import read_file as _read_file
from tools.file_system.write_file import write_file as _write_file


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _truthy_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _default_transport_security() -> TransportSecuritySettings:
    """
    Protect against DNS rebinding while allowing common local/dev hostnames.

    Some MCP clients (e.g., other Docker services) will connect using the Compose service name
    (Host: dcf-mcp:8337). If DNS rebinding protection is enabled without allowing that host,
    requests fail with HTTP 421 "Invalid Host header".
    """

    enable = _truthy_env(
        os.getenv("DCF_MCP_ENABLE_DNS_REBINDING_PROTECTION"),
        default=True,
    )

    allowed_hosts = _parse_csv_env(os.getenv("DCF_MCP_ALLOWED_HOSTS")) or [
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "dcf-mcp",
        "dcf-mcp:*",
    ]

    allowed_origins = _parse_csv_env(os.getenv("DCF_MCP_ALLOWED_ORIGINS")) or [
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://dcf-mcp:*",
    ]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=enable,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


mcp = FastMCP(name="dcf-mcp-server", transport_security=_default_transport_security())

DEFAULT_SCHEMAS_DIR = os.getenv("DCF_SCHEMAS_DIR", "/app/schemas")
DEFAULT_MANIFESTS_DIR = os.getenv("DCF_MANIFESTS_DIR", "/app/generated/manifests")
DEFAULT_WORKFLOWS_DIR = os.getenv("DCF_WORKFLOWS_DIR", "/app/workflows")
DEFAULT_AGENTS_DIR = os.getenv("DCF_AGENTS_DIR", "/app/agents")

DEFAULT_SKILL_SCHEMA = os.getenv(
    "DCF_SKILL_SCHEMA",
    os.path.join(DEFAULT_SCHEMAS_DIR, "skill_manifest_schema_v2.0.0.json"),
)
DEFAULT_WORKFLOW_SCHEMA = os.getenv(
    "DCF_WORKFLOW_SCHEMA",
    os.path.join(DEFAULT_SCHEMAS_DIR, "letta_asl_workflow_schema_v2.2.0.json"),
)


@mcp.tool()
def resolve_agent_name_to_id(agent_name: str) -> Dict[str, Any]:
    return _resolve_agent_name_to_id(agent_name=agent_name)

resolve_agent_name_to_id.__doc__ = _resolve_agent_name_to_id.__doc__


@mcp.tool()
def get_skillset(manifests_dir: str | None = None,
                 schema_path: str | None = None,
                 include_previews: bool = True,
                 preview_chars: int | None = None) -> Dict[str, Any]:
    return _get_skillset(
        manifests_dir=manifests_dir,
        schema_path=schema_path,
        include_previews=include_previews,
        preview_chars=preview_chars,
    )

get_skillset.__doc__ = _get_skillset.__doc__


@mcp.tool()
def get_skillset_from_catalog(catalog_path: str | None = None,
                              schema_path: str | None = None,
                              include_previews: bool = True,
                              preview_chars: int | None = None) -> Dict[str, Any]:
    return _get_skillset_from_catalog(
        catalog_path=catalog_path,
        schema_path=schema_path,
        include_previews=include_previews,
        preview_chars=preview_chars,
    )


get_skillset_from_catalog.__doc__ = _get_skillset_from_catalog.__doc__


@mcp.tool()
def remove_tool_return_limits(agent_id: str) -> Dict[str, Any]:
    return _remove_tool_return_limits(agent_id=agent_id)


remove_tool_return_limits.__doc__ = _remove_tool_return_limits.__doc__


@mcp.tool()
def delete_agent(agent_name: str) -> Dict[str, Any]:
    return _delete_agent(agent_name=agent_name)


delete_agent.__doc__ = _delete_agent.__doc__


@mcp.tool()
def load_skill(skill_json: str, agent_id: str) -> Dict[str, Any]:
    return _load_skill(skill_manifest=skill_json, agent_id=agent_id)


load_skill.__doc__ = _load_skill.__doc__


@mcp.tool()
def unload_skill(manifest_id: str, agent_id: str) -> Dict[str, Any]:
    return _unload_skill(manifest_id=manifest_id, agent_id=agent_id)


unload_skill.__doc__ = _unload_skill.__doc__


@mcp.tool()
def validate_skill_manifest(skill_json: str, schema_path: str | None = None) -> Dict[str, Any]:
    effective_schema = schema_path or DEFAULT_SKILL_SCHEMA
    return _validate_skill_manifest(skill_json=skill_json, schema_path=effective_schema)


validate_skill_manifest.__doc__ = _validate_skill_manifest.__doc__


@mcp.tool()
def create_workflow_control_plane(workflow_json: str,
                                  redis_url: str | None = None,
                                  expiry_secs: int | None = None,
                                  agents_map_json: str | None = None) -> Dict[str, Any]:
    return _create_workflow_control_plane(
        workflow_json=workflow_json,
        redis_url=redis_url,
        expiry_secs=expiry_secs,
        agents_map_json=agents_map_json,
    )


create_workflow_control_plane.__doc__ = _create_workflow_control_plane.__doc__


@mcp.tool()
def read_workflow_control_plane(workflow_id: str,
                                redis_url: str | None = None,
                                states_json: str | None = None,
                                include_meta: bool = True,
                                compute_readiness: bool = False) -> Dict[str, Any]:
    return _read_workflow_control_plane(
        workflow_id=workflow_id,
        redis_url=redis_url,
        states_json=states_json,
        include_meta=include_meta,
        compute_readiness=compute_readiness,
    )


read_workflow_control_plane.__doc__ = _read_workflow_control_plane.__doc__


@mcp.tool()
def update_workflow_control_plane(workflow_id: str,
                                  state: str,
                                  redis_url: str | None = None,
                                  new_status: str | None = None,
                                  lease_token: str | None = None,
                                  owner_agent_id: str | None = None,
                                  lease_ttl_s: int | None = None,
                                  attempts_increment: int | None = None,
                                  error_message: str | None = None,
                                  set_started_at: bool = False,
                                  set_finished_at: bool = False,
                                  output_json: str | None = None,
                                  output_ttl_secs: int | None = None) -> Dict[str, Any]:
    return _update_workflow_control_plane(
        workflow_id=workflow_id,
        state=state,
        redis_url=redis_url,
        new_status=new_status,
        lease_token=lease_token,
        owner_agent_id=owner_agent_id,
        lease_ttl_s=lease_ttl_s,
        attempts_increment=attempts_increment,
        error_message=error_message,
        set_started_at=set_started_at,
        set_finished_at=set_finished_at,
        output_json=output_json,
        output_ttl_secs=output_ttl_secs,
    )


update_workflow_control_plane.__doc__ = _update_workflow_control_plane.__doc__


@mcp.tool()
def acquire_state_lease(workflow_id: str,
                        state: str,
                        owner_agent_id: str,
                        redis_url: str | None = None,
                        lease_ttl_s: int | None = None,
                        require_ready: bool = True,
                        require_owner_match: bool = True,
                        allow_steal_if_expired: bool = True,
                        set_running_on_acquire: bool = True,
                        attempts_increment: int = 1,
                        lease_token: str | None = None) -> Dict[str, Any]:
    return _acquire_state_lease(
        workflow_id=workflow_id,
        state=state,
        owner_agent_id=owner_agent_id,
        redis_url=redis_url,
        lease_ttl_s=lease_ttl_s,
        require_ready=require_ready,
        require_owner_match=require_owner_match,
        allow_steal_if_expired=allow_steal_if_expired,
        set_running_on_acquire=set_running_on_acquire,
        attempts_increment=attempts_increment,
        lease_token=lease_token,
    )


acquire_state_lease.__doc__ = _acquire_state_lease.__doc__


@mcp.tool()
def renew_state_lease(workflow_id: str,
                      state: str,
                      lease_token: str,
                      owner_agent_id: str | None = None,
                      redis_url: str | None = None,
                      lease_ttl_s: int | None = None,
                      reject_if_expired: bool = True,
                      touch_only: bool = False) -> Dict[str, Any]:
    return _renew_state_lease(
        workflow_id=workflow_id,
        state=state,
        lease_token=lease_token,
        owner_agent_id=owner_agent_id,
        redis_url=redis_url,
        lease_ttl_s=lease_ttl_s,
        reject_if_expired=reject_if_expired,
        touch_only=touch_only,
    )


renew_state_lease.__doc__ = _renew_state_lease.__doc__


@mcp.tool()
def release_state_lease(workflow_id: str,
                        state: str,
                        lease_token: str,
                        owner_agent_id: str | None = None,
                        redis_url: str | None = None,
                        force: bool = False,
                        clear_owner: bool = True) -> Dict[str, Any]:
    return _release_state_lease(
        workflow_id=workflow_id,
        state=state,
        lease_token=lease_token,
        owner_agent_id=owner_agent_id,
        redis_url=redis_url,
        force=force,
        clear_owner=clear_owner,
    )


release_state_lease.__doc__ = _release_state_lease.__doc__


@mcp.tool()
def create_worker_agents(workflow_json: str,
                         imports_base_dir: str | None = None,
                         agent_name_prefix: str | None = None,
                         agent_name_suffix: str | None = None,
                         default_tags_json: str | None = None,
                         skip_if_exists: bool = True) -> Dict[str, Any]:
    effective_imports = imports_base_dir or DEFAULT_AGENTS_DIR
    effective_suffix = agent_name_suffix or ".af"
    return _create_worker_agents(
        workflow_json=workflow_json,
        imports_base_dir=effective_imports,
        agent_name_prefix=agent_name_prefix,
        agent_name_suffix=effective_suffix,
        default_tags_json=default_tags_json,
        skip_if_exists=skip_if_exists,
    )


create_worker_agents.__doc__ = _create_worker_agents.__doc__


@mcp.tool()
def yaml_to_manifests(skills_dir: str = "/app/skills_src/skills",
                      tools_yaml_path: str = "/app/skills_src/tools.yaml",
                      out_dir: str = "/app/generated/manifests",
                      catalog_path: str = "/app/generated/catalogs/skills_catalog.json") -> Dict[str, Any]:
    return _yaml_to_manifests(
        skills_dir=skills_dir,
        tools_yaml_path=tools_yaml_path,
        out_dir=out_dir,
        catalog_path=catalog_path,
    )


yaml_to_manifests.__doc__ = _yaml_to_manifests.__doc__


@mcp.tool()
def yaml_to_stub_config(tools_yaml_path: str = "/app/skills_src/tools.yaml",
                        out_path: str = "/app/generated/stub/stub_config.json") -> Dict[str, Any]:
    return _yaml_to_stub_config(
        tools_yaml_path=tools_yaml_path,
        out_path=out_path,
    )


yaml_to_stub_config.__doc__ = _yaml_to_stub_config.__doc__


@mcp.tool()
def finalize_workflow(workflow_id: str,
                      redis_url: str | None = None,
                      delete_worker_agents: bool = True,
                      preserve_planner: bool = True,
                      close_open_states: bool = True,
                      overall_status: str | None = None,
                      finalize_note: str | None = None) -> Dict[str, Any]:
    return _finalize_workflow(
        workflow_id=workflow_id,
        redis_url=redis_url,
        delete_worker_agents=delete_worker_agents,
        preserve_planner=preserve_planner,
        close_open_states=close_open_states,
        overall_status=overall_status,
        finalize_note=finalize_note,
    )


finalize_workflow.__doc__ = _finalize_workflow.__doc__


@mcp.tool()
def validate_workflow(workflow_json: str,
                      schema_path: str | None = None,
                      imports_base_dir: str | None = None,
                      skills_base_dir: str | None = None) -> Dict[str, Any]:
    effective_schema = schema_path or DEFAULT_WORKFLOW_SCHEMA
    effective_imports = imports_base_dir or DEFAULT_WORKFLOWS_DIR
    effective_skills = skills_base_dir or DEFAULT_MANIFESTS_DIR or effective_imports

    return _validate_workflow(
        workflow_json=workflow_json,
        schema_path=effective_schema,
        imports_base_dir=effective_imports,
        skills_base_dir=effective_skills,
    )


validate_workflow.__doc__ = _validate_workflow.__doc__


@mcp.tool()
def notify_if_ready(workflow_id: str,
                    state: str,
                    redis_url: str | None = None,
                    reason: str | None = None,
                    payload_json: str | None = None,
                    require_ready: bool = True,
                    skip_if_status_in_json: str | None = None,
                    message_role: str = "system",
                    async_message: bool = False,
                    max_steps: int | None = None) -> Dict[str, Any]:
    return _notify_if_ready(
        workflow_id=workflow_id,
        state=state,
        redis_url=redis_url,
        reason=reason,
        payload_json=payload_json,
        require_ready=require_ready,
        skip_if_status_in_json=skip_if_status_in_json,
        message_role=message_role,
        async_message=async_message,
        max_steps=max_steps,
    )


notify_if_ready.__doc__ = _notify_if_ready.__doc__


@mcp.tool()
def notify_next_worker_agent(workflow_id: str,
                             source_state: str | None = None,
                             reason: str | None = None,
                             payload_json: str | None = None,
                             redis_url: str | None = None,
                             include_only_ready: bool = True,
                             message_role: str = "system",
                             async_message: bool = False,
                             max_steps: int | None = None) -> Dict[str, Any]:
    return _notify_next_worker_agent(
        workflow_id=workflow_id,
        source_state=source_state,
        reason=reason,
        payload_json=payload_json,
        redis_url=redis_url,
        include_only_ready=include_only_ready,
        message_role=message_role,
        async_message=async_message,
        max_steps=max_steps,
    )


notify_next_worker_agent.__doc__ = _notify_next_worker_agent.__doc__


# --- Reflector Tools ---

@mcp.tool()
def register_reflector(planner_agent_id: str,
                       reflector_agent_id: str,
                       initial_guidelines_json: str | None = None) -> Dict[str, Any]:
    return _register_reflector(
        planner_agent_id=planner_agent_id,
        reflector_agent_id=reflector_agent_id,
        initial_guidelines_json=initial_guidelines_json,
    )


register_reflector.__doc__ = _register_reflector.__doc__


@mcp.tool()
def read_shared_memory_blocks(planner_agent_id: str,
                              reflector_agent_id: str | None = None,
                              include_labels_json: str | None = None,
                              exclude_labels_json: str | None = None,
                              include_all: bool = False) -> Dict[str, Any]:
    include_labels = None
    exclude_labels = None
    if include_labels_json:
        try:
            include_labels = __import__("json").loads(include_labels_json)
        except Exception:
            pass
    if exclude_labels_json:
        try:
            exclude_labels = __import__("json").loads(exclude_labels_json)
        except Exception:
            pass
    return _read_shared_memory_blocks(
        planner_agent_id=planner_agent_id,
        reflector_agent_id=reflector_agent_id,
        include_labels=include_labels,
        exclude_labels=exclude_labels,
        include_all=include_all,
    )


read_shared_memory_blocks.__doc__ = _read_shared_memory_blocks.__doc__


@mcp.tool()
def update_reflector_guidelines(planner_agent_id: str,
                                guidelines_json: str | None = None,
                                add_skill_recommendation: str | None = None,
                                add_workflow_pattern: str | None = None,
                                add_user_intent_tip: str | None = None,
                                add_warning: str | None = None,
                                add_insight: str | None = None,
                                merge_mode: bool = True) -> Dict[str, Any]:
    return _update_reflector_guidelines(
        planner_agent_id=planner_agent_id,
        guidelines_json=guidelines_json,
        add_skill_recommendation=add_skill_recommendation,
        add_workflow_pattern=add_workflow_pattern,
        add_user_intent_tip=add_user_intent_tip,
        add_warning=add_warning,
        add_insight=add_insight,
        merge_mode=merge_mode,
    )


update_reflector_guidelines.__doc__ = _update_reflector_guidelines.__doc__


@mcp.tool()
def trigger_reflection(workflow_id: str,
                       planner_agent_id: str,
                       final_status: str | None = None,
                       execution_summary_json: str | None = None,
                       redis_url: str | None = None,
                       async_message: bool = True,
                       max_steps: int | None = None) -> Dict[str, Any]:
    return _trigger_reflection(
        workflow_id=workflow_id,
        planner_agent_id=planner_agent_id,
        final_status=final_status,
        execution_summary_json=execution_summary_json,
        redis_url=redis_url,
        async_message=async_message,
        max_steps=max_steps,
    )


trigger_reflection.__doc__ = _trigger_reflection.__doc__


# --- DCF+ Tools (Delegated Execution Pattern) ---

@mcp.tool()
def create_companion(session_id: str,
                     conductor_id: str,
                     specialization: str = "generalist",
                     shared_block_ids_json: str | None = None,
                     initial_skills_json: str | None = None,
                     companion_name: str | None = None,
                     persona_override: str | None = None) -> Dict[str, Any]:
    return _create_companion(
        session_id=session_id,
        conductor_id=conductor_id,
        specialization=specialization,
        shared_block_ids_json=shared_block_ids_json,
        initial_skills_json=initial_skills_json,
        companion_name=companion_name,
        persona_override=persona_override,
    )


create_companion.__doc__ = _create_companion.__doc__


@mcp.tool()
def dismiss_companion(companion_id: str,
                      unload_skills: bool = True,
                      detach_shared_blocks: bool = True) -> Dict[str, Any]:
    return _dismiss_companion(
        companion_id=companion_id,
        unload_skills=unload_skills,
        detach_shared_blocks=detach_shared_blocks,
    )


dismiss_companion.__doc__ = _dismiss_companion.__doc__


@mcp.tool()
def list_session_companions(session_id: str,
                            include_status: bool = True,
                            specialization_filter: str | None = None) -> Dict[str, Any]:
    return _list_session_companions(
        session_id=session_id,
        include_status=include_status,
        specialization_filter=specialization_filter,
    )


list_session_companions.__doc__ = _list_session_companions.__doc__


@mcp.tool()
def update_companion_status(companion_id: str,
                            status: str | None = None,
                            specialization: str | None = None,
                            current_task_id: str | None = None) -> Dict[str, Any]:
    return _update_companion_status(
        companion_id=companion_id,
        status=status,
        specialization=specialization,
        current_task_id=current_task_id,
    )


update_companion_status.__doc__ = _update_companion_status.__doc__


@mcp.tool()
def create_session_context(session_id: str,
                           conductor_id: str,
                           objective: str | None = None,
                           initial_context_json: str | None = None) -> Dict[str, Any]:
    return _create_session_context(
        session_id=session_id,
        conductor_id=conductor_id,
        objective=objective,
        initial_context_json=initial_context_json,
    )


create_session_context.__doc__ = _create_session_context.__doc__


@mcp.tool()
def update_session_context(session_id: str,
                           block_id: str,
                           state: str | None = None,
                           objective: str | None = None,
                           add_active_task: str | None = None,
                           complete_task: str | None = None,
                           companion_count: int | None = None,
                           announcement: str | None = None,
                           shared_data_json: str | None = None) -> Dict[str, Any]:
    return _update_session_context(
        session_id=session_id,
        block_id=block_id,
        state=state,
        objective=objective,
        add_active_task=add_active_task,
        complete_task=complete_task,
        companion_count=companion_count,
        announcement=announcement,
        shared_data_json=shared_data_json,
    )


update_session_context.__doc__ = _update_session_context.__doc__


@mcp.tool()
def finalize_session(session_id: str,
                     session_context_block_id: str,
                     delete_companions: bool = True,
                     delete_session_block: bool = False,
                     preserve_wisdom: bool = True) -> Dict[str, Any]:
    return _finalize_session(
        session_id=session_id,
        session_context_block_id=session_context_block_id,
        delete_companions=delete_companions,
        delete_session_block=delete_session_block,
        preserve_wisdom=preserve_wisdom,
    )


finalize_session.__doc__ = _finalize_session.__doc__


@mcp.tool()
def delegate_task(conductor_id: str,
                  companion_id: str,
                  task_description: str,
                  required_skills_json: str | None = None,
                  input_data_json: str | None = None,
                  priority: str = "normal",
                  timeout_seconds: int = 300,
                  session_id: str | None = None) -> Dict[str, Any]:
    return _delegate_task(
        conductor_id=conductor_id,
        companion_id=companion_id,
        task_description=task_description,
        required_skills_json=required_skills_json,
        input_data_json=input_data_json,
        priority=priority,
        timeout_seconds=timeout_seconds,
        session_id=session_id,
    )


delegate_task.__doc__ = _delegate_task.__doc__


@mcp.tool()
def broadcast_task(conductor_id: str,
                   session_id: str,
                   task_description: str,
                   specialization_filter: str | None = None,
                   status_filter: str = "idle",
                   required_skills_json: str | None = None,
                   input_data_json: str | None = None,
                   max_companions: int = 1) -> Dict[str, Any]:
    return _broadcast_task(
        conductor_id=conductor_id,
        session_id=session_id,
        task_description=task_description,
        specialization_filter=specialization_filter,
        status_filter=status_filter,
        required_skills_json=required_skills_json,
        input_data_json=input_data_json,
        max_companions=max_companions,
    )


broadcast_task.__doc__ = _broadcast_task.__doc__


@mcp.tool()
def report_task_result(companion_id: str,
                       task_id: str,
                       conductor_id: str,
                       status: str,
                       summary: str,
                       output_data_json: str | None = None,
                       artifacts_json: str | None = None,
                       error_code: str | None = None,
                       error_message: str | None = None,
                       metrics_json: str | None = None) -> Dict[str, Any]:
    return _report_task_result(
        companion_id=companion_id,
        task_id=task_id,
        conductor_id=conductor_id,
        status=status,
        summary=summary,
        output_data_json=output_data_json,
        artifacts_json=artifacts_json,
        error_code=error_code,
        error_message=error_message,
        metrics_json=metrics_json,
    )


report_task_result.__doc__ = _report_task_result.__doc__


# --- DCF+ Strategist Integration Tools ---

@mcp.tool()
def register_strategist(conductor_agent_id: str,
                        strategist_agent_id: str,
                        initial_guidelines_json: str | None = None) -> Dict[str, Any]:
    return _register_strategist(
        conductor_agent_id=conductor_agent_id,
        strategist_agent_id=strategist_agent_id,
        initial_guidelines_json=initial_guidelines_json,
    )


register_strategist.__doc__ = _register_strategist.__doc__


@mcp.tool()
def trigger_strategist_analysis(session_id: str,
                                conductor_agent_id: str,
                                trigger_reason: str = "periodic",
                                tasks_since_last_analysis: int | None = None,
                                recent_failures: int | None = None,
                                include_full_history: bool = False,
                                async_message: bool = True,
                                max_steps: int | None = None) -> Dict[str, Any]:
    return _trigger_strategist_analysis(
        session_id=session_id,
        conductor_agent_id=conductor_agent_id,
        trigger_reason=trigger_reason,
        tasks_since_last_analysis=tasks_since_last_analysis,
        recent_failures=recent_failures,
        include_full_history=include_full_history,
        async_message=async_message,
        max_steps=max_steps,
    )


trigger_strategist_analysis.__doc__ = _trigger_strategist_analysis.__doc__


# --- DCF+ Strategist Observation Tools ---

@mcp.tool()
def read_session_activity(session_id: str,
                          conductor_id: str | None = None,
                          session_context_block_id: str | None = None,
                          include_companion_details: bool = True,
                          include_task_history: bool = True,
                          include_skill_metrics: bool = True) -> Dict[str, Any]:
    return _read_session_activity(
        session_id=session_id,
        conductor_id=conductor_id,
        session_context_block_id=session_context_block_id,
        include_companion_details=include_companion_details,
        include_task_history=include_task_history,
        include_skill_metrics=include_skill_metrics,
    )


read_session_activity.__doc__ = _read_session_activity.__doc__


@mcp.tool()
def update_conductor_guidelines(conductor_id: str,
                                guidelines_json: str | None = None,
                                recommendation: str | None = None,
                                skill_preferences_json: str | None = None,
                                companion_scaling_json: str | None = None,
                                clear_guidelines: bool = False) -> Dict[str, Any]:
    return _update_conductor_guidelines(
        conductor_id=conductor_id,
        guidelines_json=guidelines_json,
        recommendation=recommendation,
        skill_preferences_json=skill_preferences_json,
        companion_scaling_json=companion_scaling_json,
        clear_guidelines=clear_guidelines,
    )


update_conductor_guidelines.__doc__ = _update_conductor_guidelines.__doc__


@mcp.tool()
def list_directory(path: str = ".",
                   recursive: bool = False,
                   include_hidden: bool = False,
                   max_entries: int | None = None) -> Dict[str, Any]:
    return _list_directory(
        path=path,
        recursive=recursive,
        include_hidden=include_hidden,
        max_entries=max_entries,
    )


list_directory.__doc__ = _list_directory.__doc__


@mcp.tool()
def read_file(path: str,
              offset: int = 0,
              length: int | None = None,
              encoding: str = "utf-8") -> Dict[str, Any]:
    return _read_file(path=path, offset=offset, length=length, encoding=encoding)


read_file.__doc__ = _read_file.__doc__


@mcp.tool()
def write_file(path: str,
               content: str,
               append: bool = False,
               encoding: str = "utf-8",
               create_parents: bool = True) -> Dict[str, Any]:
    return _write_file(
        path=path,
        content=content,
        append=append,
        encoding=encoding,
        create_parents=create_parents,
    )


write_file.__doc__ = _write_file.__doc__


@mcp.tool()
def create_directory(path: str,
                     parents: bool = True,
                     exist_ok: bool = True) -> Dict[str, Any]:
    return _create_directory(path=path, parents=parents, exist_ok=exist_ok)


create_directory.__doc__ = _create_directory.__doc__


@mcp.tool()
def delete_path(path: str,
                recursive: bool = False) -> Dict[str, Any]:
    return _delete_path(path=path, recursive=recursive)


delete_path.__doc__ = _delete_path.__doc__


@mcp.tool()
def move_path(source: str,
              destination: str,
              overwrite: bool = False,
              create_parents: bool = True) -> Dict[str, Any]:
    return _move_path(
        source=source,
        destination=destination,
        overwrite=overwrite,
        create_parents=create_parents,
    )


move_path.__doc__ = _move_path.__doc__


@mcp.tool()
def json_create(redis_key: str = "",
                initial_json: str = "{}",
                key_prefix: str = "doc:",
                overwrite: bool = False) -> Dict[str, Any]:
    return _json_create(
        redis_key=redis_key,
        initial_json=initial_json,
        key_prefix=key_prefix,
        overwrite=overwrite,
    )


json_create.__doc__ = _json_create.__doc__


@mcp.tool()
def json_set(redis_key: str, path: str, value_json: str) -> Dict[str, Any]:
    return _json_set(redis_key=redis_key, path=path, value_json=value_json)


json_set.__doc__ = _json_set.__doc__


@mcp.tool()
def json_append(redis_key: str, path: str, value_json: str) -> Dict[str, Any]:
    return _json_append(redis_key=redis_key, path=path, value_json=value_json)


json_append.__doc__ = _json_append.__doc__


@mcp.tool()
def json_ensure(redis_key: str, path: str, default_json: str) -> Dict[str, Any]:
    return _json_ensure(redis_key=redis_key, path=path, default_json=default_json)


json_ensure.__doc__ = _json_ensure.__doc__


@mcp.tool()
def json_merge(redis_key: str, path: str, patch_json: str) -> Dict[str, Any]:
    return _json_merge(redis_key=redis_key, path=path, patch_json=patch_json)


json_merge.__doc__ = _json_merge.__doc__


@mcp.tool()
def json_increment(redis_key: str, path: str, delta: str) -> Dict[str, Any]:
    return _json_increment(redis_key=redis_key, path=path, delta=delta)


json_increment.__doc__ = _json_increment.__doc__


@mcp.tool()
def json_copy(redis_key: str,
              from_path: str,
              to_path: str,
              overwrite: bool = True) -> Dict[str, Any]:
    return _json_copy(
        redis_key=redis_key,
        from_path=from_path,
        to_path=to_path,
        overwrite=overwrite,
    )


json_copy.__doc__ = _json_copy.__doc__


@mcp.tool()
def json_move(redis_key: str,
              from_path: str,
              to_path: str,
              overwrite: bool = True) -> Dict[str, Any]:
    return _json_move(
        redis_key=redis_key,
        from_path=from_path,
        to_path=to_path,
        overwrite=overwrite,
    )


json_move.__doc__ = _json_move.__doc__


@mcp.tool()
def json_delete(redis_key: str, path: str) -> Dict[str, Any]:
    return _json_delete(redis_key=redis_key, path=path)


json_delete.__doc__ = _json_delete.__doc__


@mcp.tool()
def json_read(redis_key: str, path: str = "$", pretty: bool = False) -> Dict[str, Any]:
    return _json_read(redis_key=redis_key, path=path, pretty=pretty)


json_read.__doc__ = _json_read.__doc__


app = mcp.streamable_http_app()
