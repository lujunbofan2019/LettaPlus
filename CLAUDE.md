# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LettaPlus** is a self-evolving agentic AI architecture that enables autonomous agents to learn, adapt, and improve through experience. The system addresses two fundamental limitations of current agentic systems:

1. **Stateless, Amnesiac Design**: Most agent systems fragment knowledge across isolated conversation threads
2. **Static, Pre-defined Capabilities**: Agents cannot acquire new abilities at runtime

LettaPlus solves these by unifying three core innovations:

- **Dynamic Capabilities Framework (DCF)**: Shifts modularity from specialized agents to transferable, version-controlled "skills" that can be loaded/unloaded at runtime
- **Hybrid Memory System**: Combines a knowledge graph, hierarchical memory blocks, and vector stores for comprehensive context and structured reasoning
- **Dual Execution Patterns**: Supports both predetermined workflows (Phase 1) and dynamic task delegation (Phase 2)

### Execution Patterns

LettaPlus supports two complementary execution patterns:

| Pattern | Phase | Use Case |
|---------|-------|----------|
| **Workflow Execution** | Phase 1 (DCF) | Predetermined DAG workflows with ephemeral Workers |
| **Delegated Execution** | Phase 2 (DCF+) | Dynamic task delegation with session-scoped Companions |

### Key Concepts

#### Phase 1 (Workflow Execution)

- **Planner Agent**: User-facing agent that converses to understand intent, discovers skills, compiles SOPs into ASL state machines, and orchestrates execution
- **Ephemeral Workers**: Short-lived Letta agents instantiated from `.af v2` templates; load skills, execute tasks, write outputs, then optionally get deleted
- **Reflector Agent**: Post-workflow advisor that analyzes execution outcomes and publishes optimization recommendations
- **Workflows**: JSON-defined Standard Operating Procedures (SOPs) using ASL semantics with Letta-specific `AgentBinding` extensions
- **Choreography**: Workers self-coordinate via a RedisJSON control plane using leases, status updates, and notifications—no central orchestrator loop

#### Phase 2 (Delegated Execution)

- **Conductor Agent**: Continuously engaged orchestrator that dynamically delegates tasks to Companions during ongoing user conversations (skill authority)
- **Companion Agents**: Session-scoped executors that load skills assigned by the Conductor, execute tasks, and report results (simple executor pattern—never discover skills themselves)
- **Strategist Agent**: Real-time advisor providing continuous optimization recommendations during sessions; observes activity and publishes guidelines to the Conductor

#### Shared Concepts

- **Skills**: Self-contained, version-controlled JSON manifests defining capabilities (directives, tools, data sources, permissions, tests)

### Agent Role Comparison

| Role | Phase 1 (Workflow) | Phase 2 (Delegated) |
|------|-------------------|---------------------|
| Orchestrator | Planner | Conductor |
| Executor | Worker (ephemeral) | Companion (session-scoped) |
| Advisor | Reflector (post-workflow) | Strategist (real-time) |

### Vision

The system treats every engagement as an opportunity to refine institutional knowledge. Agents package capabilities as reusable skills, stitch skills into formal workflows, and preserve results in a layered memory fabric. Over time, the system behaves like an adaptive operations team that can compose best practices, collaborate safely, and evolve in response to new requirements.

## Architecture

### Directory Structure

| Directory | Purpose |
|-----------|---------|
| `dcf_mcp/` | Core MCP server exposing 40+ workflow/skill tools |
| `dcf_mcp/tools/dcf/` | Phase 1 workflow execution tools (validate, generate, leases, notify, finalize) |
| `dcf_mcp/tools/dcf_plus/` | Phase 2 delegated execution tools (Companion lifecycle, session management, task delegation, Strategist) |
| `dcf_mcp/tools/redis_json/` | RedisJSON operations for control plane |
| `dcf_mcp/tools/file_system/` | File operations |
| `dcf_mcp/agents/` | Letta agent templates (`.af` format) |
| `dcf_mcp/schemas/` | JSON schemas (workflow v2.2.0, skill v2.0.0, control/data plane) |
| `stub_mcp/` | Deterministic stub MCP server for BDD testing |
| `graphiti/` | Knowledge graph memory layer (FalkorDB backend) |
| `skills_src/` | YAML skill definitions and tool specifications |
| `generated/` | Generated artifacts: manifests, catalogs, stub config, registry, schemas |
| `workflows/` | Example workflow JSON files |
| `workflows/generated/` | Persisted workflow definitions |
| `workflows/runs/` | Execution audit trails (per workflow_id) |
| `prompts/` | Agent system prompts (Phase 1: Planner/Worker/Reflector; Phase 2: Conductor/Companion/Strategist) |
| `docs/` | Design documents and whitepapers |

### Hybrid Memory System

Three memory modalities work together:

1. **Knowledge Graph (Graphiti/FalkorDB)**: Temporally-aware graph storing entities, events, and relationships with performance statistics. Enables multi-hop reasoning (e.g., "Which skill version succeeded most for this task type?")

2. **Hierarchical Memory Blocks (Letta/MemGPT)**:
   - Working Memory: Recent conversational turns and short-term commitments
   - Archival Memory: Perpetual history with salience scores
   - Scratch Pads: Task-specific intermediate computations

3. **External Vector Store**: Semantic search for large documents (PDFs, manuals, code). Results are bundled into context alongside graph facts and memory notes.

### Control Plane (RedisJSON)

Workers coordinate via Redis without a central orchestrator:

- **Meta document**: `cp:wf:{workflow_id}:meta` — workflow metadata, dependency graph, agent assignments
- **State documents**: `cp:wf:{workflow_id}:state:{state_name}` — per-state status, lease info, timestamps
- **Data plane outputs**: `dp:wf:{workflow_id}:output:{state_name}` — worker outputs for downstream consumption
- **Audit records**: `dp:wf:{workflow_id}:audit:finalize` — finalization metadata

### Tool Categories

#### Phase 1 (Workflow Execution) Tools

**Planning Tools:**
- `validate_workflow` — JSON Schema validation + import resolution + ASL graph checks
- `validate_skill_manifest` — Schema validation + static checks
- `get_skillset` / `get_skillset_from_catalog` — Discover available skills
- `load_skill` / `unload_skill` — Attach/detach skills to agents

**Execution Tools:**
- `create_workflow_control_plane` — Seed control plane from ASL
- `create_worker_agents` — Instantiate workers from templates
- `read_workflow_control_plane` / `update_workflow_control_plane` — Read/write state
- `acquire_state_lease` / `renew_state_lease` / `release_state_lease` — Lease lifecycle
- `notify_next_worker_agent` / `notify_if_ready` — Worker notifications
- `finalize_workflow` — Compute final status, cleanup workers, write audit record

**Generation Tools:**
- `generate_all` — Generate skill manifests and stub config from YAML
- `yaml_to_manifests` — Generate skill manifests from YAML sources
- `yaml_to_stub_config` — Generate stub MCP server configuration

#### Phase 2 (Delegated Execution) Tools

**Companion Lifecycle:**
- `create_companion` — Create session-scoped Companion agent with standard configuration
- `dismiss_companion` — Remove Companion and cleanup resources (unload skills, detach blocks)
- `list_session_companions` — List Companions in session with current state (status, loaded skills)
- `update_companion_status` — Update Companion status tags ("idle" | "busy" | "error")

**Session Management:**
- `create_session_context` — Create shared memory blocks for a new session
- `update_session_context` — Update shared session state (goals, preferences, task tracking)
- `finalize_session` — Close session, dismiss Companions, archive session data

**Task Delegation:**
- `delegate_task` — Delegate task to specific Companion with required skills
- `broadcast_task` — Broadcast task to multiple Companions matching criteria

**Strategist Integration:**
- `register_strategist` — Establish Conductor-Strategist relationship (parallel to `register_reflector`)
- `trigger_strategist_analysis` — Trigger Strategist to analyze session activity (parallel to `trigger_reflection`)

**Strategist Observation:**
- `read_session_activity` — Analyze session activity for patterns (delegations, completions, errors)
- `update_conductor_guidelines` — Publish Strategist recommendations to Conductor's guidelines block

## Commands

### Docker (primary development method)

```bash
docker compose up --build          # Start full stack
docker compose logs -f dcf-mcp     # Follow DCF MCP logs
docker compose down                # Stop services
```

### Health checks

```bash
curl -sf http://localhost:8283/v1/health/  # Letta API
curl -sf http://localhost:8765/healthz      # Stub MCP
```

> **Note:** For comprehensive API calls, log observation, and troubleshooting, see the [Testing Environment](#testing-environment) section.

### Regenerate artifacts from YAML sources

```bash
# Generate all artifacts (manifests + stub config + registry)
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'

# Or individual generators
python -c 'from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests; yaml_to_manifests()'
python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
python -c 'from dcf_mcp.tools.dcf.yaml_to_registry import yaml_to_registry; yaml_to_registry()'
```

### Graphiti subproject (knowledge graph)

```bash
cd graphiti && uv sync --dev       # Install dependencies
cd graphiti && ruff format         # Format code
cd graphiti && ruff check          # Lint
cd graphiti && pytest              # Run tests
```

## Service Ports (Docker Compose)

| Service | Port | Purpose |
|---------|------|---------|
| Letta API | 8283 | Agent framework |
| DCF MCP | 8337 | Workflow tools (Streamable HTTP at `/mcp`) |
| Stub MCP | 8765 | Deterministic testing (Streamable HTTP at `/mcp`) |
| Graphiti MCP | 8000 | Knowledge graph (Streamable HTTP at `/mcp/`) |
| Redis Stack | 6379 | Control plane |
| FalkorDB | 8379 | Knowledge graph storage |

## YAML Skill Pipeline

Skills and tools are authored via YAML for clarity and maintainability. **YAML files are the human-editable source of truth; JSON files are machine-generated outputs.**

### Source Files (YAML - Human-Editable)

| File | Purpose |
|------|---------|
| `skills_src/skills/*.skill.yaml` | Individual skill definitions (one per file) |
| `skills_src/tools.yaml` | Tool specifications and test cases for simulation |
| `skills_src/registry.yaml` | MCP server resolver map (server ID → endpoint) |

### Generated Files (JSON - Machine-Readable)

| File | Generated From | Purpose |
|------|----------------|---------|
| `generated/manifests/skill.*.json` | `skills_src/skills/*.yaml` | Skill manifests for load_skill |
| `generated/catalogs/skills_catalog.json` | All skill manifests | Fast skill discovery index |
| `generated/stub/stub_config.json` | `skills_src/tools.yaml` | Stub MCP server configuration |
| `generated/registry.json` | `skills_src/registry.yaml` | MCP server endpoint resolution |
| `generated/schemas/*.json` | `skills_src/schemas/*.schema.yaml` | JSON Schemas for validation tools |

### Generation Pipeline

1. Author YAML source files in `skills_src/`
2. Run `generate_all()` to produce all JSON outputs:
   - `yaml_to_manifests` → skill manifests + catalog
   - `yaml_to_stub_config` → stub config
   - `yaml_to_registry` → registry.json
3. Stub MCP server hot-reloads config automatically
4. Switch to real backends by updating `skills_src/registry.yaml` and regenerating

> **Important:** Never edit files in `generated/` directly. Always modify the YAML sources and regenerate.

See `skills_src/SKILLS.md` for detailed authoring documentation.

## Execution Flows

### Phase 1: Workflow Execution Flow

#### Planner Flow

**Planning Phase:**
1. **Conversation**: Collect objective, inputs, outputs, guardrails
2. **Skill discovery**: Call `get_skillset(...)` to find available capabilities
3. **Draft workflow**: Create linear SOP with step names and candidate skills
4. **Compile to ASL**: Transform to state machine with `AgentBinding` per Task
5. **Validate**: `validate_workflow(...)` with import resolution
6. **Approval**: Confirm with user; persist workflow JSON to `workflows/generated/`

**Execution Phase:**
7. **Create control plane**: `create_workflow_control_plane(...)` seeds Redis
8. **Create workers**: `create_worker_agents(...)` instantiates ephemeral agents
9. **Trigger execution**: `notify_next_worker_agent(..., source_state=None)` kicks off initial states
10. **Monitor** (optional): `read_workflow_control_plane(..., compute_readiness=True)`
11. **Finalize**: `finalize_workflow(...)` closes states, deletes workers, writes audit record
12. **Collect results & persist audit trail**: Read all execution data and persist to `workflows/runs/<workflow_id>/`:
    - `workflow.json` — Workflow definition
    - `summary.json` — Human-readable execution summary
    - `control_plane/meta.json` — Workflow metadata
    - `control_plane/states/*.json` — Per-state status documents
    - `data_plane/outputs/*.json` — Worker outputs
    - `data_plane/audit/finalize.json` — Finalization record
13. **Present results**: Communicate final status, key outputs, and audit trail path to user
14. **Trigger reflection** (optional): `trigger_reflection(...)` for self-improvement analysis

#### Worker Flow (per state)

1. **Check readiness**: Verify upstream states are `done`
2. **Acquire lease**: `acquire_state_lease(...)` → get exclusive access
3. **Load skills**: `load_skill(...)` for this task's required capabilities
4. **Read inputs**: Get upstream outputs from data plane
5. **Execute**: Run tools following skill directives
6. **Write output**: `update_workflow_control_plane(..., output_json=...)`
7. **Unload skills**: Return to clean baseline
8. **Release lease**: `release_state_lease(...)`
9. **Notify downstream**: `notify_next_worker_agent(...)`

#### Leases

Soft leases (token + TTL) prevent race conditions when multiple workers are available:
- Use `renew_state_lease()` for long-running tasks
- Expired leases can be stolen by other workers
- Lease tokens are validated on state updates

### Phase 2: Delegated Execution Flow

#### Conductor Flow

1. **Session initialization**: Create session context via `create_session_context`
2. **Register Strategist** (optional): Call `register_strategist` to establish optimization relationship
3. **Spawn initial Companions**: Call `create_companion` with shared session context
4. **Continuous conversation**: Engage with user to understand evolving goals and requirements
5. **Task identification**: Identify discrete tasks from user requests
6. **Skill discovery**: Call `get_skillset(...)` to find available capabilities for each task
7. **Read Strategist guidelines**: Check `strategist_guidelines` block for optimization advice before delegation
8. **Delegate tasks**: Use `delegate_task` with `skills_required` to assign work to Companions
9. **Receive results**: Process task results reported by Companions via `send_message_to_agent_async`
10. **Trigger analysis**: Call `trigger_strategist_analysis` every 3-5 tasks for continuous optimization
11. **Synthesize and respond**: Combine Companion outputs into coherent user responses
12. **Companion management**: Scale pool (create/dismiss), adjust specializations based on workload
13. **Session finalization**: Call `finalize_session` to cleanup when user session ends

#### Companion Flow (per task)

1. **Receive delegation**: Receive task delegation message from Conductor
2. **Update status**: Set status to "busy" via tag update
3. **Load skills**: Call `load_skill(...)` for each skill in `skills_required` (trust Conductor's selection)
4. **Execute task**: Run tools following skill directives
5. **Report result**: Send structured result to Conductor via `send_message_to_agent_async`
6. **Unload skills**: Return to clean baseline via `unload_skill(...)`
7. **Update status**: Set status back to "idle"

#### Strategist Flow

1. **Receive trigger**: Receive `analysis_event` from `trigger_strategist_analysis` (called by Conductor)
2. **Read Conductor memory**: Access shared blocks via `read_shared_memory_blocks` (delegation_log, session_context)
3. **Read session activity**: Get detailed metrics via `read_session_activity`
4. **Query historical context**: Search Graphiti for similar patterns and past insights
5. **Analyze patterns**: Identify skill effectiveness, Companion performance, and delegation patterns
6. **Generate recommendations**: Formulate optimization advice (skill preferences, Companion specializations)
7. **Persist to Graphiti**: Write significant patterns via `add_episode` (SessionPattern, SkillMetric, Insight)
8. **Publish guidelines**: Write recommendations to `strategist_guidelines` block via `update_conductor_guidelines`

### Architecture Comparison

| Aspect | Phase 1 (Workflow) | Phase 2 (Delegated) |
|--------|-------------------|---------------------|
| Planning | Predetermined DAG upfront | Dynamic during conversation |
| Executors | Ephemeral Workers (per-workflow) | Session-scoped Companions |
| User Engagement | Paused during execution | Continuous |
| Coordination | Redis control plane + leases | Shared memory blocks + async messaging |
| Optimization | Post-workflow Reflector | Real-time Strategist |
| Skill Authority | Planner at workflow creation | Conductor at each delegation |
| Executor Autonomy | Workers follow workflow state | Companions follow Conductor instructions |

## Important Notes

### Stub MCP Sessions
The Streamable HTTP endpoint (`/mcp`) returns an `mcp-session` header; clients must echo it on follow-up calls to maintain stateful sessions.

### Template Resolution
`create_worker_agents` prefers `AgentBinding.agent_ref`. If a workflow only supplies `agent_template_ref`, templates may need to be embedded in `af_v2_entities` or bindings transformed before invoking.

### Generated Artifacts
After editing `skills_src/` YAML files, regenerate `generated/` and commit outputs so workflows remain reproducible.

### Workers are Ephemeral (Phase 1)
Created per workflow, optionally deleted after finalization via `finalize_workflow(..., delete_worker_agents=True)`.

### Companions are Session-Scoped (Phase 2)
Unlike ephemeral Workers, Companions persist across multiple tasks within a session. They are created at session start and dismissed at session end (or dynamically scaled by the Conductor).

### Skill Authority
In both phases, the orchestrating agent is the skill authority:
- **Phase 1**: Planner discovers and assigns skills at workflow creation time
- **Phase 2**: Conductor discovers and assigns skills at each delegation—Companions never discover skills themselves

### Tool Response Format
All tools return `{status, error, ...}` where `error` is `None` on success, enabling reliable chaining in agent conversations.

## Testing Environment

This section provides instructions for Claude Code to effectively test changes and observe outcomes in the local Docker environment.

### Service Architecture & Rebuild Guide

| Service | Container | Source Directory | Rebuild Trigger | Restart Command |
|---------|-----------|------------------|-----------------|-----------------|
| **Letta API** | `letta` | `Dockerfile.letta`, `entrypoint.sh`, `requirements.txt` | Changes to Letta config or custom Python deps | `docker compose up --build letta` |
| **DCF MCP** | `dcf-mcp` | `dcf_mcp/` | Tool implementation changes in `dcf_mcp/tools/` | `docker compose up --build dcf-mcp` |
| **Stub MCP** | `stub-mcp` | `stub_mcp/` | Server logic changes (rare) | `docker compose up --build stub-mcp` |
| **Graphiti MCP** | `graphiti-mcp` | `graphiti/` | Changes to `graphiti/src/` | `docker compose up --build graphiti-mcp` |
| **Redis** | `redis` | N/A (official image) | N/A | `docker compose restart redis` |
| **FalkorDB** | `falkordb` | N/A (official image) | N/A | `docker compose restart falkordb` |

**Hot-Reload Behavior:**
- **Stub MCP** hot-reloads `generated/stub/stub_config.json` automatically (no restart needed for tool case changes)
- **DCF MCP** requires restart for Python code changes, but reads manifests from mounted volumes
- **Skill manifests** in `generated/manifests/` are mounted as volumes; regenerate and they're available immediately

### Development Loop Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. MAKE CHANGES                                                             │
│    ├── Skill YAML (skills_src/skills/*.yaml, skills_src/tools.yaml)         │
│    ├── Tool code (dcf_mcp/tools/**/*.py)                                    │
│    └── Agent templates (dcf_mcp/agents/*.af)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. REGENERATE (if YAML changed)                                             │
│    docker exec dcf-mcp python -c \                                          │
│      'from tools.dcf.yaml_to_manifests import yaml_to_manifests; \          │
│       from tools.dcf.yaml_to_stub_config import yaml_to_stub_config; \      │
│       yaml_to_manifests(); yaml_to_stub_config()'                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. REBUILD (if Python code changed)                                         │
│    docker compose up --build dcf-mcp -d                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. TEST via API calls (see below)                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. OBSERVE via logs, Redis, or API responses                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### API Reference for Testing

#### Health Checks

```bash
# All services healthy?
curl -sf http://localhost:8283/v1/health/  && echo "Letta OK"
curl -sf http://localhost:8765/healthz     && echo "Stub MCP OK"
curl -sf http://localhost:8337/health      && echo "DCF MCP OK"  # If implemented
curl -sf http://localhost:8000/health      && echo "Graphiti OK" # If implemented
```

#### Letta API (Port 8283)

**List all agents:**
```bash
curl -s http://localhost:8283/v1/agents/ | jq '.[] | {id, name, agent_type}'
```

**Get specific agent:**
```bash
curl -s http://localhost:8283/v1/agents/{agent_id} | jq '.'
```

**List agent's tools:**
```bash
curl -s http://localhost:8283/v1/agents/{agent_id}/tools | jq '.[].name'
```

**List agent's memory blocks:**
```bash
curl -s http://localhost:8283/v1/agents/{agent_id}/core-memory/blocks | jq '.[] | {id, label, value}'
```

**Send message to agent (synchronous):**
```bash
curl -s -X POST http://localhost:8283/v1/agents/{agent_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}' | jq '.'
```

**Delete agent:**
```bash
curl -s -X DELETE http://localhost:8283/v1/agents/{agent_id}
```

**List all memory blocks:**
```bash
curl -s http://localhost:8283/v1/blocks/ | jq '.[] | {id, label}'
```

#### Stub MCP Server (Port 8765)

**View metrics (tool call counts, case hits):**
```bash
curl -s http://localhost:8765/metrics | jq '.'
```

**Reset metrics (before a test run):**
```bash
curl -s -X POST http://localhost:8765/metrics/reset
```

**Test MCP tool call directly (requires session management):**
```bash
# Initialize session
curl -s -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test"}}}' \
  -D - | grep -i mcp-session

# Call tool (use session header from above)
curl -s -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -H "mcp-session: {session_id}" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tool_name","arguments":{...}}}'
```

#### Redis (Port 6379) - Control Plane Inspection

**List all workflow control plane keys:**
```bash
docker exec redis redis-cli KEYS "cp:wf:*"
```

**Read workflow meta document:**
```bash
docker exec redis redis-cli JSON.GET "cp:wf:{workflow_id}:meta" $ | jq '.'
```

**Read state document:**
```bash
docker exec redis redis-cli JSON.GET "cp:wf:{workflow_id}:state:{state_name}" $ | jq '.'
```

**Read data plane output:**
```bash
docker exec redis redis-cli JSON.GET "dp:wf:{workflow_id}:output:{state_name}" $ | jq '.'
```

**Clear all workflow data (CAUTION):**
```bash
docker exec redis redis-cli KEYS "cp:wf:*" | xargs -r docker exec -i redis redis-cli DEL
docker exec redis redis-cli KEYS "dp:wf:*" | xargs -r docker exec -i redis redis-cli DEL
```

**List session-related keys (Phase 2):**
```bash
docker exec redis redis-cli KEYS "session:*"
```

#### FalkorDB (Port 8379) - Knowledge Graph Inspection

**Run Cypher query:**
```bash
docker exec falkordb redis-cli -a demodemo GRAPH.QUERY lettaplus "MATCH (n) RETURN labels(n), count(*)"
```

**List all node types:**
```bash
docker exec falkordb redis-cli -a demodemo GRAPH.QUERY lettaplus "MATCH (n) RETURN DISTINCT labels(n)"
```

**Find specific entity:**
```bash
docker exec falkordb redis-cli -a demodemo GRAPH.QUERY lettaplus "MATCH (n) WHERE n.name CONTAINS 'keyword' RETURN n"
```

**Clear graph (CAUTION - destroys all knowledge):**
```bash
docker exec falkordb redis-cli -a demodemo GRAPH.DELETE lettaplus
```

### Log Observation

**Follow all service logs:**
```bash
docker compose logs -f
```

**Follow specific service:**
```bash
docker compose logs -f dcf-mcp      # DCF tool execution
docker compose logs -f letta        # Agent conversations, tool calls
docker compose logs -f stub-mcp     # Stubbed tool responses
docker compose logs -f graphiti-mcp # Knowledge graph operations
```

**Filter logs by pattern:**
```bash
docker compose logs -f dcf-mcp 2>&1 | grep -E "(acquire_state_lease|release_state_lease)"
docker compose logs -f letta 2>&1 | grep -E "(tool_call|function_call)"
```

### Testing Scenarios

#### Quick Validation After Code Changes

1. **Verify DCF MCP tools are registered:**
   ```bash
   # This should list all available tools
   curl -s -X POST http://localhost:8337/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test"}}}'
   ```

2. **Test skill catalog generation:**
   ```bash
   docker exec dcf-mcp python -c "from tools.dcf.get_skillset_from_catalog import get_skillset_from_catalog; import json; print(json.dumps(get_skillset_from_catalog(), indent=2))"
   ```

3. **Validate a workflow:**
   ```bash
   docker exec dcf-mcp python -c "
   from tools.dcf.validate_workflow import validate_workflow
   import json
   wf = open('/app/workflows/examples/example_workflow.json').read()
   print(json.dumps(validate_workflow(wf), indent=2))
   "
   ```

#### Phase 1 Workflow Testing

1. **Pre-test cleanup:**
   ```bash
   # Clear any existing workflow state
   docker exec redis redis-cli KEYS "cp:wf:*" | xargs -r docker exec -i redis redis-cli DEL
   docker exec redis redis-cli KEYS "dp:wf:*" | xargs -r docker exec -i redis redis-cli DEL
   # Reset stub metrics
   curl -s -X POST http://localhost:8765/metrics/reset
   ```

2. **Monitor during execution:**
   ```bash
   # Terminal 1: Watch control plane changes
   watch -n 1 'docker exec redis redis-cli KEYS "cp:wf:*"'

   # Terminal 2: Watch logs
   docker compose logs -f dcf-mcp letta
   ```

3. **Post-test inspection:**
   ```bash
   # Check stub metrics to verify tool calls
   curl -s http://localhost:8765/metrics | jq '.metrics.case_hits'

   # Examine workflow final state
   docker exec redis redis-cli JSON.GET "cp:wf:{workflow_id}:meta" $.workflow_status
   ```

#### Phase 2 Session Testing

1. **List Companions for a session:**
   ```bash
   # After creating companions, verify they exist
   curl -s http://localhost:8283/v1/agents/ | jq '.[] | select(.tags[]? | contains("session:")) | {id, name, tags}'
   ```

2. **Check session context block:**
   ```bash
   curl -s http://localhost:8283/v1/blocks/ | jq '.[] | select(.label == "session_context")'
   ```

### Troubleshooting Common Issues

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|--------------|------------|-----|
| Tool returns `{"error": "..."}` | Tool implementation bug | Check `docker compose logs dcf-mcp` | Fix Python code, rebuild |
| Agent not found | Agent ID changed or deleted | `curl http://localhost:8283/v1/agents/` | Recreate agent or use correct ID |
| Stub returns wrong response | Case matching failed | Check `stub_config.json` match rules | Update YAML, regenerate |
| Redis connection refused | Redis not running | `docker compose ps redis` | `docker compose up redis -d` |
| Workflow stuck in "running" | Worker crashed or lease expired | Check state documents in Redis | Finalize workflow manually |
| Graphiti operations fail | FalkorDB connection issue | Check graphiti-mcp logs | Restart graphiti-mcp |

### Environment Variables

Key environment variables (set via `.env` or `docker-compose.yml`):

| Variable | Service | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | letta, graphiti-mcp | LLM API access |
| `DCF_MANIFESTS_DIR` | dcf-mcp | Skill manifest location |
| `DCF_SKILLS_CATALOG` | dcf-mcp | Pre-computed catalog path |
| `STUB_CONFIG` | stub-mcp | Stub configuration file |
| `FALKORDB_PASSWORD` | falkordb, graphiti-mcp | Graph database auth |

## Coding Style

- Python: 4-space indentation, type hints where practical
- Graphiti: `ruff format` and `ruff check` (line length 100, single quotes)
- Generated manifests: `skill.<domain>.<name>-<semver>.json` under `generated/manifests/`

## Security Notes

- Do not commit secrets; use `.env` or environment variables (`OPENAI_API_KEY`, etc.)
- Skill manifests declare permissions (`egress`, `secrets`, `riskLevel`) for governance
- PII filtering before vectorization or diary writes in production

## Related Documentation

### Architecture & Design
- `docs/Architectural_Evolution_Opus.md` — **Evolution from Workflow to Delegated Execution patterns**
- `docs/Overall_Combined.md` — Comprehensive architecture overview
- `docs/Self-Evolving-Agent-Whitepaper.md` — Detailed design rationale
- `docs/DCF-Patent-Proposal.md` — Dynamic Capabilities Framework concept
- `docs/Hybrid-Memory-Patent-Proposal.md` — Memory system design

### Tool Documentation
- `dcf_mcp/tools/TOOLS.md` — Phase 1 (dcf) tools: Planner, Worker, Reflector
- `dcf_mcp/tools/dcf+/TOOLS.md` — **Phase 2 (dcf+) tools: Conductor, Companion, Strategist**

### Agent Prompts
- `prompts/dcf/` — Phase 1 agent prompts (Planner, Worker, Reflector)
- `prompts/dcf+/` — Phase 2 agent prompts (Conductor, Companion, Strategist)

### Testing
- `docs/TESTING_PLAN_*.md` — End-to-end testing guides
- **Testing Environment** section above — API calls, log observation, troubleshooting for local development
