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
    "workflow_id": "…",
    "workflow_name": "Web Research and Summary",
    "schema_version": "2.2.0",
    "created_at": "ISO-8601",
    "start_at": "Research",
    "terminal_states": ["Summarize"],
    "states": ["Research", "Summarize"],
    "agents": { "Research": "agent_id_…", "Summarize": "agent_id_…" },
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

1. **Conversation**: collect objective, inputs, outputs, guardrails, budget/time, egress policy.
2. **Skill discovery**: call `get_skillset(...)` (optionally with validation). Optionally enrich with a knowledge graph for better selection & justification.
3. **Draft Workflow**: a linear `steps[]` plan with step names, inputs/outputs, and candidate skills.
4. **Compile to ASL**: transmute workflow → `asl` (`StartAt`, `States`), attach `AgentBinding` per Task:
  - `agent_template_ref`: e.g., `"agent_template_worker@1.0.0"`
  - `skills`: e.g., `["skill://web.search@1.0.0", "skill://summarize@1.0.0"]`
5. **Validate**: `validate_workflow(workflow_json, schema_path, imports_base_dir, skills_base_dir)`.
6. **Approval**: confirm with user; persist workflow JSON if desired.

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
load_skill(manifest_id="…manifest-id-of-web.search…", agent_id=self.id)

# 4) Do work (call registered web_search tool, etc.) and produce output JSON
research_output = {"urls": ["https://example.com/a", "https://example.com/b"], "notes": "…"}

# 5) Update control-plane + data-plane
update_workflow_control_plane("71c76b4d-c004-4910-a789-466241d1170c", "Research",
                              new_status="done",
                              output_json=json.dumps(research_output),
                              lease_token=token)

# 6) Unload skill (best-effort) + release lease
unload_skill(manifest_id="…manifest-id-of-web.search…", agent_id=self.id)
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
load_skill(manifest_id="…manifest-id-of-summarize…", agent_id=self.id)

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
unload_skill(manifest_id="…manifest-id-of-summarize…", agent_id=self.id)
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

---

## Update Oct-2025: CSV-first prototyping & stub MCP server

**CSV-first rapid skill prototyping**
- Author many skills and their MCP tools in simple CSV files
- Generate validated skill manifests plus a registry for discovery
- Stand up a stub MCP server that exposes deterministic tools for BDD-style tests

### What each file is for

1. `skills.csv`

Purpose: the master list of **skills** (i.e., capabilities you want agents to load). Each row becomes one **skill manifest (v2.0.0)** when you run `csv_to_manifests.py`.

Typical columns (minimal core):
- `manifestId` (stable UUID or slug)
- `skillPackageId` (package/namespace)
- `skillName` and `skillVersion`
- `description`, `tags` (comma-sep)
- Optional policy fields (e.g., `permissions.secrets`)

You **do not** list tools here in detail - just define the skill itself.

2. `skill_tool_refs.csv`

Purpose: maps **skills → tools** (many-to-many). This is how you attach tools to a given skill without duplicating tool definitions. `csv_to_manifests.py` joins this file to `skills.csv` to populate each manifest’s `requiredTools`.

Typical columns:
- `manifestId` (or `skillName@skillVersion`)
- `toolKey` (a stable logical reference to a tool defined in `mcp_tools.csv`)
- Optional flags (e.g., “required”, “notes”, “alias”)

3. `mcp_tools.csv`

Purpose: declares the **MCP tools** available from logical MCP servers. These are “real” tools in the sense of their **interfaces** (names + JSON schemas), but during testing they’ll be served by the stub server.

Typical columns:
- `serverId` (logical, e.g., `pricing-tools`, `etl-tools`)
- `toolName` (the function name the agent calls)
- `description`
- `json_schema` (OpenAI-style tool schema as JSON text; parameters + required)
- Optional: `tags`, `return_char_limit`, `notes`

This is the **source of truth** for tool signatures. Multiple skills can reference the same `toolKey`/`toolName` here.

4. `mcp_cases.csv`

Purpose: deterministic **stub/mocked I/O** for tools — lets you do BDD/end-to-end tests before real implementations exist. `csv_to_stub_config.py` reads this to build the stub server’s behavior.

Typical columns:
- `serverId`, `toolName` (join to `mcp_tools.csv`)
- `caseId` or `scenario` (a label for the test)
- `inputs_json` (exact args object the tool will be called with)
- `output_json` (the canned return)
- Optional: `delay_ms`, `error` (to simulate failures), `notes`

The stub MCP server matches incoming calls to `(serverId, toolName, inputs_json)` and returns the pre-canned result.

5. `registry.json`

Purpose: **resolver map** from `serverId` → runtime endpoint info. Your **skill loader** uses this to decide where to call each MCP server (stub vs real), without changing manifests.

Typical shape:

```json
{
  "servers": {
    "pricing-tools": { "transport": "ws", "endpoint": "ws://stub-mcp:8765" },
    "etl-tools":     { "transport": "ws", "endpoint": "ws://stub-mcp:8765" }
  },
  "env": "dev"
}

```

Switch this file (or point it to prod URLs) to move from mocks to real backends.

### How they work together (pipeline)

1. Design skills & attach tools
- Author skills in `skills.csv`.
- Map which tools each skill needs in `skill_tool_refs.csv`.
2. Define tool interfaces & test cases
- Describe each tool’s **schema** in `mcp_tools.csv`.
- Provide deterministic test cases in `mcp_cases.csv`.
3. Generate artifacts
- Run **`csv_to_manifests.py`** → emits JSON **skill manifests** (v2.0.0) under `skills/` using (`skills.csv` + `skill_tool_refs.csv` + `mcp_tools.csv`).
- Run **`csv_to_stub_config.py`** → emits `generated/stub/stub_config.json` for the stub MCP server (using `mcp_tools.csv` + `mcp_cases.csv`).
4. Wire endpoints
- Set **`registry.json`** to point each `serverId` to either the **stub MCP server** (for BDD/testing) or a **real MCP server** (for live runs).
5. Load & run
- The **skill loader** reads `skills/` manifests and resolves `serverId` → endpoint via `registry.json`.
- During tests, the loader hits the **stub server**, which returns the canned outputs from `mcp_cases.csv`.
- When implementations are ready, you just update `registry.json` to point to the real MCP servers — no manifest changes required.

### Mental model

- `skills.csv` = “What skills exist?”
- `skill_tool_refs.csv` = “Which tools do those skills require?”
- `mcp_tools.csv` = “What are the tools’ interfaces?”
- `mcp_cases.csv` = “What should those tools return in test scenarios?”
- `registry.json` = “Where do those tools live right now (stub or real)?”