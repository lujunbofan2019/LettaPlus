# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LettaPlus** is a self-evolving agentic AI architecture that enables autonomous agents to learn, adapt, and improve through experience. The system addresses two fundamental limitations of current agentic systems:

1. **Stateless, Amnesiac Design**: Most agent systems fragment knowledge across isolated conversation threads
2. **Static, Pre-defined Capabilities**: Agents cannot acquire new abilities at runtime

LettaPlus solves these by unifying three core innovations:

- **Dynamic Capabilities Framework (DCF)**: Shifts modularity from specialized agents to transferable, version-controlled "skills" that can be loaded/unloaded at runtime
- **Hybrid Memory System**: Combines a knowledge graph, hierarchical memory blocks, and vector stores for comprehensive context and structured reasoning
- **Workflow Execution Engine**: Uses AWS Step Functions (ASL) semantics to orchestrate complex tasks via ephemeral, choreography-driven worker agents

### Key Concepts

- **Planner Agent**: User-facing agent that converses to understand intent, discovers skills, compiles SOPs into ASL state machines, and orchestrates execution
- **Ephemeral Workers**: Short-lived Letta agents instantiated from `.af v2` templates; load skills, execute tasks, write outputs, then optionally get deleted
- **Skills**: Self-contained, version-controlled JSON manifests defining capabilities (directives, tools, data sources, permissions, tests)
- **Workflows**: JSON-defined Standard Operating Procedures (SOPs) using ASL semantics with Letta-specific `AgentBinding` extensions
- **Choreography**: Workers self-coordinate via a RedisJSON control plane using leases, status updates, and notifications—no central orchestrator loop

### Vision

The system treats every engagement as an opportunity to refine institutional knowledge. Agents package capabilities as reusable skills, stitch skills into formal workflows, and preserve results in a layered memory fabric. Over time, the system behaves like an adaptive operations team that can compose best practices, collaborate safely, and evolve in response to new requirements.

## Architecture

### Directory Structure

| Directory | Purpose |
|-----------|---------|
| `dcf_mcp/` | Core MCP server exposing 40+ workflow/skill tools |
| `dcf_mcp/tools/dcf/` | Workflow execution tools (validate, generate, leases, notify, finalize) |
| `dcf_mcp/tools/redis_json/` | RedisJSON operations for control plane |
| `dcf_mcp/tools/file_system/` | File operations |
| `dcf_mcp/agents/` | Letta agent templates (`.af` format) |
| `dcf_mcp/schemas/` | JSON schemas (workflow v2.2.0, skill v2.0.0, control/data plane) |
| `stub_mcp/` | Deterministic stub MCP server for BDD testing |
| `graphiti/` | Knowledge graph memory layer (FalkorDB backend) |
| `skills_src/` | YAML skill definitions and tool specifications |
| `generated/` | Generated artifacts: manifests, catalogs, stub config |
| `workflows/` | Example workflow JSON files |
| `workflows/generated/` | Persisted workflow definitions |
| `workflows/runs/` | Execution audit trails (per workflow_id) |
| `prompts/` | Agent system prompts (Planner/Worker variants) |
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

### Regenerate artifacts from YAML sources

```bash
# Generate all artifacts (manifests + stub config)
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'

# Or individual generators
python -c 'from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests; yaml_to_manifests()'
python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
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

Skills and tools are authored via YAML for clarity and maintainability:

1. **`skills_src/skills/*.skill.yaml`** — Individual skill definitions (one per file)
2. **`skills_src/tools.yaml`** — Tool specifications and test cases for simulation
3. **`skills_src/registry.yaml`** — Resolver map from server ID → endpoint (stub vs real)

**Pipeline:**
1. Author YAML skill files in `skills_src/skills/`
2. Define tools and test cases in `skills_src/tools.yaml`
3. Run `generate_all()` → generates manifests + stub config
4. Stub MCP server hot-reloads config automatically
5. Switch to real backends by updating `registry.yaml`

See `skills_src/SKILLS.md` for detailed authoring documentation.

## Workflow Execution Flow

### Planner Flow

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

### Worker Flow (per state)

1. **Check readiness**: Verify upstream states are `done`
2. **Acquire lease**: `acquire_state_lease(...)` → get exclusive access
3. **Load skills**: `load_skill(...)` for this task's required capabilities
4. **Read inputs**: Get upstream outputs from data plane
5. **Execute**: Run tools following skill directives
6. **Write output**: `update_workflow_control_plane(..., output_json=...)`
7. **Unload skills**: Return to clean baseline
8. **Release lease**: `release_state_lease(...)`
9. **Notify downstream**: `notify_next_worker_agent(...)`

### Leases

Soft leases (token + TTL) prevent race conditions when multiple workers are available:
- Use `renew_state_lease()` for long-running tasks
- Expired leases can be stolen by other workers
- Lease tokens are validated on state updates

## Important Notes

### Stub MCP Sessions
The Streamable HTTP endpoint (`/mcp`) returns an `mcp-session` header; clients must echo it on follow-up calls to maintain stateful sessions.

### Template Resolution
`create_worker_agents` prefers `AgentBinding.agent_ref`. If a workflow only supplies `agent_template_ref`, templates may need to be embedded in `af_v2_entities` or bindings transformed before invoking.

### Generated Artifacts
After editing `skills_src/` YAML files, regenerate `generated/` and commit outputs so workflows remain reproducible.

### Workers are Ephemeral
Created per workflow, optionally deleted after finalization via `finalize_workflow(..., delete_worker_agents=True)`.

### Tool Response Format
All tools return `{status, error, ...}` where `error` is `None` on success, enabling reliable chaining in agent conversations.

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
