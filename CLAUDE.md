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
| `skills_src/` | CSV authoring inputs for skills and tools |
| `generated/` | Generated artifacts: manifests, catalogs, stub config |
| `workflows/` | Example workflow JSON files |
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
- `csv_to_manifests` — Generate skill manifests from CSV sources
- `csv_to_stub_config` — Generate stub MCP server configuration

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

### Regenerate artifacts from CSV sources

```bash
# Generate skill manifests + catalog
python -c 'from dcf_mcp.tools.dcf.csv_to_manifests import csv_to_manifests; csv_to_manifests()'

# Generate stub MCP config
python -c 'from dcf_mcp.tools.dcf.csv_to_stub_config import csv_to_stub_config; csv_to_stub_config()'
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

## CSV-First Skill Pipeline

Skills and tools are authored via CSV for rapid prototyping:

1. **`skills_src/skills.csv`** — Master list of skills (name, version, description, tags, permissions)
2. **`skills_src/skill_tool_refs.csv`** — Maps skills to tools (many-to-many)
3. **`skills_src/mcp_tools.csv`** — Tool schemas (name, JSON schema, server ID)
4. **`skills_src/mcp_cases.csv`** — Deterministic stub test cases (input → output)
5. **`skills_src/registry.json`** — Resolver map from server ID → endpoint (stub vs real)

**Pipeline:**
1. Author CSVs
2. Run `csv_to_manifests()` → `generated/manifests/`
3. Run `csv_to_stub_config()` → `generated/stub/stub_config.json`
4. Stub MCP server hot-reloads config automatically
5. Switch to real backends by updating `registry.json`

## Workflow Execution Flow

### Planner Flow

1. **Conversation**: Collect objective, inputs, outputs, guardrails
2. **Skill discovery**: Call `get_skillset(...)` to find available capabilities
3. **Draft workflow**: Create linear SOP with step names and candidate skills
4. **Compile to ASL**: Transform to state machine with `AgentBinding` per Task
5. **Validate**: `validate_workflow(...)` with import resolution
6. **Approval**: Confirm with user; persist workflow JSON

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
After editing `skills_src/` CSVs, regenerate `generated/` and commit outputs so workflows remain reproducible.

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

- `docs/Overall_Combined.md` — Comprehensive architecture overview
- `docs/Self-Evolving-Agent-Whitepaper.md` — Detailed design rationale
- `docs/DCF-Patent-Proposal.md` — Dynamic Capabilities Framework concept
- `docs/Hybrid-Memory-Patent-Proposal.md` — Memory system design
- `docs/TESTING_PLAN_*.md` — End-to-end testing guides
- `prompts/*.md` — Agent system prompts
