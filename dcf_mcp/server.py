# server.py
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from tools.common.delete_agent import delete_agent as _delete_agent
from tools.common.remove_tool_return_limits import remove_tool_return_limits as _remove_tool_return_limits
from tools.common.resolve_agent_name_to_id import resolve_agent_name_to_id as _resolve_agent_name_to_id
from tools.dcf.acquire_state_lease import acquire_state_lease as _acquire_state_lease
from tools.dcf.create_workflow_control_plane import create_workflow_control_plane as _create_workflow_control_plane
from tools.dcf.create_worker_agents import create_worker_agents as _create_worker_agents
from tools.dcf.csv_to_manifests import csv_to_manifests as _csv_to_manifests
from tools.dcf.csv_to_stub_config import csv_to_stub_config as _csv_to_stub_config
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


mcp = FastMCP(name="dcf-mcp-server")


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
def validate_skill_manifest(skill_json: str, schema_path: str) -> Dict[str, Any]:
    return _validate_skill_manifest(skill_json=skill_json, schema_path=schema_path)


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
                         default_tags_json: str | None = None) -> Dict[str, Any]:
    return _create_worker_agents(
        workflow_json=workflow_json,
        imports_base_dir=imports_base_dir,
        agent_name_prefix=agent_name_prefix,
        default_tags_json=default_tags_json,
    )


create_worker_agents.__doc__ = _create_worker_agents.__doc__


@mcp.tool()
def csv_to_manifests(skills_csv_path: str = "/app/skills_src/skills.csv",
                     refs_csv_path: str = "/app/skills_src/skill_tool_refs.csv",
                     out_dir: str = "/app/generated/manifests",
                     catalog_path: str = "/app/generated/catalogs/skills_catalog.json") -> Dict[str, Any]:
    return _csv_to_manifests(
        skills_csv_path=skills_csv_path,
        refs_csv_path=refs_csv_path,
        out_dir=out_dir,
        catalog_path=catalog_path,
    )


csv_to_manifests.__doc__ = _csv_to_manifests.__doc__


@mcp.tool()
def csv_to_stub_config(mcp_tools_csv_path: str = "/app/skills_src/mcp_tools.csv",
                       mcp_cases_csv_path: str = "/app/skills_src/mcp_cases.csv",
                       out_path: str = "/app/generated/stub/stub_config.json") -> Dict[str, Any]:
    return _csv_to_stub_config(
        mcp_tools_csv_path=mcp_tools_csv_path,
        mcp_cases_csv_path=mcp_cases_csv_path,
        out_path=out_path,
    )


csv_to_stub_config.__doc__ = _csv_to_stub_config.__doc__


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
                      schema_path: str,
                      imports_base_dir: str | None = None,
                      skills_base_dir: str | None = None) -> Dict[str, Any]:
    return _validate_workflow(
        workflow_json=workflow_json,
        schema_path=schema_path,
        imports_base_dir=imports_base_dir,
        skills_base_dir=skills_base_dir,
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