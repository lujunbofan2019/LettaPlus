# Repository Guidelines

## Project Summary (What this repo is)

- **Goal**: plan, validate, and execute multi-step workflows defined as **ASL-style state machines** with **Letta-specific bindings**.
- **Execution model**: **choreography-first**. There is no central orchestrator loop; **ephemeral worker agents** self-coordinate using a **RedisJSON control plane** (readiness, leases, status, outputs).
- **Skills**: capabilities are packaged as **skill manifests** (schema’d JSON) that can be **loaded/unloaded dynamically** per worker/state.
- **Testing**: a deterministic **stub MCP server** serves canned tool responses (generated from CSV) for BDD-style regression tests without live backends.
- **Optional memory layer**: `graphiti/` provides a Graphiti MCP server backed by FalkorDB (via Docker Compose) for knowledge-graph style memory.
- **Example workflow**: `workflows/example/market_research_workflow.json` wires generated skills from `generated/manifests/` into a multi-stage research → synthesis → writing pipeline.

## Key Concepts (mental model)

- **Workflow**: JSON validated against `dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json`. Task states bind an agent template + a list of skills (URIs like `skill://<skillName>@<skillVersion>`).
- **Planner vs workers**:
  - Planner: user-facing; turns intent into a workflow; does not micromanage.
  - Workers: run Task states; acquire a lease, load skills, do work, write output, release lease, notify downstream.
- **Control plane keys (RedisJSON + data-plane outputs)**:
  - Meta: `cp:wf:{workflow_id}:meta`
  - Per-state: `cp:wf:{workflow_id}:state:{state_name}`
  - Outputs: `dp:wf:{workflow_id}:output:{state_name}` (JSON blob written by `update_workflow_control_plane`)
  - Finalize audit: `dp:wf:{workflow_id}:audit:finalize`

## Local Stack (Docker Compose)

- Bring everything up: `docker compose up --build`
- Services/ports (defaults from `docker-compose.yml`):
  - Letta API: `http://localhost:8283`
  - DCF MCP (Streamable HTTP): `http://localhost:8337/mcp`
  - Stub MCP (Streamable HTTP): `http://localhost:8765/mcp`
  - Graphiti MCP (Streamable HTTP): `http://localhost:8000/mcp/`
  - Redis Stack: `localhost:6379`
  - FalkorDB (Redis protocol): `localhost:8379`

## Project Structure & Module Organization

- `dcf_mcp/`: MCP server exposing workflow/skill utilities (schemas, RedisJSON control plane, file-system helpers).
- `dcf_mcp/tools/dcf/`: core workflow/skill operations (validate, generate, leases, notify, outputs, finalize).
- `dcf_mcp/agents/`: Letta `.af` templates (planner/worker) referenced by workflows.
- `stub_mcp/`: deterministic MCP stub server; reads `generated/stub/stub_config.json`.
- `graphiti/`: Graphiti MCP server (Python project with `ruff`, `pyright`, `pytest`).
- `skills_src/`: CSV authoring inputs (`skills.csv`, `skill_tool_refs.csv`, `mcp_tools.csv`, `mcp_cases.csv`).
- `generated/`: generated artifacts (`generated/manifests/`, `generated/catalogs/`, `generated/stub/`).
- `workflows/`: example workflow JSON (ASL + Letta bindings), e.g. `workflows/example/`.
- `prompts/`, `docs/`: agent prompts and design/testing notes.

## Build, Test, and Development Commands

- `docker compose up --build`: start local stack (Letta + Redis/RedisStack + DCF MCP + stub MCP + Graphiti + FalkorDB as configured in `docker-compose.yml`).
- `docker compose logs -f dcf-mcp` (or `stub-mcp`, `graphiti-mcp`, `letta`): follow service logs.
- `docker compose down`: stop services (keeps volumes by default).
- Regenerate generated artifacts from CSV (local, no Docker required):
  - `python -c 'import json; from dcf_mcp.tools.dcf.csv_to_manifests import csv_to_manifests; print(json.dumps(csv_to_manifests(skills_csv_path="skills_src/skills.csv", refs_csv_path="skills_src/skill_tool_refs.csv", mcp_tools_csv_path="skills_src/mcp_tools.csv", out_dir="generated/manifests", catalog_path="generated/catalogs/skills_catalog.json"), indent=2))'`
  - `python -c 'import json; from dcf_mcp.tools.dcf.csv_to_stub_config import csv_to_stub_config; print(json.dumps(csv_to_stub_config(mcp_tools_csv_path="skills_src/mcp_tools.csv", mcp_cases_csv_path="skills_src/mcp_cases.csv", out_path="generated/stub/stub_config.json"), indent=2))'`
- Graphiti local dev:
  - `cd graphiti && uv sync --dev`
  - `cd graphiti && uv run main.py --config config/config-docker-falkordb.yaml`

## Coding Style & Naming Conventions

- Python: 4-space indentation, type hints where practical, avoid one-letter names outside tiny scopes.
- Graphiti formatting/linting:
  - `cd graphiti && ruff format`
  - `cd graphiti && ruff check`
  - Config: line length 100, single quotes (see `graphiti/pyproject.toml`).
- Generated manifests: prefer `skill.<domain>.<name>-<semver>.json` under `generated/manifests/`.

## Testing Guidelines

- Graphiti tests: `cd graphiti && pytest` (prefer `test_*.py` naming; keep tests close to the code they cover).
- Smoke checks (optional):
  - stub MCP health: `curl -sf http://localhost:8765/healthz`
  - Letta health: `curl -sf http://localhost:8283/v1/health/`

## Notes / Gotchas

- **Stub MCP sessions**: the Streamable HTTP MCP endpoint (`/mcp`) returns an `mcp-session` header; clients should echo it on follow-up calls (see `stub_mcp/README.md`).
- **`create_worker_agents` template resolution**: currently prefers `AgentBinding.agent_ref` in some flows; if a workflow only supplies `agent_template_ref`, you may need to embed templates under `af_v2_entities` or transform bindings before invoking (see `README.md`).
- **When editing `skills_src/`**: regenerate and commit the corresponding `generated/` outputs so workflows remain reproducible.

## Commit & Pull Request Guidelines

- Commit messages in this repo are short and imperative (no strict Conventional Commits); use a component prefix when helpful (e.g., `dcf_mcp: …`, `stub_mcp: …`).
- PRs: include a clear summary, how you tested (`docker compose …`, `pytest`, etc.), and screenshots/log snippets for behavior changes.
- If you change `skills_src/`, regenerate and commit the corresponding outputs in `generated/` so workflows remain reproducible.

## Security & Configuration Tips

- Do not commit secrets: `.env` is ignored; use local `.env` or environment variables (`OPENAI_API_KEY`, etc.) when running Compose.
