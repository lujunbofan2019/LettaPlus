# Letta–ASL Workflows + Skills (DAG + Ephemeral Workers)

> **Goal**: Plan, validate, and execute multi-step workflows using AWS Step Functions–style (ASL) state machines and **ephemeral Letta agents** equipped with **dynamically loadable skills**. Execution is **choreography-first**: workers self-coordinate via a RedisJSON control-plane - no central orchestrator loop.

This project provides:

- **Schemas**
  - `dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json` — Workflow JSON schema (ASL + Letta bindings)
  - `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json` — Skill manifest JSON schema
  - `dcf_mcp/schemas/control-plane-meta-1.0.0.json` — *Documented shape* of control-plane meta (see “Control Plane & Data Plane”)
  - `dcf_mcp/schemas/control-plane-state-1.0.0.json` — *Documented shape* of per-state docs
  - `dcf_mcp/schemas/notification-payload-1.0.0.json`
  - `dcf_mcp/schemas/data-plane-output-1.0.0.json`
- **Planning tools**
  1) `dcf_mcp/tools/dcf/validate_workflow(workflow_json, schema_path, imports_base_dir=None, skills_base_dir=None)`
  2) `dcf_mcp/tools/dcf/validate_skill_manifest(skill_json, schema_path)`
  3) `dcf_mcp/tools/dcf/get_skillset(manifests_dir=None, schema_path=None, include_previews=True, preview_chars=None)`
  4) `dcf_mcp/tools/dcf/get_skillset_from_catalog(catalog_path=None, schema_path=None, include_previews=False, preview_chars=None)`
  5) `dcf_mcp/tools/dcf/load_skill(skill_manifest, agent_id)`
  6) `dcf_mcp/tools/dcf/unload_skill(manifest_id, agent_id)`
- **Execution tools**
  7) `dcf_mcp/tools/dcf/create_workflow_control_plane(workflow_json, redis_url=None, expiry_secs=None, agents_map_json=None)`
  8) `dcf_mcp/tools/dcf/create_worker_agents(workflow_json, imports_base_dir=None, agent_name_prefix=None, default_tags_json=None)`
  9) `dcf_mcp/tools/dcf/read_workflow_control_plane(workflow_id, redis_url=None, states_json=None, include_meta=True, compute_readiness=False)`
  10) `dcf_mcp/tools/dcf/update_workflow_control_plane(workflow_id, state, redis_url=None, new_status=None, lease_token=None, owner_agent_id=None, lease_ttl_s=None, attempts_increment=None, error_message=None, set_started_at=False, set_finished_at=False, output_json=None, output_ttl_secs=None)`
  11) `dcf_mcp/tools/dcf/acquire_state_lease(workflow_id, state, owner_agent_id, redis_url=None, lease_ttl_s=None, require_ready=True, require_owner_match=True, allow_steal_if_expired=True, set_running_on_acquire=True, attempts_increment=1, lease_token=None)`
  12) `dcf_mcp/tools/dcf/renew_state_lease(workflow_id, state, lease_token, owner_agent_id=None, redis_url=None, lease_ttl_s=None, reject_if_expired=True, touch_only=False)`
  13) `dcf_mcp/tools/dcf/release_state_lease(workflow_id, state, lease_token, owner_agent_id=None, redis_url=None, force=False, clear_owner=True)`
  14) `dcf_mcp/tools/dcf/notify_next_worker_agent(workflow_id, source_state=None, reason=None, payload_json=None, redis_url=None, include_only_ready=True, message_role="system", async_message=False, max_steps=None)`
  15) `dcf_mcp/tools/dcf/notify_if_ready(workflow_id, state, redis_url=None, reason=None, payload_json=None, require_ready=True, skip_if_status_in_json=None, message_role="system", async_message=False, max_steps=None)`
  16) `dcf_mcp/tools/dcf/finalize_workflow(workflow_id, redis_url=None, delete_worker_agents=True, preserve_planner=True, close_open_states=True, overall_status=None, finalize_note=None)`
- **Testing tools**
  17) `dcf_mcp/tools/dcf/csv_to_manifests(skills_csv_path="skills_src/skills.csv", refs_csv_path="skills_src/skill_tool_refs.csv", ...)`
  18) `dcf_mcp/tools/dcf/csv_to_stub_config(mcp_tools_csv_path="skills_src/mcp_tools.csv", mcp_cases_csv_path="skills_src/mcp_cases.csv", ...)`

Everything is designed for **composition**: workflows import `.af v2` bundles and skill manifests by file path (`file://` allowed) without inlining. Skills are loaded/unloaded dynamically per worker.

---

## Architectural Overview

### Key concepts
- **Planner agent**: converses with the user, gathers intent and constraints, proposes & iterates the plan, then compiles SOP steps into an **ASL** state machine inside the workflow JSON (validated against `dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json`). The Planner never micromanages workers—workers run autonomously.
- **Ephemeral workers**: short-lived Letta agents instantiated from a shared **.af v2 template**. Before each Task, the worker **loads skills** relevant to that Task and **unloads** them after.
- **Skills**: packaged capabilities described by `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json` (directives, required tools, required data sources, permissions). Reusable across workflows.
- **Choreography**: workers coordinate via messages and a **RedisJSON control-plane**. Each worker checks readiness (all upstream `done`), acquires a lease, runs, writes output, releases lease, and notifies downstream.
- **Knowledge graph** *(optional but recommended)*: the skill catalog (from `get_skillset`) can be ingested into a lightweight KG (tags → tools → capabilities → success metrics). The Planner queries it to select candidate skills and to justify the plan (traceability).

### Control Plane & Data Plane (RedisJSON)
We keep two logical spaces in Redis:

- **Control-plane meta** — `cp:wf:{workflow_id}:meta`
  Minimal JSON document with:
  ```jsonc
  {
    "workflow_id": "...",
    "workflow_name": "Web Research and Summary",
    "schema_version": "2.2.0",
    "created_at": "ISO-8601",
    "start_at": "Research",
    "terminal_states": ["Summarize"],
    "states": ["Research", "Summarize"],
    "agents": { "Research": "agent_id_...", "Summarize": "agent_id_..." },
    "skills": { "Research": ["skill://web.search@1.0.0"] },
    "deps": {
      "Research":   { "upstream": [],           "downstream": ["Summarize"] },
      "Summarize":  { "upstream": ["Research"], "downstream": [] }
    }
  }
  ```

- **Per-state doc** — `cp:wf:{workflow_id}:state:{state}`
  ```jsonc
  {
    "status": "pending", // -> running|done|failed (helpers treat "done" as the success sentinel)
    "attempts": 0,
    "lease": { "token": null, "owner_agent_id": null, "ts": null, "ttl_s": null },
    "started_at": null,
    "finished_at": null,
    "last_error": null
  }
  ```

- **Data-plane outputs** — `dp:wf:{workflow_id}:output:{state}`
  Arbitrary JSON written by the worker for downstream consumption.
  Example: `{ "urls": [...], "notes": "..." }`

> We **do not** delete control-plane/data-plane keys after execution (audit trail). `finalize_workflow` optionally deletes worker agents only.

### Why leases?
Multiple agents could race to run a state (retries, scaling). A soft **lease** (token + timestamp) in the state doc, updated atomically via Redis WATCH/MULTI, ensures only one active runner. If the runner dies, the lease **expires** and another agent can take over.

---

## Planner Flow (from intent to ASL)

**Planning Phase:**
1. **Conversation**: collect objective, inputs, outputs, guardrails, budget/time, egress policy.
2. **Skill discovery**: call `get_skillset(...)` (optionally with validation). Optionally enrich with a knowledge graph for better selection & justification.
3. **Draft Workflow**: a linear `steps[]` plan with step names, inputs/outputs, and candidate skills.
4. **Compile to ASL**: transmute workflow → `asl` (`StartAt`, `States`), attach `AgentBinding` per Task:
  - `agent_template_ref`: e.g., `"agent_template_worker@1.0.0"`
  - `skills`: e.g., `["skill://web.search@1.0.0", "skill://summarize@1.0.0"]`
5. **Validate**: `validate_workflow(workflow_json, schema_path, imports_base_dir, skills_base_dir)`.
6. **Approval**: confirm with user; persist workflow JSON to `workflows/generated/`.

**Execution Phase:**
7. **Create control plane**: `create_workflow_control_plane(...)` seeds Redis with meta and per-state docs.
8. **Create workers**: `create_worker_agents(...)` instantiates ephemeral agents from `.af v2` templates.
9. **Trigger execution**: `notify_next_worker_agent(..., source_state=None)` kicks off initial states.
10. **Monitor** (optional): `read_workflow_control_plane(..., compute_readiness=True)` to track progress.
11. **Finalize**: `finalize_workflow(...)` closes open states, deletes workers, writes audit record.
12. **Collect results & persist audit trail**: Read all execution data and persist to `workflows/runs/<workflow_id>/`:
    - `workflow.json` — Workflow definition
    - `summary.json` — Human-readable execution summary
    - `control_plane/meta.json` — Workflow metadata
    - `control_plane/states/*.json` — Per-state status documents
    - `data_plane/outputs/*.json` — Worker outputs per state
    - `data_plane/audit/finalize.json` — Finalization record
13. **Present results**: Communicate final status, key outputs, errors (if any), and audit trail path to user.
14. **Trigger reflection** (optional): `trigger_reflection(...)` sends execution summary to Reflector for analysis.

---

## Worker Behavior (choreography)

**At notification (from `notify_next_worker_agent` or `notify_if_ready`):**

1. **Check readiness** (optional quick check): `notify_if_ready` already ensures upstream `done` when used.
2. **Acquire lease**: `acquire_state_lease(wf_id, state, owner_agent_id)` → `lease.token`.
3. **Load skills**: for this Task’s `AgentBinding.skills`, call `load_skill(manifest_id, agent_id)`.
4. **Read inputs** (if needed): `read_workflow_control_plane(wf_id, upstream_state)` or read `dp:wf:{id}:output:{up}`.
5. **Do the work**: run tools; follow directives.
6. **Write output + status**: `update_workflow_control_plane(wf_id, state, new_status="done", output_json=...)` (helpers still treat `"done"` as the success sentinel; the tool will store the canonical form).
7. **Unload skills**: `unload_skill(manifest_id, agent_id)` (best-effort; agent may also be ephemeral).
8. **Release lease**: `release_state_lease(wf_id, state, lease_token)`.
9. **Notify downstream**: `notify_next_worker_agent(wf_id, source_state=state, reason="upstream_done")`.

**On long tasks**: periodically `renew_state_lease(...)` until done.

**On errors**: `update_workflow_control_plane(..., new_status="failed", error_message=...)`, release lease, (optionally) notify downstream or planner for compensating logic.

---

## Tool Catalog (purpose & typical usage)

> All tools are **single-function** for Letta compatibility. Return shape is `{status, error, ...}` where `error` is `None` on success.

### Planning
- **`validate_workflow`** — JSON Schema validation + import resolution + ASL graph checks.
- **`validate_skill_manifest`** — Schema validation + static checks (unique tools, permissions). Accepts raw JSON or a path/``file://`` URI, mirroring `load_skill` semantics.
- **`get_skillset`** — Scan skills directory; returns catalog with aliases and optional directive previews.
- **`load_skill` / `unload_skill`** — Attach/detach directives, tools, data sources to an agent; maintain state in a `dcf_active_skills` block on the agent.

### Execution
- **`create_workflow_control_plane`** — Seeds `meta`, builds `deps` from ASL, initializes per-state docs. Optionally accepts `agents_map_json` (state→agent id) if you pre-created workers.
- **`create_worker_agents`** — Instantiates worker agents from a .af v2 template; updates `meta.agents`.
- **`read_workflow_control_plane`** — Returns `meta`, per-state doc(s), and (optionally) outputs.
- **`update_workflow_control_plane`** — Atomically updates a state’s `status`, `errors`, `finished_at`, and writes data-plane output JSON (`dp:...:output:{state}`). Optionally requires `lease_token`.
- **`acquire_state_lease` / `renew_state_lease` / `release_state_lease`** — Lease lifecycle (WATCH/MULTI).
- **`notify_next_worker_agent`** — Fan-out to downstream states’ agents (system-role Letta messages).
- **`notify_if_ready`** — Notify a single state’s agent only when upstream are `done`.
- **`finalize_workflow`** — Compute final status, optionally cancel open states, **delete worker agents**, and write an audit record. **Does not** remove Redis keys.

---

## Working Example (end-to-end)

**Scenario**: “Research a topic and produce a concise summary.”

### 1) Skills
- Generate manifests from the CSV scaffolding (see “CSV-first rapid skill prototyping”): for this example, run `csv_to_manifests(out_dir="skills", catalog_path="generated/catalogs/skills_catalog.json")` so the files land where the workflow expects them.
- After generation, `skills/web.search.json` and `skills/summarize.json` describe the two example skills.
  Validate them against the bundled schema:
```python
validate_skill_manifest(
    "skills/web.search.json",
    "dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json",
)
validate_skill_manifest(
    open("skills/summarize.json").read(),
    "dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json",
)
```

### 2) Workflow (ASL + Letta bindings)
`workflows/v2.2.0/example/web_search_and_summary.workflow.json` (highlights):
```jsonc
{
  "workflow_schema_version": "2.2.0",
  "workflow_id": "71c76b4d-c004-4910-a789-466241d1170c",
  "workflow_name": "Web Research and Summary",
  "version": "1.0.0",
  "af_imports": [
    { "uri": "file://af/agent_templates.json", "version": "2" }
  ],
  "skill_imports": [
    { "uri": "file://skills/web.search.json" },
    { "uri": "file://skills/summarize.json" }
  ],
  "asl": {
    "StartAt": "Research",
    "States": {
      "Research": {
        "Type": "Task",
        "Comment": "Find high-quality sources",
        "Parameters": {"query.$": "$.topic"},
        "ResultPath": "$.research",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
          "skills": ["skill://web.search@1.0.0"]
        },
        "Next": "Summarize"
      },
      "Summarize": {
        "Type": "Task",
        "Comment": "Write a short synthesis",
        "Parameters": {"max_words": 200, "sources.$": "$.research.urls"},
        "ResultPath": "$.summary",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
          "skills": ["skill://summarize@1.0.0"]
        },
        "End": true
      }
    }
  }
}
```

> ℹ️ If you keep the generated manifests under `generated/manifests/`, update the `skill_imports[*].uri` values accordingly (for example, `file://generated/manifests/web.search.json`).

Validate:
```python
validate_workflow(
    open("workflows/v2.2.0/example/web_search_and_summary.workflow.json").read(),
    "dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json",
    imports_base_dir="./workflows/v2.2.0/example",
    skills_base_dir="./skills",
)
```

### 3) Create control-plane + workers
```python
# Seed control-plane from ASL
create_workflow_control_plane(
  workflow_json=open("workflows/v2.2.0/example/web_search_and_summary.workflow.json").read()
)

# Create workers from .af v2 template
create_worker_agents(
  workflow_json=open("workflows/v2.2.0/example/web_search_and_summary.workflow.json").read(),
  imports_base_dir="./workflows/v2.2.0/example"
)
```

> ⚠️ `create_worker_agents` currently resolves templates via `AgentBinding.agent_ref`. If your workflow only supplies `agent_template_ref`, embed the matching template under `af_v2_entities` or transform the binding before invoking the tool.

### 4) Kick off
```python
# Notify source states (no upstream) or call notify_if_ready for each start state:
notify_next_worker_agent(
  workflow_id="71c76b4d-c004-4910-a789-466241d1170c",
  reason="initial"
)
```

### 5) Worker loop (Research)
Inside the **Research** worker agent’s message handler (conceptual sequence):
```python
# 1) Ensure ready (if self-notified)
notify_if_ready("71c76b4d-c004-4910-a789-466241d1170c", "Research")

# 2) Acquire lease
lease = acquire_state_lease("71c76b4d-c004-4910-a789-466241d1170c", "Research", owner_agent_id=self.id)
token = lease["lease"]["token"]

# 3) Load skills
load_skill(manifest_id="...manifest-id-of-web.search...", agent_id=self.id)

# 4) Do work (call registered web_search tool, etc.) and produce output JSON
research_output = {"urls": ["https://example.com/a", "https://example.com/b"], "notes": "..."}

# 5) Update control-plane + data-plane
update_workflow_control_plane("71c76b4d-c004-4910-a789-466241d1170c", "Research",
                              new_status="done",
                              output_json=json.dumps(research_output),
                              lease_token=token)

# 6) Unload skill (best-effort) + release lease
unload_skill(manifest_id="...manifest-id-of-web.search...", agent_id=self.id)
release_state_lease("71c76b4d-c004-4910-a789-466241d1170c", "Research", token)

# 7) Notify downstream (Summarize)
notify_next_worker_agent("71c76b4d-c004-4910-a789-466241d1170c", source_state="Research", reason="upstream_done")
```

### 6) Worker loop (Summarize)
```python
# 1) Wait for notify, then (optionally) ensure ready
notify_if_ready("71c76b4d-c004-4910-a789-466241d1170c", "Summarize")

# 2) Acquire lease
lease = acquire_state_lease("71c76b4d-c004-4910-a789-466241d1170c", "Summarize", owner_agent_id=self.id)
token = lease["lease"]["token"]

# 3) Load skill
load_skill(manifest_id="...manifest-id-of-summarize...", agent_id=self.id)

# 4) Read upstream output
cp = read_workflow_control_plane("71c76b4d-c004-4910-a789-466241d1170c", states_json='["Research"]')
sources = cp.get("outputs", {}).get("Research", {}).get("urls", [])

# 5) Summarize and produce output
summary = {"text": "Here’s a 200-word synthesis...", "sources": sources}

# 6) Update + release
update_workflow_control_plane("71c76b4d-c004-4910-a789-466241d1170c", "Summarize",
                              new_status="done",
                              output_json=json.dumps(summary),
                              lease_token=token)
unload_skill(manifest_id="...manifest-id-of-summarize...", agent_id=self.id)
release_state_lease("71c76b4d-c004-4910-a789-466241d1170c", "Summarize", token)

# 7) Since this is terminal, the Planner can call finalize_workflow
```

### 7) Finalize
```python
finalize_workflow("71c76b4d-c004-4910-a789-466241d1170c",
                  delete_worker_agents=True,
                  preserve_planner=True,
                  close_open_states=True,
                  finalize_note="Completed successfully.")
```
This writes an audit record at `dp:wf:{id}:audit:finalize` and computes an overall status.

### 8) Collect Results & Persist Audit Trail
```python
# Read complete execution state
cp = read_workflow_control_plane("71c76b4d-c004-4910-a789-466241d1170c", include_meta=True)

# Create audit trail directory structure
create_directory("/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c")
create_directory("/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/control_plane")
create_directory("/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/control_plane/states")
create_directory("/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/data_plane")
create_directory("/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/data_plane/outputs")
create_directory("/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/data_plane/audit")

# Persist all execution artifacts
write_file("/app/workflows/runs/71c76b4d-.../control_plane/meta.json", json.dumps(cp["meta"]))
write_file("/app/workflows/runs/71c76b4d-.../control_plane/states/Research.json", json.dumps(cp["states"]["Research"]))
write_file("/app/workflows/runs/71c76b4d-.../control_plane/states/Summarize.json", json.dumps(cp["states"]["Summarize"]))
write_file("/app/workflows/runs/71c76b4d-.../data_plane/outputs/Research.json", json.dumps(cp["outputs"]["Research"]))
write_file("/app/workflows/runs/71c76b4d-.../data_plane/outputs/Summarize.json", json.dumps(cp["outputs"]["Summarize"]))

# Generate and persist summary.json
summary = {
    "workflow_id": "71c76b4d-c004-4910-a789-466241d1170c",
    "workflow_name": "Web Research and Summary",
    "final_status": "succeeded",
    "execution_summary": {"total_states": 2, "succeeded": 2, "failed": 0},
    "terminal_outputs": [{"state": "Summarize", "output": cp["outputs"]["Summarize"]}],
    "audit_trail_path": "/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/"
}
write_file("/app/workflows/runs/71c76b4d-.../summary.json", json.dumps(summary))

# Present results to user
print(f"Execution Complete: {summary['final_status']}")
print(f"Result: {summary['terminal_outputs'][0]['output']}")
print(f"Audit Trail: {summary['audit_trail_path']}")
```

The audit trail directory structure:
```
/app/workflows/runs/71c76b4d-c004-4910-a789-466241d1170c/
├── workflow.json                      # Workflow definition
├── summary.json                       # Human-readable execution summary
├── control_plane/
│   ├── meta.json                      # cp:wf:{id}:meta
│   └── states/
│       ├── Research.json              # cp:wf:{id}:state:Research
│       └── Summarize.json             # cp:wf:{id}:state:Summarize
└── data_plane/
    ├── outputs/
    │   ├── Research.json              # dp:wf:{id}:output:Research
    │   └── Summarize.json             # dp:wf:{id}:output:Summarize
    └── audit/
        └── finalize.json              # dp:wf:{id}:audit:finalize
```

---

## YAML-Based Skill Authoring & Stub MCP Server

**YAML-first skill development** (Updated Feb-2026)
- Author skills and tools in human-readable YAML files
- Generate validated JSON manifests and stub server configuration
- Stand up a stub MCP server for deterministic BDD-style testing

### Source Files (YAML - Human-Editable)

| File | Purpose |
|------|---------|
| `skills_src/skills/*.skill.yaml` | Individual skill definitions (one per file) |
| `skills_src/tools.yaml` | Tool specifications and BDD test cases |
| `skills_src/registry.yaml` | MCP server resolver map (server ID → endpoint) |

### Generated Files (JSON - Machine-Readable)

| File | Generated From | Purpose |
|------|----------------|---------|
| `generated/manifests/skill.*.json` | `skills_src/skills/*.yaml` | Skill manifests for `load_skill` |
| `generated/catalogs/skills_catalog.json` | All skill manifests | Fast skill discovery index |
| `generated/stub/stub_config.json` | `skills_src/tools.yaml` | Stub MCP server configuration |
| `generated/registry.json` | `skills_src/registry.yaml` | MCP server endpoint resolution |

### Skill File Structure (*.skill.yaml)

Each skill is defined in its own YAML file:

```yaml
# skills_src/skills/research.web.skill.yaml
apiVersion: skill/v1
kind: Skill

metadata:
  manifestId: skill.research.web@0.1.0
  name: research.web
  version: 0.1.0
  description: Lightweight web research capability
  tags: [research, web]

spec:
  permissions:
    egress: internet
    secrets: [BING_API_KEY]

  # AMSP v3.0 Complexity Profile (for model selection)
  complexityProfile:
    baseWCS: 8
    dimensionScores:
      horizon: 1       # Multi-turn: may need multiple searches
      context: 1       # Local: search query context
      tooling: 2       # Multi-tool: search + fetch
      observability: 2 # Partial: web results are unpredictable
      modality: 0      # Text-only
      precision: 1     # Moderate: facts should be accurate
      adaptability: 1  # Slow-changing: web content evolves
    finalFCS: 9.2
    recommendedTier: 0  # Efficient tier (FCS < 12)

  directives: |
    Follow queries precisely.
    Extract key facts from search results.
    Provide citations with source URLs.

  tools:
    - ref: search:search_query
      required: true
      description: Core search tool for web queries
```

### Tools Configuration (tools.yaml)

All tool definitions and test cases in one file:

```yaml
# skills_src/tools.yaml
apiVersion: tools/v1
kind: ToolsConfig

tools:
  - serverId: search
    name: search_query
    description: Search the web for information
    inputSchema:
      type: object
      properties:
        query: { type: string, description: "Search query" }
        max_results: { type: integer, default: 10 }
      required: [query]
    cases:
      - caseId: case_market_scan
        match:
          query: "AI market trends 2026"
        output:
          results:
            - title: "AI Market Analysis"
              url: "https://example.com/ai-trends"
              snippet: "Key trends in AI adoption..."
```

### Registry Configuration (registry.yaml)

Maps logical server IDs to endpoints:

```yaml
# skills_src/registry.yaml
apiVersion: registry/v1
kind: ServerRegistry

servers:
  search:
    transport: streamable_http
    endpoint: http://stub-mcp:8765/mcp  # Stub for testing
  llm:
    transport: streamable_http
    endpoint: http://stub-mcp:8765/mcp

# Switch endpoints for production:
# servers:
#   search:
#     transport: streamable_http
#     endpoint: http://real-search-api:8080/mcp
```

### Generation Pipeline

Run generators to produce JSON artifacts:

```bash
# Generate all artifacts (manifests + stub config + registry)
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'

# Or individual generators
python -c 'from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests; yaml_to_manifests()'
python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
python -c 'from dcf_mcp.tools.dcf.yaml_to_registry import yaml_to_registry; yaml_to_registry()'
```

### Mental Model

- `skills_src/skills/*.skill.yaml` = "What skills exist and what do they do?"
- `skills_src/tools.yaml` = "What tools exist and how do they behave in tests?"
- `skills_src/registry.yaml` = "Where do those tools live (stub or real)?"
- `generated/manifests/` = "Machine-readable skill definitions for agents"
- `generated/stub/stub_config.json` = "Stub server behavior configuration"

### How to Run with the Stub Server

1. **Generate artifacts**:
   ```bash
   python -c 'from dcf_mcp.tools.dcf.generate import generate_all; generate_all()'
   ```

2. **Start services** (via Docker Compose):
   ```bash
   docker compose up --build
   ```

3. **Verify stub server**:
   ```bash
   curl -sf http://localhost:8765/healthz && echo "Stub MCP OK"
   ```

4. **Execute workflow**: The skill loader reads manifests from `generated/manifests/` and resolves endpoints via `generated/registry.json`. During tests, tools hit the stub server for deterministic responses.

### Two-Layer Architecture

The skill system operates as a **two-layer architecture**:

```
AUTHORING LAYER (Human-Editable YAML)
         │
    [ GENERATORS ]
         │
         ▼
RUNTIME LAYER (Machine-Readable JSON)
```

**Key insight**: You can freely modify the YAML authoring layer (file structure, format, organization) as long as the generators produce the same JSON output format. The runtime layer (JSON manifests) is consumed by agents and must remain stable.

For details on which fields are safe to modify vs. protected, see `skills_src/SKILL_RUNTIME_DEPENDENCIES.md`.

---

How to: fix Windows Hyper-V ports reservation

1. Stop and exit Docker Desktop
2. Stop WinNAT service `net stop winnat`
3. Set the new dynamic port range `netsh int ipv4 set dynamicport tcp start=49152 num=16384`
4. Restart WinNAT `net start winnat`
5. Confirm the change was effective `netsh int ipv4 show dynamicport tcp`
6. Reboot machine if needed.
