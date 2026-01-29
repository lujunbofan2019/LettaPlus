# DCF+ Tools Documentation

> **Phase**: 2 (Delegated Execution)
> **Status**: Design Specification
> **Last Updated**: 2026-01-29

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
│                      SKILL MANAGEMENT FLOW                       │
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
    "updated_tags": List[str]
}
```

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

Tools for delegating and tracking tasks.

#### `delegate_task`

Delegates a task to a specific Companion.

**Parameters**:
- `companion_id`: Target Companion agent ID
- `task_id`: Unique task identifier
- `description`: Task description
- `skills_required_json`: JSON array of skill URIs needed
- `context_json`: Optional context/inputs for the task
- `priority`: Task priority ("low" | "normal" | "high")
- `update_session_context`: Whether to track in session context (default: true)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "task_id": str,
    "companion_id": str,
    "message_sent": bool,
    "delegation_payload": dict
}
```

**Implementation Notes**:
- Uses `send_message_to_agent_async` internally
- Updates Companion status to "busy"
- Logs delegation in session context

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

### Strategist Tools

Tools for the Strategist agent to observe and advise.

#### `read_session_activity`

Reads recent session activity for analysis.

**Parameters**:
- `session_id`: Session identifier
- `include_delegation_log`: Include task delegations (default: true)
- `include_companion_states`: Include Companion status history (default: true)
- `time_window_minutes`: How far back to look (default: 60)

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "session_id": str,
    "activity": {
        "delegations": [...],
        "companion_states": [...],
        "task_completions": [...],
        "errors": [...]
    }
}
```

#### `update_conductor_guidelines`

Publishes strategic recommendations to the Conductor.

**Parameters**:
- `conductor_id`: Conductor agent ID
- `add_recommendation_json`: Recommendation to add
- `add_warning_json`: Warning to add
- `update_companion_strategy_json`: Companion management advice

**Returns**:
```python
{
    "status": str | None,
    "error": str | None,
    "conductor_id": str,
    "guidelines_block_id": str,
    "revision": int
}
```

---

## Agent Specifications

### Conductor Agent

#### Required Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `send_message_to_agent_async` | Letta built-in | Delegate tasks, receive results |
| `send_message_to_agents_matching_all_tags` | Letta built-in | Broadcast to Companions |
| `create_companion` | DCF+ | Spawn new Companions |
| `dismiss_companion` | DCF+ | Remove Companions |
| `list_session_companions` | DCF+ | Query Companion pool |
| `delegate_task` | DCF+ | Assign tasks |
| `update_session_context` | DCF+ | Manage shared state |
| `finalize_session` | DCF+ | Clean up session |
| `load_skill` | DCF (reused) | Load skills to Companions |
| `unload_skill` | DCF (reused) | Unload skills from Companions |

#### Memory Blocks

| Label | Shared | Purpose |
|-------|--------|---------|
| `persona` | No | Conductor identity and behavior |
| `session_context` | Yes | Shared session state |
| `companion_registry` | No | Local tracking of Companions |
| `strategist_guidelines` | Yes | Recommendations from Strategist |
| `delegation_log` | Yes | Task delegation history (for Strategist) |

### Companion Agent

#### Required Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `send_message_to_agent_async` | Letta built-in | Report results to Conductor |
| `load_skill` | DCF (reused) | Load assigned skills |
| `unload_skill` | DCF (reused) | Unload skills after task |
| *(skill-specific tools)* | Dynamic | Loaded via skills |

#### Memory Blocks

| Label | Shared | Purpose |
|-------|--------|---------|
| `persona` | No | Companion identity |
| `task_context` | No | Current task details |
| `session_context` | Yes (read-mostly) | Shared session state |
| `dcf_active_skills` | No | Skill loading tracker |

### Strategist Agent

#### Required Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `send_message_to_agent_async` | Letta built-in | Advise Conductor |
| `read_session_activity` | DCF+ | Observe patterns |
| `update_conductor_guidelines` | DCF+ | Publish recommendations |
| `read_shared_memory_blocks` | DCF (reused) | Access Conductor memory |
| *(Graphiti tools)* | Graphiti MCP | Pattern persistence |

#### Memory Blocks

| Label | Shared | Purpose |
|-------|--------|---------|
| `persona` | No | Strategist identity |
| `session_context` | Yes (read-only) | Observe session state |
| `strategist_guidelines` | Yes | Publish recommendations |
| `observation_buffer` | No | Temporary analysis workspace |
| `pattern_library` | No | Recognized patterns |

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

## Implementation Roadmap

### Phase 2.1: Foundation

1. [x] Create `create_companion` tool
2. [x] Create `dismiss_companion` tool
3. [x] Create `list_session_companions` tool
4. [x] Create `create_session_context` tool
5. [x] Create `finalize_session` tool
6. [x] Write Conductor system prompt (`prompts/dcf_plus/Conductor.md`)
7. [x] Write Companion system prompt (`prompts/dcf_plus/Companion.md`)

### Phase 2.2: Delegation

1. [x] Create `delegate_task` tool
2. [x] Create `broadcast_task` tool
3. [x] Create `update_companion_status` tool
4. [x] Create `update_session_context` tool
5. [ ] Test Conductor → Companion delegation flow
6. [ ] Test Companion → Conductor result reporting

### Phase 2.3: Strategist

1. [x] Create `read_session_activity` tool
2. [x] Create `update_conductor_guidelines` tool
3. [x] Write Strategist system prompt (`prompts/dcf_plus/Strategist.md`)
4. [ ] Integrate with Graphiti for pattern persistence
5. [ ] Test end-to-end Conductor ↔ Companion ↔ Strategist flow

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
