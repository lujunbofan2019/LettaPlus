# DCF+ Tools Documentation

> **Phase**: 2 (Delegated Execution)
> **Status**: Design Specification
> **Last Updated**: 2026-02-04

This document specifies the tools required for DCF+ (Phase 2: Delegated Execution pattern). For Phase 1 (Workflow Execution) tools, see [`../TOOLS.md`](../TOOLS.md).

> **Note**: The directory is named `dcf_plus` (not `dcf+`) for Python import compatibility. Tools are accessible via `tools.dcf_plus.*` imports.

---

## Overview

DCF+ implements the **Delegated Execution** pattern where a **Conductor** agent manages a pool of session-scoped **Companion** agents, with a **Strategist** providing continuous optimization advice. Unlike Phase 1's predetermined workflows, DCF+ features dynamic task delegation during ongoing user conversations.

### Key Differences from Phase 1

| Aspect | Phase 1 (dcf) | Phase 2 (dcf+) |
|--------|---------------|----------------|
| Orchestrator | Planner | Conductor |
| Executors | Workers (ephemeral per workflow) | Companions (session-scoped) |
| Communication | Custom Redis notifications | Letta native multi-agent tools |
| State sharing | Redis control plane | Shared memory blocks + Redis |
| Task structure | Predetermined DAG | Dynamic delegation |
| User engagement | Paused during execution | Continuous |

---

## Skill Management (Critical Design Decision)

### Who Is the Skill Authority?

In both Phase 1 and Phase 2, **the orchestrating agent is the skill authority**:

| Phase | Skill Authority | Executors | Advisor |
|-------|-----------------|-----------|---------|
| Phase 1 (dcf) | **Planner** | Workers | Reflector |
| Phase 2 (dcf+) | **Conductor** | Companions | Strategist |

### Skill Management Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      SKILL MANAGEMENT FLOW                      │
└─────────────────────────────────────────────────────────────────┘

  Strategist                    Conductor                  Companion
  (Advisor)                     (Authority)                (Executor)
      │                              │                          │
      │ 1. Observes outcomes         │                          │
      │◄─────────────────────────────┼──────────────────────────┤
      │                              │                          │
      │ 2. Publishes skill_preferences                          │
      ├─────────────────────────────►│                          │
      │                              │                          │
      │                   3. Discovers skills                   │
      │                   get_skillset()                        │
      │                              │                          │
      │                   4. Selects skills                     │
      │                   (applies preferences)                 │
      │                              │                          │
      │                   5. Delegates with required_skills     │
      │                              ├─────────────────────────►│
      │                              │                          │
      │                              │         6. Loads skills  │
      │                              │         load_skill()     │
      │                              │                          │
      │                              │         7. Executes task │
      │                              │                          │
      │                              │         8. Unloads skills│
      │                              │         unload_skill()   │
      │                              │                          │
      │                   9. Receives results                   │
      │                              │◄─────────────────────────┤
      │                              │                          │
      │ 10. Loop continues           │                          │
      │◄─────────────────────────────┤                          │
```

### Why Companions Don't Discover Skills

Companions are **simple executors** by design:

1. **Predictability**: Companions do exactly what they're told
2. **Centralized optimization**: Strategist can influence all skill decisions via Conductor
3. **Lightweight**: Companions don't need catalog access or skill evaluation logic
4. **Debuggability**: Skill selection issues always trace to Conductor/Strategist

### The Feedback Loop

The Strategist improves skill selection over time:

1. Companion executes task with Conductor-assigned skills
2. Companion reports success/failure with metrics
3. Strategist observes outcomes and analyzes skill effectiveness
4. Strategist publishes `skill_preferences` to guidelines
5. Conductor reads preferences before next delegation
6. Better skill selection → higher success rate
7. Loop continues

---

## Strategist/Reflector Parallel

The Strategist serves the same role in DCF+ that the Reflector serves in DCF:

| Aspect | Phase 1 Reflector | Phase 2 Strategist |
|--------|-------------------|-------------------|
| Observes | Completed workflow executions | Ongoing session activity |
| Reads | Planner's shared memory | `session_context` block |
| Writes | `reflector_guidelines` block | `strategist_guidelines` block |
| Persists | Graphiti (patterns, metrics) | Graphiti (patterns, metrics) |
| Timing | Post-workflow (batch) | Real-time (continuous) |
| Improves | Planner's workflow planning | Conductor's task delegation |

Both use the same architectural pattern:
- Read-only access to orchestrator's shared state
- Write access to dedicated guidelines block
- Long-term memory via Graphiti
- Evidence-based recommendations

---

## Letta Platform Integration

DCF+ leverages Letta's native multi-agent capabilities. This section documents the Letta features used and best practices for DCF+.

### Native Multi-Agent Communication Tools

Letta provides built-in tools for inter-agent messaging. These should be attached to agents instead of building custom notification mechanisms.

#### `send_message_to_agent_async`

**Purpose**: Fire-and-forget messaging for task delegation and result reporting.

**Signature**:
```python
def send_message_to_agent_async(message: str, other_agent_id: str) -> str
```

**Use Cases**:
- Conductor → Companion: Delegate tasks
- Companion → Conductor: Report results
- Strategist → Conductor: Provide advice

**DCF+ Usage**:
```python
# Conductor delegates task to Companion
send_message_to_agent_async(
    message=json.dumps({
        "type": "task_delegation",
        "task_id": "uuid",
        "description": "Research quantum computing advances",
        "skills_required": ["skill://research.web@0.2.0"],
        "context": {...},
        "priority": "normal"
    }),
    other_agent_id=companion_id
)

# Companion reports result to Conductor
send_message_to_agent_async(
    message=json.dumps({
        "type": "task_result",
        "task_id": "uuid",
        "status": "succeeded",
        "output": {...},
        "metrics": {"duration_s": 45, "tool_calls": 3}
    }),
    other_agent_id=conductor_id
)
```

#### `send_message_to_agent_and_wait_for_reply`

**Purpose**: Synchronous messaging when immediate response is required.

**Signature**:
```python
def send_message_to_agent_and_wait_for_reply(message: str, other_agent_id: str) -> str
```

**Use Cases**:
- Conductor querying Companion for status
- Coordinator patterns requiring acknowledgment

**Note**: Letta recommends attaching only ONE of `async` or `sync` tools to avoid confusion.

#### `send_message_to_agents_matching_all_tags`

**Purpose**: Broadcast to agent groups (supervisor-worker pattern).

**Signature**:
```python
def send_message_to_agents_matching_all_tags(message: str, tags: List[str]) -> List[str]
```

**Use Cases**:
- Conductor → All Companions: Session-wide announcements
- Conductor → Specialists: Task broadcast to capable agents

**DCF+ Usage**:
```python
# Broadcast session context update to all Companions
send_message_to_agents_matching_all_tags(
    message=json.dumps({
        "type": "session_update",
        "context": {"user_priority": "speed over quality"}
    }),
    tags=["role:companion", f"session:{session_id}"]
)
```

### Shared Memory Blocks

Letta supports attaching the same memory block to multiple agents for real-time state sharing.

#### Creating Shared Blocks

```python
# Create a shared session context block
session_block = client.blocks.create(
    label="session_context",
    description="Shared session state accessible by Conductor and all Companions. Contains user goals, preferences, and active task tracking.",
    value=json.dumps({
        "session_id": "uuid",
        "user_goals": [],
        "preferences": {},
        "active_tasks": {},
        "completed_tasks": []
    }),
    limit=8000
)
```

#### Attaching to Multiple Agents

```python
# Attach to Conductor
client.agents.blocks.attach(agent_id=conductor_id, block_id=session_block.id)

# Attach to each Companion (they see updates in real-time)
for companion_id in companion_ids:
    client.agents.blocks.attach(agent_id=companion_id, block_id=session_block.id)
```

#### Block Descriptions (Critical)

The `description` field guides how agents use the block. Well-crafted descriptions are essential:

```python
# Good: Specific guidance
description="Task queue block. Conductor writes new tasks here. Companions read and claim tasks by updating status to 'in_progress' with their agent_id."

# Bad: Vague
description="Shared data"
```

#### Concurrency Best Practices

| Pattern | Approach | Use Case |
|---------|----------|----------|
| Append-only | Use `memory_insert` | Logging, event streams |
| Single owner | Designate one agent for writes | Configuration, task queue |
| Partitioned | Each agent writes to own section | Status reporting |
| Timestamped | Include agent_id + timestamp | Conflict resolution |

### Tag-Based Agent Management

Tags enable efficient agent grouping and discovery.

#### Standard DCF+ Tag Schema

| Tag | Purpose | Example |
|-----|---------|---------|
| `role:{type}` | Agent type | `role:conductor`, `role:companion`, `role:strategist` |
| `session:{id}` | Session membership | `session:abc123` |
| `specialization:{domain}` | Companion expertise | `specialization:research`, `specialization:analysis` |
| `status:{state}` | Current state | `status:idle`, `status:busy` |

#### Creating Tagged Agents

```python
companion = client.agents.create(
    name=f"companion-{session_id[:8]}-{uuid4()[:8]}",
    tags=[
        "role:companion",
        f"session:{session_id}",
        "specialization:generalist",
        "status:idle"
    ],
    memory_blocks=[...],
    tools=[...]
)
```

#### Querying by Tags

```python
# Find all Companions in a session
companions = [
    agent for agent in client.agents.list()
    if f"session:{session_id}" in (agent.tags or [])
    and "role:companion" in (agent.tags or [])
]
```

---

## Common Utilities

### `get_agent_tags` (Internal Helper)

Located at `tools/common/get_agent_tags.py`, this utility function retrieves agent tags via direct HTTP API calls instead of using the `letta_client` library.

**Why This Exists**:

The `letta_client` Python library has a known bug where agent tags are not parsed correctly from the API response. This affects multiple DCF+ tools that rely on tag-based filtering and status tracking.

**Workaround**:
```python
from tools.common.get_agent_tags import get_agent_tags

# Returns List[str] of tags for the agent
tags = get_agent_tags(agent_id)

# Check for specific tags
if "role:companion" in tags:
    # This is a Companion agent
    pass

if "status:idle" in tags:
    # Companion is available for work
    pass
```

**Files Using This Utility**:
- `delegate_task.py`
- `finalize_session.py`
- `update_companion_status.py`
- `cleanup_orphaned_companions.py`
- `broadcast_task.py`
- `read_session_activity.py`
- `report_task_result.py`

**Note**: This utility should be replaced with direct `letta_client` calls once the tag parsing bug is fixed upstream.

---

## DCF+ Tool Categories

### Companion Lifecycle Tools

Tools for managing the Companion pool.

#### `create_companion`

Creates a session-scoped Companion agent with standard configuration.

**Parameters**:
- `session_id`: Session identifier for tagging
- `conductor_id`: Conductor's agent ID (for result reporting)
- `specialization`: Initial specialization ("generalist" | "research" | "analysis" | "writing" | ...)
- `shared_block_ids_json`: JSON array of block IDs to attach (e.g., session_context)
- `initial_skills_json`: Optional JSON array of skill URIs to pre-load

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "companion_id": str,
    "companion_name": str,
    "tags": List[str],
    "shared_blocks_attached": List[str]
}
```

**Implementation Notes**:
- Attaches `send_message_to_agent_async` tool for Conductor communication
- Creates standard memory blocks: `persona`, `task_context`, `dcf_active_skills`
- Attaches shared blocks (session_context, etc.)
- Tags with `role:companion`, `session:{id}`, `specialization:{type}`, `status:idle`

#### `dismiss_companion`

Removes a Companion from the session and cleans up resources.

**Parameters**:
- `companion_id`: Companion agent ID to dismiss
- `unload_skills`: Whether to unload skills before deletion (default: true)
- `detach_shared_blocks`: Whether to detach shared blocks (default: true)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "companion_id": str,
    "skills_unloaded": List[str],
    "blocks_detached": List[str]
}
```

#### `list_session_companions`

Lists all Companions in a session with their current state.

**Parameters**:
- `session_id`: Session identifier
- `include_status`: Include detailed status info (default: true)
- `specialization_filter`: Optional filter by specialization

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "session_id": str,
    "companions": [
        {
            "companion_id": str,
            "companion_name": str,
            "specialization": str,
            "status": str,  # "idle" | "busy" | "error"
            "current_task_id": str | None,
            "loaded_skills": List[str]
        }
    ],
    "count": int
}
```

#### `update_companion_status`

Updates a Companion's status tag and optionally other metadata.

**Parameters**:
- `companion_id`: Companion agent ID
- `status`: New status ("idle" | "busy" | "error")
- `specialization`: Optional new specialization
- `current_task_id`: Optional task ID being worked on

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "companion_id": str,
    "updated_tags": List[str],
    "previous_tags": List[str]
}
```

#### `cleanup_orphaned_companions`

Utility tool for cleaning up Companion agents that were not properly dismissed. This is useful for:
- Test failures before cleanup phase
- Ad-hoc testing without proper `finalize_session` calls
- Sessions that lost track of their `session_context_block_id`

**Parameters**:
- `session_id`: Optional session ID to filter by (if None, finds all sessions)
- `name_pattern`: Optional substring filter for Companion names (e.g., "test", "e2e")
- `include_tagless`: Whether to include agents that look like Companions by name but lack proper `role:companion` tag (default: false)
- `dry_run`: If true (default), only report what would be deleted without actually deleting

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "dry_run": bool,
    "companions_found": [
        {
            "id": str,
            "name": str,
            "session": str | None,
            "tags": List[str]
        }
    ],
    "companions_deleted": List[str],  # Only populated if dry_run=False
    "warnings": List[str]
}
```

**Usage Examples**:
```python
# Preview orphaned companions from a specific session
result = cleanup_orphaned_companions(session_id="test-session-001", dry_run=True)

# Delete all companions with "test" in the name
result = cleanup_orphaned_companions(name_pattern="test", dry_run=False)

# Find all companions including those with broken tags
result = cleanup_orphaned_companions(include_tagless=True, dry_run=True)

# Clean up ALL orphaned companions (use with caution)
result = cleanup_orphaned_companions(dry_run=False)
```

**Note**: This tool uses the `dismiss_companion` function internally when available, falling back to direct deletion if not. Always use `dry_run=True` first to preview what would be deleted.

### Session Management Tools

Tools for managing session state and shared memory.

#### `create_session_context`

Creates shared memory blocks for a new session.

**Parameters**:
- `session_id`: Unique session identifier
- `conductor_id`: Conductor agent ID
- `initial_goals_json`: Optional initial goals
- `initial_preferences_json`: Optional user preferences

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "session_id": str,
    "blocks_created": {
        "session_context": str,  # block_id
        "delegation_log": str,   # block_id
        "strategist_guidelines": str  # block_id
    }
}
```

#### `update_session_context`

Updates the shared session context block.

**Parameters**:
- `session_id`: Session identifier
- `goals_json`: Optional updated goals
- `preferences_json`: Optional updated preferences
- `add_active_task_json`: Optional task to add to active tracking
- `complete_task_id`: Optional task ID to move to completed

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "session_id": str,
    "updated_fields": List[str]
}
```

#### `finalize_session`

Cleans up a session: dismisses all Companions, detaches shared blocks.

**Parameters**:
- `session_id`: Session identifier
- `conductor_id`: Conductor agent ID
- `delete_companions`: Whether to delete Companions (default: true)
- `archive_session_data`: Whether to persist session data to files (default: true)
- `archive_path`: Path for archived data (default: `/app/sessions/{session_id}/`)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "session_id": str,
    "companions_dismissed": int,
    "blocks_cleaned": int,
    "archive_path": str | None
}
```

### Task Delegation Tools

Tools for delegating and tracking tasks. These tools implement the complete delegation lifecycle with proper logging for Strategist analysis.

#### `delegate_task`

Delegates a task to a specific Companion with full tracking and messaging.

**Complete Delegation Flow**:
1. Validates Companion exists and is not already busy
2. Updates Companion status to "busy" with task tag
3. Updates Companion's `task_context` with task details
4. Writes delegation record to Conductor's `delegation_log` (for Strategist analysis)
5. Sends `task_delegation` message to Companion via Letta messaging
6. Returns delegation status with run_id for tracking

**Parameters**:
- `conductor_id`: Conductor agent ID (to find delegation_log block)
- `companion_id`: Target Companion agent ID
- `session_id`: Session identifier
- `task_id`: Unique task identifier
- `description`: Task description
- `required_skills_json`: JSON array of skill URIs needed (e.g., `["skill://research.web@0.2.0"]`)
- `input_json`: Optional JSON object with task inputs
- `priority`: Task priority ("low" | "normal" | "high")
- `timeout_seconds`: Optional task timeout

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "task_id": str,
    "companion_id": str,
    "message_sent": bool,
    "delegation_logged": bool,  # Whether delegation_log was updated
    "run_id": str | None        # Letta message run ID
}
```

**Delegation Log Record** (written to Conductor's `delegation_log` block):
```json
{
    "task_id": "uuid",
    "companion_id": "uuid",
    "skills_assigned": ["skill://research.web@0.2.0"],
    "status": "pending",
    "delegated_at": "ISO-8601",
    "completed_at": null,
    "duration_s": null,
    "result_status": null
}
```

**Error Conditions**:
- Companion not found → returns error
- Companion already busy → returns error with current task info
- Delegation log update fails → continues (non-fatal)
- Message send fails → returns error

#### `report_task_result`

**Used by**: Companion agents

Reports task completion from Companion back to Conductor. This is the Companion's counterpart to `delegate_task`.

**Complete Reporting Flow**:
1. Updates Companion's `task_context` with structured result
2. Updates Companion status to "idle" (or "error" on failure)
3. Updates `delegation_log` on Conductor with completion status and metrics
4. Sends structured `task_result` message to Conductor

**Parameters**:
- `companion_id`: This Companion's agent ID
- `task_id`: The task ID from the delegation message
- `conductor_id`: The Conductor's agent ID (from `task_delegation.from_conductor`)
- `status`: Result status ("succeeded" | "failed" | "partial")
- `summary`: Human-readable 1-2 sentence summary of results
- `output_data_json`: Optional JSON object with structured output data
- `artifacts_json`: Optional JSON array of artifacts `[{type, value, note}]`
- `error_code`: Error code if status is "failed" (e.g., "skill_load_error")
- `error_message`: Error message if status is "failed"
- `metrics_json`: Optional JSON object with execution metrics `{duration_s, tool_calls, etc.}`

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "task_id": str,
    "companion_id": str,
    "conductor_id": str,
    "message_sent": bool,
    "delegation_log_updated": bool,
    "run_id": str | None
}
```

**Result Message** (sent to Conductor):
```json
{
    "type": "task_result",
    "task_id": "uuid",
    "status": "succeeded",
    "output": {
        "summary": "Found 5 recent articles on quantum computing...",
        "data": { ... },
        "artifacts": [{ "type": "path", "value": "/app/sessions/.../report.md" }]
    },
    "metrics": {
        "duration_s": 45.2,
        "tool_calls": 7,
        "skills_used": ["skill://research.web@0.2.0"]
    },
    "companion_id": "uuid",
    "completed_at": "ISO-8601"
}
```

**On Failure**:
```json
{
    "type": "task_result",
    "task_id": "uuid",
    "status": "failed",
    "output": { "summary": "Web search failed - no results found" },
    "error": {
        "code": "skill_execution_error",
        "message": "Web search returned no results for the given query"
    },
    "metrics": { "duration_s": 5.2, "tool_calls": 2 },
    "companion_id": "uuid",
    "completed_at": "ISO-8601"
}
```

#### `broadcast_task`

Broadcasts a task to all available Companions matching criteria.

**Parameters**:
- `session_id`: Session identifier
- `task_id`: Unique task identifier
- `description`: Task description
- `skills_required_json`: JSON array of skill URIs needed
- `specialization_filter`: Optional specialization requirement
- `status_filter`: Only notify Companions with this status (default: "idle")

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "task_id": str,
    "companions_notified": List[str],
    "companions_skipped": List[str]
}
```

### Strategist Integration Tools

Tools that establish and manage the Conductor-Strategist relationship (parallel to Phase 1's Planner-Reflector integration).

#### `register_strategist`

Establishes a bidirectional memory sharing relationship between a Conductor and Strategist agent. This is the Phase 2 equivalent of `register_reflector`.

**Actions**:
1. Creates `strategist_registration` block on Conductor (stores Strategist ID)
2. Creates `strategist_guidelines` block on Conductor (shared, writable by Strategist)
3. Creates `delegation_log` block on Conductor (shared, readable by Strategist)
4. Records Conductor reference in Strategist's memory (`conductor_reference` block)
5. Attaches shared blocks to both agents for bidirectional access

**Parameters**:
- `conductor_agent_id`: The Conductor agent's UUID
- `strategist_agent_id`: The Strategist agent's UUID
- `initial_guidelines_json`: Optional initial guidelines structure

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "registration_block_id": str,
    "guidelines_block_id": str,
    "delegation_log_block_id": str,
    "warnings": List[str]
}
```

#### `trigger_strategist_analysis`

Triggers the Strategist agent to analyze recent session activity. This is the Phase 2 equivalent of `trigger_reflection`, but can be called during an active session (not just after completion).

**Analysis Event Payload**:
```json
{
  "type": "analysis_event",
  "session_id": "...",
  "conductor_id": "...",
  "trigger_reason": "periodic|milestone|on_demand|task_completed",
  "context": {
    "tasks_since_last_analysis": N,
    "time_since_last_analysis_s": N,
    "recent_failures": N
  },
  "triggered_at": "ISO-8601"
}
```

**Parameters**:
- `session_id`: Session UUID
- `conductor_agent_id`: Conductor's UUID (to find registered Strategist)
- `trigger_reason`: Why analysis was triggered ("periodic" | "milestone" | "on_demand" | "task_completed")
- `include_full_history`: Include complete session history (default: false)
- `async_message`: Send asynchronously (default: true)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "strategist_agent_id": str,
    "message_sent": bool,
    "run_id": str | None  # If async
}
```

**Usage Notes**:
- Call periodically (e.g., every 3-5 task completions) for continuous optimization
- Call on milestones (significant errors, scaling events) for immediate analysis
- The Strategist will read `delegation_log` and `session_context` to perform analysis

---

### Strategist Observation Tools

Tools for the Strategist agent to observe session activity and publish recommendations.

#### `read_session_activity`

Reads comprehensive session activity for Strategist analysis. Primary data source is the Conductor's `delegation_log` block, combined with Companion states and calculated skill metrics.

**Data Sources**:
1. **`delegation_log`** (from Conductor) — Primary source of truth for task outcomes
2. **`session_context`** (shared block) — Session state and goals
3. **Companion agents** (queried by tags) — Current status and task history

**Parameters**:
- `session_id`: Session identifier
- `conductor_id`: Optional Conductor ID (enables direct delegation_log access)
- `session_context_block_id`: Optional block ID (if known, avoids lookup)
- `include_companion_details`: Include detailed Companion information (default: true)
- `include_task_history`: Include task history from Companions (default: true)
- `include_skill_metrics`: Calculate skill success rates and metrics (default: true)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "session_id": str,
    "session_state": str,  # "active" | "paused" | "completed" | "unknown"
    "session_context": dict,  # Full session context if found
    "delegations": [  # From delegation_log (last 50)
        {
            "task_id": str,
            "companion_id": str,
            "skills_assigned": List[str],
            "status": str,  # "pending" | "completed"
            "delegated_at": str,
            "completed_at": str | None,
            "duration_s": float | None,
            "result_status": str | None,  # "succeeded" | "failed" | "partial"
            "error_code": str | None
        }
    ],
    "companions": [
        {
            "companion_id": str,
            "companion_name": str,
            "specialization": str,
            "status": str,  # "idle" | "busy" | "error"
            "current_task": str | None,
            "tasks_completed": int,
            "tasks_failed": int,
            "skills_used": List[str],
            "loaded_skills": List[str],  # Currently loaded
            "task_history": List[dict]  # If include_task_history=true
        }
    ],
    "skill_metrics": {  # Calculated from delegation_log
        "<skill_uri>": {
            "usage_count": int,
            "success_count": int,
            "failure_count": int,
            "pending_count": int,
            "avg_duration_s": float | None,
            "success_rate": float | None,  # Percentage (0-100)
            "failure_modes": [
                { "mode": str, "count": int }
            ]
        }
    },
    "metrics": {
        "companion_count": int,
        "idle_companions": int,
        "busy_companions": int,
        "error_companions": int,
        "total_delegations": int,
        "completed_tasks": int,
        "failed_tasks": int,
        "pending_tasks": int,
        "success_rate": float,  # Percentage (0-100)
        "avg_task_duration_s": float | None,
        "unique_skills_used": int,
        "top_skills": List[Tuple[str, int, float]]  # (skill, usage_count, success_rate)
    }
}
```

#### `update_conductor_guidelines`

Publishes strategic recommendations to the Conductor's `strategist_guidelines` block.

**Parameters**:
- `conductor_id`: Conductor agent ID
- `recommendation_json`: General recommendation to add
- `skill_preferences_json`: Skill preferences by task type (e.g., `{"research": "skill://..."}`)
- `companion_scaling_json`: Scaling thresholds (e.g., `{"min": 1, "max": 5}`)
- `warning_json`: Warning to add (with severity)
- `clear_recommendations`: Clear existing recommendations before adding (default: false)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "conductor_id": str,
    "guidelines_block_id": str,
    "revision": int,
    "updated_fields": List[str]
}
```

**Guidelines Block Structure**:
```json
{
  "last_updated": "ISO-8601",
  "revision": N,
  "recommendations": [
    { "timestamp": "...", "text": "...", "confidence": 0.85 }
  ],
  "skill_preferences": {
    "<task_type>": "<preferred_skill_uri>"
  },
  "companion_scaling": {
    "min_companions": 1,
    "max_companions": 5,
    "scale_up_threshold": 3,
    "scale_down_threshold": 0
  },
  "warnings": [
    { "severity": "high", "message": "...", "timestamp": "..." }
  ]
}
```

---

## Agent Tool Assignment

Each agent type requires a specific set of tools. Use this table when configuring agents in Letta.

### Conductor Agent Tools

| Tool | Required | Purpose |
|------|----------|---------|
| **Session & Companion Management** | | |
| `create_session_context` | ✅ | Initialize session shared blocks |
| `update_session_context` | ✅ | Update session state and announcements |
| `finalize_session` | ✅ | Close session and cleanup |
| `create_companion` | ✅ | Spawn new Companions |
| `dismiss_companion` | ✅ | Remove Companions |
| `list_session_companions` | ✅ | Query Companion pool and status |
| `update_companion_status` | ⚪ | Update Companion tags |
| `cleanup_orphaned_companions` | ⚪ | Clean up orphaned Companions (utility) |
| **Task Delegation** | | |
| `delegate_task` | ✅ | Assign tasks to specific Companion |
| `broadcast_task` | ⚪ | Broadcast to multiple Companions |
| **Skill Management (Authority)** | | |
| `get_skillset` | ✅ | Discover available skills |
| `get_skillset_from_catalog` | ⚪ | Alternative skill discovery |
| `load_skill` | ✅ | Load skills to Companions |
| `unload_skill` | ✅ | Unload skills from Companions |
| **Strategist Integration** | | |
| `register_strategist` | ✅ | Establish Strategist relationship |
| `trigger_strategist_analysis` | ⚪ | Request Strategist analysis |
| **Letta Native** | | |
| `send_message_to_agent_async` | ✅ | Communicate with Companions/Strategist |
| `send_message_to_agents_matching_all_tags` | ⚪ | Broadcast to agent groups |
| **File Operations** | | |
| `write_file` | ⚪ | Persist session artifacts |
| `create_directory` | ⚪ | Create session directories |

### Companion Agent Tools

| Tool | Required | Purpose |
|------|----------|---------|
| **Skill Execution** | | |
| `load_skill` | ✅ | Load assigned skills |
| `unload_skill` | ✅ | Unload skills after task |
| **Status Management** | | |
| `update_companion_status` | ⚪ | Update own status (handled by report_task_result) |
| **Task Reporting** | | |
| `report_task_result` | ✅ | Report task completion to Conductor (updates status, delegation_log, sends message) |
| **Communication** | | |
| `send_message_to_agent_async` | ⚪ | Direct messaging (use report_task_result for task results) |
| **File Operations** | | |
| `read_file` | ⚪ | Read input files |
| `write_file` | ⚪ | Write output artifacts |
| **Dynamic Tools** | | |
| *(skill-specific tools)* | ✅ | Loaded dynamically via `load_skill` |

### Strategist Agent Tools

| Tool | Required | Purpose |
|------|----------|---------|
| **Session Observation** | | |
| `read_session_activity` | ✅ | Analyze session patterns |
| `read_shared_memory_blocks` | ✅ | Access Conductor's memory blocks |
| **Guidelines Publishing** | | |
| `update_conductor_guidelines` | ✅ | Publish recommendations |
| **Communication** | | |
| `send_message_to_agent_async` | ✅ | Send proactive advice to Conductor |
| **Knowledge Graph (Graphiti MCP)** | | |
| `add_episode` | ✅ | Persist patterns and insights |
| `search_nodes` | ✅ | Find similar entity patterns |
| `search_facts` | ✅ | Query skill performance relationships |

**Legend**: ✅ = Required, ⚪ = Optional/Situational

### Tool Assignment Diagram

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                          DCF+ Tool Distribution                                │
├────────────────────────────────────────────────────────────────────────────────┤
│  CONDUCTOR (18 tools)       │  COMPANION (8 tools)      │  STRATEGIST (7 tools)│
├─────────────────────────────┼───────────────────────────┼──────────────────────┤
│  Session:                   │  Skills:                  │  Observation:        │
│    create_session_context   │    load_skill             │    read_session_     │
│    update_session_context   │    unload_skill           │      activity        │
│    finalize_session         │                           │    read_shared_      │
│                             │  Task Reporting:          │      memory_blocks   │
│  Companions:                │    report_task_result     │                      │
│    create_companion         │                           │  Guidelines:         │
│    dismiss_companion        │  Status (optional):       │    update_conductor_ │
│    list_session_companions  │    update_companion_      │      guidelines      │
│    update_companion_status  │      status               │                      │
│                             │                           │  Communication:      │
│  Delegation:                │  Communication:           │    send_message_to_  │
│    delegate_task            │    send_message_to_       │      agent_async     │
│    broadcast_task           │      agent_async          │                      │
│                             │                           │  Graphiti MCP:       │
│  Skills (Authority):        │  Files:                   │    add_episode       │
│    get_skillset             │    read_file              │    search_nodes      │
│    get_skillset_from_       │    write_file             │    search_facts      │
│      catalog                │                           │                      │
│    load_skill               │  + Skill-specific tools   │                      │
│    unload_skill             │    (loaded dynamically)   │                      │
│                             │                           │                      │
│  Strategist:                │                           │                      │
│    register_strategist      │                           │                      │
│    trigger_strategist_      │                           │                      │
│      analysis               │                           │                      │
│                             │                           │                      │
│  Letta Native:              │                           │                      │
│    send_message_to_         │                           │                      │
│      agent_async            │                           │                      │
│    send_message_to_agents_  │                           │                      │
│      matching_all_tags      │                           │                      │
│                             │                           │                      │
│  Files:                     │                           │                      │
│    write_file               │                           │                      │
│    create_directory         │                           │                      │
└─────────────────────────────┴───────────────────────────┴──────────────────────┘
```

---

## Agent Specifications

### Conductor Agent

#### Memory Blocks

| Label | Shared | Purpose |
|-------|--------|---------|
| `persona` | No | Conductor identity and behavior |
| `session_context` | Yes | Shared session state (attached to all Companions) |
| `strategist_guidelines` | Yes | Recommendations from Strategist (read-only for Conductor) |
| `strategist_registration` | No | Registered Strategist ID |
| `companion_registry` | No | Local tracking of active Companions |
| `delegation_log` | Yes | Task delegation history (for Strategist analysis) |

### Companion Agent

#### Memory Blocks

| Label | Shared | Purpose |
|-------|--------|---------|
| `persona` | No | Companion identity and specialization |
| `task_context` | No | Current task details and history |
| `session_context` | Yes (read-mostly) | Shared session state from Conductor |
| `dcf_active_skills` | No | Skill loading tracker |

### Strategist Agent

#### Memory Blocks

| Label | Shared | Purpose |
|-------|--------|---------|
| `persona` | No | Strategist identity and analysis approach |
| `session_context` | Yes (read-only) | Observe session state |
| `strategist_guidelines` | Yes | Publish recommendations to Conductor |
| `conductor_reference` | No | Reference to registered Conductor |
| `observation_buffer` | No | Temporary analysis workspace |
| `pattern_library` | No | Recognized patterns from analysis |

---

## Message Protocols

### Task Delegation Message

Sent from Conductor to Companion via `send_message_to_agent_async`:

```json
{
    "type": "task_delegation",
    "task_id": "uuid",
    "description": "Research recent advances in quantum computing",
    "skills_required": ["skill://research.web@0.2.0"],
    "context": {
        "user_query": "What's new in quantum computing?",
        "constraints": {"max_sources": 5, "recency": "2025-2026"}
    },
    "priority": "normal",
    "conductor_id": "uuid",
    "session_id": "uuid",
    "delegated_at": "ISO-8601"
}
```

### Task Result Message

Sent from Companion to Conductor via `send_message_to_agent_async`:

```json
{
    "type": "task_result",
    "task_id": "uuid",
    "status": "succeeded",
    "output": {
        "summary": "Recent quantum computing advances include...",
        "sources": [...],
        "artifacts": [...]
    },
    "metrics": {
        "duration_s": 45,
        "tool_calls": 3,
        "skills_used": ["skill://research.web@0.2.0"]
    },
    "companion_id": "uuid",
    "completed_at": "ISO-8601"
}
```

### Task Progress Message (Optional)

For long-running tasks:

```json
{
    "type": "task_progress",
    "task_id": "uuid",
    "progress_pct": 50,
    "status_message": "Found 3 sources, analyzing...",
    "companion_id": "uuid",
    "updated_at": "ISO-8601"
}
```

### Strategic Advice Message

Sent from Strategist to Conductor:

```json
{
    "type": "strategic_advice",
    "advice_type": "companion_specialization",
    "recommendation": "Consider keeping Companion-A specialized for research tasks",
    "evidence": {
        "research_tasks_completed": 5,
        "success_rate": 1.0,
        "avg_duration_s": 30
    },
    "confidence": 0.85,
    "strategist_id": "uuid",
    "advised_at": "ISO-8601"
}
```

---

## Graphiti Entity Types

The Strategist persists patterns and metrics to Graphiti for institutional learning. These entity types parallel Phase 1's `WorkflowExecution`, `LearningInsight`, and `SkillMetric`.

### Entity Type Definitions

| Entity | Group ID | Purpose | Parallel in Phase 1 |
|--------|----------|---------|---------------------|
| `SessionPattern:<session_id>` | `dcf_plus_patterns` | Behavioral patterns from a session | `WorkflowExecution` |
| `SkillMetric:<skill_id>:<date>` | `dcf_plus_metrics` | Aggregated skill performance | `SkillMetric` |
| `Insight:<insight_id>` | `dcf_plus_insights` | Strategic insights with evidence | `LearningInsight` |
| `CompanionPattern:<companion_id>` | `dcf_plus_companions` | Companion specialization patterns | N/A (new) |

### SessionPattern Schema

```json
{
  "entity": "SessionPattern",
  "session_id": "uuid",
  "conductor_id": "uuid",
  "duration_s": 3600,
  "task_count": 15,
  "success_rate": 0.87,
  "companion_count_avg": 2.5,
  "skill_usage": {
    "skill://research.web@0.2.0": { "count": 8, "success_rate": 0.95 },
    "skill://analysis.data@0.1.0": { "count": 5, "success_rate": 0.80 }
  },
  "patterns_observed": [
    "High parallelism with 3+ Companions improved throughput",
    "Research tasks succeeded more with specialized Companions"
  ],
  "recorded_at": "ISO-8601"
}
```

### SkillMetric Schema

```json
{
  "entity": "SkillMetric",
  "skill_id": "skill://research.web@0.2.0",
  "date": "2026-01-30",
  "usage_count": 25,
  "success_count": 23,
  "failure_count": 2,
  "success_rate": 0.92,
  "avg_duration_s": 45.2,
  "failure_modes": [
    { "mode": "timeout", "count": 1 },
    { "mode": "no_results", "count": 1 }
  ],
  "companions_used": ["uuid1", "uuid2"],
  "recorded_at": "ISO-8601"
}
```

### Insight Schema

```json
{
  "entity": "Insight",
  "insight_id": "uuid",
  "category": "skill_preference|companion_scaling|specialization|warning",
  "confidence": 0.85,
  "evidence_count": 5,
  "summary": "skill://research.web@0.2.0 outperforms v0.1.0 by 23%",
  "recommendation": "Prefer v0.2.0 for all research tasks",
  "applies_to": ["skill://research.web", "task_type:research"],
  "derived_from": ["session_id_1", "session_id_2"],
  "supersedes": "previous_insight_id",
  "created_at": "ISO-8601"
}
```

### CompanionPattern Schema

```json
{
  "entity": "CompanionPattern",
  "companion_id": "uuid",
  "session_id": "uuid",
  "specialization": "research",
  "tasks_completed": 8,
  "tasks_failed": 0,
  "success_rate": 1.0,
  "avg_task_duration_s": 32.5,
  "skills_used": ["skill://research.web@0.2.0"],
  "specialization_fit": 0.95,
  "recorded_at": "ISO-8601"
}
```

---

## Tool Usage Flows

### Conductor Tool Usage Flow

```
1. create_session_context()           → Initialize session shared blocks
2. register_strategist()              → Establish Strategist relationship (optional)
3. create_companion()                 → Spawn initial Companions
4. (Conversation with user)
5. get_skillset()                     → Discover available skills
6. (Check strategist_guidelines)      → Read Strategist recommendations
7. delegate_task()                    → Delegate to Companion with required_skills
8. (Receive task_result message)      → Process Companion results
9. update_session_context()           → Track task completion
10. trigger_strategist_analysis()     → Request optimization (every 3-5 tasks)
11. (Loop 4-10 for ongoing conversation)
12. finalize_session()                → Close session, dismiss Companions

Companion management during session:
• create_companion()                  → Scale up when needed
• dismiss_companion()                 → Scale down idle Companions
• list_session_companions()           → Monitor pool status
• update_companion_status()           → Update specializations
```

### Companion Tool Usage Flow

```
1. (Receive task_delegation message from Conductor)
   ├── Validate message type == "task_delegation"
   └── Extract task_id, from_conductor, required_skills, input
2. load_skill()                       → Load each skill in task.required_skills
   └── On failure: report_task_result(status="failed") immediately
3. (Execute task using skill tools)
   ├── Follow loaded skill's directive
   ├── Reference task.input for context
   └── Write large artifacts to disk
4. report_task_result()               → Complete reporting flow
   ├── Updates task_context with result
   ├── Updates status to "idle" (or "error" on failure)
   ├── Updates delegation_log for Strategist
   └── Sends task_result message to Conductor
5. unload_skill()                     → Cleanup all loaded skills
6. (Wait for next delegation)
```

**Note**: The `report_task_result` tool handles status updates automatically. Do not call `update_companion_status` separately when reporting results.

### Strategist Tool Usage Flow

```
1. (Receive analysis_event message from trigger_strategist_analysis)
   ├── session_id, conductor_id, trigger_reason

2. read_shared_memory_blocks()        → Access Conductor's memory
   ├── delegation_log, session_context
   └── strategist_guidelines (current state)

3. read_session_activity()            → Get detailed activity data
   ├── Task delegations with outcomes
   ├── Companion states and performance
   └── Skill usage metrics

4. (Query Graphiti for historical context)
   ├── search_nodes()                 → Find similar sessions
   ├── search_facts()                 → Get skill performance history
   └── search_nodes()                 → Retrieve past insights

5. (Analyze patterns and derive insights)
   ├── Compare with historical data
   ├── Identify skill effectiveness
   ├── Evaluate Companion performance
   └── Generate recommendations

6. (Persist to Graphiti)
   ├── add_episode()                  → SessionPattern record
   ├── add_episode()                  → SkillMetric records
   ├── add_episode()                  → Insight records
   └── add_episode()                  → CompanionPattern records

7. update_conductor_guidelines()      → Publish to Conductor
   ├── skill_preferences              → Recommended skills by task type
   ├── companion_scaling              → Scaling thresholds
   ├── recommendations                → General advice
   └── warnings                       → Issues to avoid
```

---

## Implementation Roadmap

### Phase 2.1: Foundation

1. [x] Create `create_companion` tool
2. [x] Create `dismiss_companion` tool
3. [x] Create `list_session_companions` tool
4. [x] Create `create_session_context` tool
5. [x] Create `finalize_session` tool
6. [x] Write Conductor system prompt (`prompts/dcf_plus/Conductor.md`)
7. [x] Write Companion system prompt (`prompts/dcf_plus/Companion.md`)
8. [x] Create shared `get_agent_tags` utility (workaround for letta_client tag parsing bug)
9. [x] Create `cleanup_orphaned_companions` utility tool

### Phase 2.2: Delegation

1. [x] Create `delegate_task` tool
2. [x] Create `broadcast_task` tool
3. [x] Create `update_companion_status` tool
4. [x] Create `update_session_context` tool
5. [x] **Enhance `delegate_task`** — Now sends messages, writes to delegation_log
6. [x] **Create `report_task_result` tool** — Companion result reporting with full tracking
7. [x] **Enhance `read_session_activity`** — Reads delegation_log, calculates skill metrics
8. [ ] Test Conductor → Companion delegation flow
9. [ ] Test Companion → Conductor result reporting

### Phase 2.3: Strategist Integration

1. [x] Create `read_session_activity` tool
2. [x] Create `update_conductor_guidelines` tool
3. [x] **Create `register_strategist` tool** (parallel to `register_reflector`)
4. [x] **Create `trigger_strategist_analysis` tool** (parallel to `trigger_reflection`)
5. [x] Write Strategist system prompt (`prompts/dcf_plus/Strategist.md`)
6. [x] Add `read_shared_memory_blocks` to Strategist tool set (reuse from Phase 1)
7. [ ] Integrate with Graphiti for pattern persistence
8. [ ] Test end-to-end Conductor ↔ Companion ↔ Strategist flow

### Phase 2.4: Integration

1. [ ] Create Conductor agent template (`.af` format)
2. [ ] Create Companion agent template
3. [ ] Create Strategist agent template
4. [x] Update DCF MCP server to register dcf_plus tools
5. [ ] Write integration tests
6. [ ] Update documentation

---

## References

- [Letta Multi-agent systems](https://docs.letta.com/guides/agents/multi-agent/)
- [Letta Multi-agent shared memory](https://docs.letta.com/guides/agents/multi-agent-shared-memory)
- [Letta Memory blocks](https://docs.letta.com/guides/agents/memory-blocks/)
- [Letta Python SDK](https://docs.letta.com/api/python/)
- [`docs/Architectural_Evolution_Opus.md`](../../../docs/Architectural_Evolution_Opus.md) — Pattern taxonomy
- [`dcf_mcp/tools/TOOLS.md`](../TOOLS.md) — Phase 1 (dcf) tools
