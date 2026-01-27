# DCF MCP Tools Documentation

This document provides a comprehensive overview of the tools available in the DCF (Dynamic Capabilities Framework) MCP server. These tools enable Planner and Worker agents to orchestrate workflow execution, manage skills, and coordinate via the Redis control plane.

## Architecture Overview

### Design Philosophy

The DCF MCP tools implement a **choreography-first** execution model where workers self-coordinate via a shared Redis control plane without a central orchestrator. Key design principles:

1. **Atomic Operations**: Critical operations (lease acquisition, state updates) use Redis transactions to prevent race conditions
2. **Idempotent Where Possible**: Control plane creation and worker agent creation detect existing resources
3. **Defensive Programming**: All tools use lazy imports and graceful error handling for missing dependencies
4. **Consistent Response Format**: Tools return structured dictionaries with predictable fields for agent parsing

### Tool Categories

The tools are organized into four categories:

| Category | Location | Purpose |
|----------|----------|---------|
| **DCF** | `dcf/` | Workflow execution, validation, skills, leases, notifications |
| **RedisJSON** | `redis_json/` | Low-level JSON document operations in Redis |
| **File System** | `file_system/` | File and directory operations |
| **Common** | `common/` | Agent utilities (name resolution, deletion) |

---

## Response Format Patterns

Tools use two response patterns based on their purpose:

### Pattern A: Validation/Loading Tools
Used by tools that need semantic error categorization.

```python
{
    "ok": bool,           # Quick success check
    "exit_code": int,     # 0=success, 1-4=error categories
    "status": str | None, # Descriptive message
    "error": str | None,  # Error details
    "warnings": [str],    # Non-fatal issues
    # ... tool-specific fields
}
```

**Tools using this pattern**: `validate_workflow`, `validate_skill_manifest`, `load_skill`, `csv_to_manifests`, `csv_to_stub_config`

### Pattern B: Control Plane/Action Tools
Used by tools that perform actions with simple success/failure outcomes.

```python
{
    "status": str | None, # Descriptive message (None on error)
    "error": str | None,  # Error details (None on success)
    # ... tool-specific fields
}
```

**Tools using this pattern**: All control plane, lease, notification, file system, and Redis tools

---

## DCF Tools Reference

### Planning & Validation

#### `validate_workflow`
Validates a Letta-ASL workflow JSON document through a four-stage pipeline.

**Validation Stages**:
1. **Schema validation** (`exit_code=1`): JSON Schema compliance
2. **Import resolution** (`exit_code=2`): Load `.af` bundles and skill manifests
3. **Reference resolution** (`exit_code=2`): Resolve AgentBindings and skill URIs
4. **Graph validation** (`exit_code=3`): Check StartAt, transitions, terminals

**Key Parameters**:
- `workflow_json`: Workflow document as JSON string
- `schema_path`: Path to workflow schema (default: v2.2.0)
- `imports_base_dir`: Base directory for `.af` imports
- `skills_base_dir`: Base directory for skill manifests

**Response Fields**:
- `schema_errors`: List of JSON Schema violations
- `resolution.unresolved_agent_refs`: AgentBindings that couldn't be resolved
- `resolution.unresolved_skill_ids`: Skills not found in imports
- `resolution.state_skill_map`: Mapping of states to resolved skills
- `graph`: StartAt/transition/terminal validation results

#### `validate_skill_manifest`
Validates a skill manifest JSON against the v2.0.0 skill schema.

**Parameters**:
- `skill_json`: Skill manifest as JSON string or file path
- `schema_path`: Path to skill schema (default: v2.0.0)

---

### Skill Management

#### `get_skillset` / `get_skillset_from_catalog`
Retrieves available skills from the manifests directory or a catalog file.

**Parameters**:
- `manifests_dir` / `catalog_path`: Source location
- `include_previews`: Include directive previews (default: true)
- `preview_chars`: Max characters for preview truncation

**Response**: List of skill summaries with metadata and optional directive previews.

#### `load_skill`
Dynamically loads a skill manifest into a Letta agent.

**Loading Process**:
1. Parse manifest (JSON string or file path)
2. Attach `skillDirectives` as a memory block
3. Attach required tools (registered, MCP server, or python_source)
4. Attach data sources (text_content chunks)
5. Update skill state block (`dcf_active_skills`) for tracking

**MCP Server Resolution**:
- **Logical servers**: Resolved via `skills_src/registry.json`
- **Physical servers**: Direct endpoint URL in manifest
- **Supported transports**: `streamable_http`, `stdio`, `ws/sse`

**Parameters**:
- `skill_json`: Manifest as JSON string or file path/URI
- `agent_id`: Target Letta agent ID

**Response Fields**:
- `added.memory_block_ids`: Created memory blocks
- `added.tool_ids`: Attached tools
- `added.data_block_ids`: Created data source blocks

#### `unload_skill`
Removes a previously loaded skill from an agent (idempotent).

**Cleanup Process**:
1. Read skill state from `dcf_active_skills` block
2. Detach and delete tools, memory blocks, data blocks
3. Update or remove state block

**Parameters**:
- `manifest_id`: The `manifestId` of the skill to unload
- `agent_id`: Target Letta agent ID

---

### Workflow Control Plane

#### `create_workflow_control_plane`
Seeds the Redis control plane for a workflow (idempotent via NX flag).

**Created Keys**:
- `cp:wf:{workflow_id}:meta`: Workflow metadata (states, deps, agents, skills)
- `cp:wf:{workflow_id}:state:{state_name}`: Per-state status documents

**Parameters**:
- `workflow_json`: Validated workflow document
- `redis_url`: Redis connection URL
- `expiry_secs`: Optional TTL for keys
- `agents_map_json`: Optional state→agent_id mapping

**Response Fields**:
- `created_keys`: Keys created in this call
- `existing_keys`: Keys that already existed
- `meta_sample`: Round-tripped meta document

#### `read_workflow_control_plane`
Reads workflow state and metadata from the control plane.

**Parameters**:
- `workflow_id`: Workflow UUID
- `states_json`: Optional JSON array of specific states to read
- `include_meta`: Include meta document (default: true)
- `compute_readiness`: Compute per-state readiness based on dependencies

**Response Fields**:
- `meta`: Workflow metadata (if requested)
- `states`: Per-state status documents
- `outputs`: Per-state output data
- `readiness`: Boolean readiness per state (if computed)

#### `update_workflow_control_plane`
Updates a workflow state with new status, lease info, or output.

**Parameters**:
- `workflow_id`, `state`: Target state
- `new_status`: New status value
- `lease_token`: Required for lease validation
- `output_json`: Output data to write to data plane
- `set_started_at`, `set_finished_at`: Timestamp flags
- `error_message`: Error message for failed states

---

### Lease Management

Leases provide mutual exclusion for state execution, preventing multiple workers from processing the same state simultaneously.

#### `acquire_state_lease`
Atomically acquires a lease on a workflow state using WATCH/MULTI/EXEC.

**Acquisition Logic**:
1. Check readiness (all upstream states complete)
2. Check owner match (agent assigned to this state)
3. If lease exists:
   - If expired and `allow_steal_if_expired`: takeover
   - If same owner/token: return `lease_already_held`
   - Else: return `lease_held` error
4. Create new lease with token and TTL

**Parameters**:
- `workflow_id`, `state`: Target state
- `owner_agent_id`: Claiming agent's ID
- `lease_ttl_s`: Lease TTL in seconds (default: 300)
- `require_ready`: Enforce upstream completion (default: true)
- `require_owner_match`: Enforce agent assignment (default: true)
- `allow_steal_if_expired`: Allow takeover of expired leases (default: true)
- `set_running_on_acquire`: Set status to "running" (default: true)

**Response Fields**:
- `status`: `"lease_acquired"` or `"lease_already_held"`
- `lease`: Lease info (token, owner, timestamp, TTL)
- `ready`: Readiness evaluation result

#### `renew_state_lease`
Extends an existing lease's timestamp.

**Parameters**:
- `workflow_id`, `state`: Target state
- `lease_token`: Current lease token (required)
- `reject_if_expired`: Fail if lease already expired (default: true)
- `touch_only`: Only update timestamp, not TTL

#### `release_state_lease`
Releases a lease, allowing other workers to acquire it.

**Parameters**:
- `workflow_id`, `state`: Target state
- `lease_token`: Current lease token
- `force`: Release without token validation
- `clear_owner`: Clear owner_agent_id field

---

### Worker Management & Notifications

#### `create_worker_agents`
Creates one Letta agent per ASL Task state from templates (idempotent).

**Template Resolution Order**:
1. Embedded `.af v2` entities in workflow JSON
2. External `.af` bundles from `af_imports`
3. Disk templates from `imports_base_dir`
4. Inline legacy `.af v1` agent configs

**Idempotency**: When `skip_if_exists=True` (default), checks for existing workers with matching workflow tag and returns them instead of creating duplicates.

**Parameters**:
- `workflow_json`: Validated workflow document
- `imports_base_dir`: Base directory for template resolution
- `skip_if_exists`: Return existing workers if found (default: true)

**Response Fields**:
- `agents_map`: State→agent_id mapping
- `created`: List of newly created agents
- `existing`: List of existing agents (when skip_if_exists triggered)

#### `notify_next_worker_agent`
Sends workflow event notifications to downstream workers.

**Target Selection**:
- If `source_state` provided: notify downstream states
- If `source_state` is None: notify initial states (no upstream)

**Parameters**:
- `workflow_id`: Workflow UUID
- `source_state`: Triggering state (or None for initial kickoff)
- `include_only_ready`: Only notify ready states (default: true)
- `async_message`: Use async Letta messaging (default: false)

**Event Payload**:
```json
{
  "type": "workflow_event",
  "workflow_id": "...",
  "target_state": "...",
  "source_state": "...",
  "reason": "initial|upstream_done",
  "control_plane": {
    "meta_key": "cp:wf:{id}:meta",
    "state_key": "cp:wf:{id}:state:{state}",
    "output_key": "dp:wf:{id}:output:{state}"
  }
}
```

#### `notify_if_ready`
Sends a notification to a specific state's agent if it's ready.

**Parameters**:
- `workflow_id`, `state`: Target state
- `require_ready`: Only notify if ready (default: true)
- `skip_if_status_in_json`: Skip if status in given list

---

### Finalization

#### `finalize_workflow`
Cleans up a completed workflow.

**Actions**:
1. Optionally close open states (pending/running → cancelled)
2. Optionally delete worker agents
3. Compute final status (succeeded/failed/partial)
4. Write audit record to data plane

**Parameters**:
- `workflow_id`: Workflow UUID
- `delete_worker_agents`: Delete workers (default: true)
- `preserve_planner`: Don't delete planner agent (default: true)
- `close_open_states`: Cancel incomplete states (default: true)
- `overall_status`: Override computed status
- `finalize_note`: Free-text audit note

---

## RedisJSON Tools Reference

Low-level JSON document operations for advanced control plane manipulation.

| Tool | Description |
|------|-------------|
| `json_create` | Create new JSON document |
| `json_set` | Set value at path |
| `json_read` | Read value at path |
| `json_append` | Append to array or string |
| `json_merge` | RFC 7386 JSON merge patch |
| `json_increment` | Increment numeric value |
| `json_delete` | Delete value at path |
| `json_copy` | Copy value within document |
| `json_move` | Move value within document |
| `json_ensure` | Ensure path exists with default |

---

## File System Tools Reference

| Tool | Description |
|------|-------------|
| `list_directory` | List directory contents |
| `read_file` | Read file with offset/length |
| `write_file` | Write/append to file |
| `create_directory` | Create directory structure |
| `delete_path` | Delete file or directory |
| `move_path` | Move/rename file or directory |

---

## Common Tools Reference

| Tool | Description |
|------|-------------|
| `resolve_agent_name_to_id` | Get Letta agent ID from name |
| `delete_agent` | Delete Letta agent by name |
| `remove_tool_return_limits` | Remove character limits on tool returns |

---

## Redis Key Structure

### Control Plane Keys
| Key Pattern | Purpose |
|-------------|---------|
| `cp:wf:{workflow_id}:meta` | Workflow metadata (states, deps, agents) |
| `cp:wf:{workflow_id}:state:{state_name}` | Per-state status, lease, timestamps |

### Data Plane Keys
| Key Pattern | Purpose |
|-------------|---------|
| `dp:wf:{workflow_id}:output:{state_name}` | Worker output data |
| `dp:wf:{workflow_id}:audit:finalize` | Finalization audit record |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `LETTA_BASE_URL` | `http://letta:8283` | Letta API endpoint |
| `DCF_SCHEMAS_DIR` | `/app/schemas` | Schema file directory |
| `DCF_MANIFESTS_DIR` | `/app/generated/manifests` | Skill manifest directory |
| `DCF_WORKFLOWS_DIR` | `/app/workflows` | Workflow file directory |
| `DCF_AGENTS_DIR` | `/app/agents` | Agent template directory |
| `SKILL_REGISTRY_PATH` | `skills_src/registry.json` | MCP server registry |
| `SKILL_STATE_BLOCK_LABEL` | `dcf_active_skills` | Skill tracking block label |
| `ALLOW_MCP_SKILLS` | `true` | Enable MCP server skills |
| `ALLOW_PYTHON_SOURCE_SKILLS` | `false` | Enable python_source skills |

---

## Planner Tool Usage Flow

```
1. get_skillset()                    → Discover available skills
2. validate_workflow()               → Validate + resolve imports
   └── Loop until exit_code == 0
3. write_file()                      → Persist workflow JSON
4. create_workflow_control_plane()   → Seed Redis (idempotent)
5. create_worker_agents()            → Create workers (idempotent)
6. json_set() meta.agents            → Record agent mapping
7. notify_next_worker_agent()        → Trigger initial states
8. read_workflow_control_plane()     → Monitor progress
9. finalize_workflow()               → Cleanup
```

## Worker Tool Usage Flow

```
1. (Receive workflow_event message)
2. read_workflow_control_plane()     → Check readiness + get inputs
3. acquire_state_lease()             → Get exclusive access
4. load_skill()                      → Attach required skills
5. (Execute task using skill tools)
6. update_workflow_control_plane()   → Write output + status
7. notify_next_worker_agent()        → Trigger downstream (success only)
8. unload_skill()                    → Cleanup skills
9. release_state_lease()             → Release lock
```

---

## Security Considerations

- **Lazy imports**: Dependencies loaded only when needed, with graceful error handling
- **Lease tokens**: Prevent unauthorized state modifications
- **Owner matching**: Ensures only assigned agents can execute states
- **Skill permissions**: Manifests declare `egress`, `secrets`, and `riskLevel`
- **DNS rebinding protection**: MCP server validates Host/Origin headers
