# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LettaPlus is a workflow orchestration system combining AWS Step Functions-style ASL (Amazon State Language) state machines with ephemeral Letta agents. Execution is choreography-first: workers self-coordinate via a RedisJSON control plane with no central orchestrator loop.

Key concepts:
- **Planner agent**: Converses with user, compiles intent into ASL state machines
- **Ephemeral workers**: Short-lived agents that load/unload skills dynamically per task
- **Skills**: Reusable capabilities (directives + tools) described by JSON manifests
- **Choreography**: Workers coordinate via Redis leases, status updates, and notifications

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
# From Python or via MCP tool calls:
csv_to_manifests(skills_csv_path="skills_src/skills.csv", ...)
csv_to_stub_config(mcp_tools_csv_path="skills_src/mcp_tools.csv", ...)
```

### Graphiti subproject (knowledge graph)
```bash
cd graphiti && uv sync --dev       # Install dependencies
cd graphiti && ruff format         # Format code
cd graphiti && ruff check          # Lint
cd graphiti && pytest              # Run tests
```

## Architecture

### Directory Structure
| Directory | Purpose |
|-----------|---------|
| `dcf_mcp/` | Core MCP server with 40+ workflow/skill tools |
| `dcf_mcp/tools/dcf/` | Workflow execution tools (19 files) |
| `dcf_mcp/tools/redis_json/` | RedisJSON operations (10 files) |
| `dcf_mcp/tools/file_system/` | File operations (6 files) |
| `dcf_mcp/agents/` | Letta agent templates (.af format) |
| `dcf_mcp/schemas/` | JSON schemas (workflow v2.2.0, skill v2.0.0, control/data plane) |
| `stub_mcp/` | Deterministic stub MCP server for BDD testing |
| `graphiti/` | Knowledge graph memory layer (FalkorDB backend) |
| `skills_src/` | CSV authoring inputs for skills and tools |
| `generated/` | Generated artifacts: manifests, catalogs, stub config |
| `workflows/` | Example workflow JSON files |
| `prompts/` | Agent system prompts |

### Tool Categories
1. **Planning**: `validate_workflow`, `validate_skill_manifest`, `get_skillset`, `load_skill`, `unload_skill`
2. **Control Plane**: `create_workflow_control_plane`, `create_worker_agents`, `read_workflow_control_plane`, `update_workflow_control_plane`
3. **Lease Management**: `acquire_state_lease`, `renew_state_lease`, `release_state_lease`
4. **Notifications**: `notify_next_worker_agent`, `notify_if_ready`
5. **Finalization**: `finalize_workflow`

### Redis Key Structure
- `cp:wf:{workflow_id}:meta` — Workflow metadata (states, agents, deps, skills)
- `cp:wf:{workflow_id}:state:{state_name}` — Per-state status, lease, timestamps
- `dp:wf:{workflow_id}:output:{state_name}` — Data-plane outputs from workers

### CSV-First Skill Pipeline
1. Author skills in `skills_src/skills.csv`
2. Map tools to skills in `skills_src/skill_tool_refs.csv`
3. Define tool schemas in `skills_src/mcp_tools.csv`
4. Add test cases in `skills_src/mcp_cases.csv`
5. Set endpoints in `skills_src/registry.json`
6. Generate with `csv_to_manifests()` → `generated/manifests/` and `csv_to_stub_config()` → `generated/stub/`

## Service Ports (Docker Compose)
| Service | Port | Purpose |
|---------|------|---------|
| Letta API | 8283 | Agent framework |
| DCF MCP | 8337 | Workflow tools |
| Stub MCP | 8765 | Deterministic testing |
| Graphiti MCP | 8000 | Knowledge graph |
| Redis Stack | 6379 | Control plane |
| FalkorDB | 8379 | Knowledge graph storage |

## Important Notes

- **Stub MCP sessions**: Streamable HTTP endpoint returns `mcp-session` header; clients must echo it on follow-up calls
- **Template resolution**: `create_worker_agents` prefers `AgentBinding.agent_ref`; if only `agent_template_ref` is supplied, templates may need to be embedded in `af_v2_entities`
- **Generated artifacts**: After editing `skills_src/` CSVs, regenerate `generated/` and commit outputs
- **Leases**: Soft leases expire and can be stolen; use `renew_state_lease()` for long tasks
- **Workers are ephemeral**: Created per workflow, optionally deleted after finalization
