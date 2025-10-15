# Letta–ASL Workflows + Skills (DAG + Ephemeral Workers)

> **Goal**: Plan, validate, and execute multi-step workflows using AWS Step Functions–style (ASL) state machines and **ephemeral Letta agents** equipped with **dynamically loadable skills**. Execution is **choreography-first**: workers self-coordinate via a RedisJSON control-plane—no central orchestrator loop.

This project provides:

- **Schemas**
    - `schemas/letta-asl-workflow-2.2.0.json` — Workflow JSON schema (ASL + Letta bindings)
    - `schemas/skill-manifest-v2.0.0.json` — Skill manifest JSON schema
    - `schemas/control-plane-meta-v1.0.0.json` — *Documented shape* of control-plane meta (see “Control Plane & Data Plane”)
    - `schemas/control-plane-state-v1.0.0.json` — *Documented shape* of per-state docs
    - `schemas/notification-payload-v1.0.0.json`
    - `schemas/data-plane-output-v1.0.0.json`
- **Planning tools**
    1) `validate_workflow(workflow_json, schema_path, imports_base_dir=None, skills_base_dir=None)`
    2) `validate_skill_manifest(manifest_json, schema_path)`
    3) `get_skillset(manifests_dir=None, schema_path=None, include_previews=False, preview_chars=None)`
    4) `load_skill(manifest_id, agent_id)` and `load_skill_with_resolver(manifest_id, agent_id)`
    5) `unload_skill(manifest_id, agent_id)`
- **Execution tools**
    6) `create_workflow_control_plane(workflow_id, asl_json, agents_map_json=None, redis_url=None)`
    7) `create_worker_agents(workflow_id, af_bundle_path, agent_template_ref, skills_dir=None, planner_agent_id=None, redis_url=None)`
    8) `read_workflow_control_plane(workflow_id, state=None, redis_url=None, include_meta=True)`
    9) `update_workflow_control_plane(workflow_id, state, status, output_json=None, lease_token=None, error_message=None, redis_url=None)`
    10) `acquire_state_lease(workflow_id, state, owner_agent_id, lease_ttl_s=300, ...)`
    11) `renew_state_lease(workflow_id, state, lease_token, ...)`
    12) `release_state_lease(workflow_id, state, lease_token, ...)`
    13) `notify_next_worker_agent(workflow_id, source_state=None, reason=None, payload_json=None, ...)`
    14) `notify_if_ready(workflow_id, state, ...)`
    15) `finalize_workflow(workflow_id, delete_worker_agents=True, ...)`
- **Testing tools**
    16) `csv_to_manifests(skills_csv_path="skills_src/skills.csv", refs_csv_path="skills_src/skill_tool_refs.csv", ...)`
    17) `csv_to_stub_config(mcp_tools_csv_path="skills_src/mcp_tools.csv", mcp_cases_csv_path="skills_src/mcp_cases.csv", ...)`

Everything is designed for **composition**: workflows import `.af v2` bundles and skill manifests by file path (`file://` allowed) without inlining. Skills are loaded/unloaded dynamically per worker.

---

## Architectural Overview

### Key concepts
- **Planner agent**: converses with the user, gathers intent and constraints, proposes & iterates the plan, then compiles SOP steps into an **ASL** state machine inside the workflow JSON (validated against `letta-asl-workflow-2.2.0.json`). The Planner never micromanages workers—workers run autonomously.
- **Ephemeral workers**: short-lived Letta agents instantiated from a shared **.af v2 template** (e.g., `agent_template_worker@1.0.0`). Before each Task, the worker **loads skills** relevant to that Task and **unloads** them after.
- **Skills**: packaged capabilities described by `skill-manifest-v2.0.0.json` (directives, required tools, required data sources, permissions). Reusable across workflows.
- **Choreography**: workers coordinate via messages and a **RedisJSON control-plane**. Each worker checks readiness (all upstream `done`), acquires a lease, runs, writes output, releases lease, and notifies downstream.
- **Knowledge graph** *(optional but recommended)*: the skill catalog (from `get_skillset`) can be ingested into a lightweight KG (tags → tools → capabilities → success metrics). The Planner queries it to select candidate skills and to justify the plan (traceability).

### Control Plane & Data Plane (RedisJSON)
We keep two logical spaces in Redis:

- **Control-plane meta** — `cp:wf:{workflow_id}:meta`  
  Minimal JSON document with:
  ```jsonc
  {
    "workflow_id": "…",
    "states": ["Research", "Summarize", "..."],
    "deps": {
      "Research":   { "upstream": [],           "downstream": ["Summarize"] },
      "Summarize":  { "upstream": ["Research"], "downstream": [] }
    },
    "agents": { "Research": "agent_id_…", "Summarize": "agent_id_…" },
    "planner_agent_id": "agent_id_planner",
    "created_at": "ISO-8601",
    "finalized_at": null,
    "status": "active" // updates to succeeded|failed|partial|cancelled on finalize
  }
  ```

- **Per-state doc** — `cp:wf:{workflow_id}:state:{state}`
  ```jsonc
  {
    "state": "Research",
    "status": "pending", // -> running|done|failed|cancelled
    "attempts": 0,
    "lease": { "token": null, "owner_agent_id": null, "ts": null, "ttl_s": 300 },
    "started_at": null,
    "finished_at": null,
    "errors": []
  }
  ```

- **Data-plane outputs** — `dp:wf:{workflow_id}:output:{state}`  
  Arbitrary JSON written by the worker for downstream consumption.  
  Example: `{ "urls": [...], "notes": "…" }`

> We **do not** delete control-plane/data-plane keys after execution (audit trail). `finalize_workflow` optionally deletes worker agents only.

### Why leases?
Multiple agents could race to run a state (retries, scaling). A soft **lease** (token + timestamp) in the state doc, updated atomically via Redis WATCH/MULTI, ensures only one active runner. If the runner dies, the lease **expires** and another agent can take over.

---

## Planner Flow (from intent to ASL)

1. **Conversation**: collect objective, inputs, outputs, guardrails, budget/time, egress policy.
2. **Skill discovery**: call `get_skillset(...)` (optionally with validation). Optionally enrich with a knowledge graph for better selection & justification.
3. **Draft SOP**: a linear `steps[]` plan with step names, inputs/outputs, and candidate skills.
4. **Compile to ASL**: transmute SOP → `asl` (`StartAt`, `States`), attach `AgentBinding` per Task:
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
6. **Write output + status**: `update_workflow_control_plane(wf_id, state, status="done", output_json=...)`.
7. **Unload skills**: `unload_skill(manifest_id, agent_id)` (best-effort; agent may also be ephemeral).
8. **Release lease**: `release_state_lease(wf_id, state, lease_token)`.
9. **Notify downstream**: `notify_next_worker_agent(wf_id, source_state=state, reason="upstream_done")`.

**On long tasks**: periodically `renew_state_lease(...)` until done.

**On errors**: `update_workflow_control_plane(..., status="failed", error_message=...)`, release lease, (optionally) notify downstream or planner for compensating logic.

---

## Tool Catalog (purpose & typical usage)

> All tools are **single-function** for Letta compatibility. Return shape is `{status, error, ...}` where `error` is `None` on success.

### Planning
- **`validate_workflow`** — JSON Schema validation + import resolution + ASL graph checks.
- **`validate_skill_manifest`** — Schema validation + static checks (unique tools, permissions).
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
- `skills/web.search.json` — registered `web_search` tool, directives for querying and URL selection.
- `skills/summarize.json` — pure LLM directive skill for concise summaries.  
  Validate them:
```python
validate_skill_manifest(open("schemas/skill-manifest-v2.0.0.json").read(), "schemas/skill-manifest-v2.0.0.json")  # schema self-check (optional)
# For each manifest file:
validate_skill_manifest(open("skills/web.search.json").read(), "schemas/skill-manifest-v2.0.0.json")
validate_skill_manifest(open("skills/summarize.json").read(), "schemas/skill-manifest-v2.0.0.json")
```

### 2) Workflow (ASL + Letta bindings)
`workflows/example_workflow_v220.json` (highlights):
```jsonc
{
  "workflow_id": "58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1",
  "workflow_name": "Research & Summarize",
  "version": "1.0.0",
  "af_imports": ["file://af/agent_templates.json"],
  "skill_imports": ["file://skills/web.search.json", "file://skills/summarize.json"],
  "asl": {
    "StartAt": "Research",
    "States": {
      "Research": {
        "Type": "Task",
        "Comment": "Find high-quality sources",
        "Parameters": {"query.$": "$.topic"},
        "ResultPath": "$.research",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
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
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://summarize@1.0.0"]
        },
        "End": true
      }
    }
  }
}
```

Validate:
```python
validate_workflow(open("workflows/example_workflow_v220.json").read(),
                  "schemas/letta-asl-workflow-2.2.0.json",
                  imports_base_dir=".", skills_base_dir="./skills")
```

### 3) Create control-plane + workers
```python
# Seed control-plane from ASL
create_workflow_control_plane(
  workflow_id="58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1",
  asl_json=json.dumps(json.load(open("workflows/example_workflow_v220.json"))["asl"])
)

# Create workers from .af v2 template (planner can pass its own id)
create_worker_agents(
  workflow_id="58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1",
  af_bundle_path="af/agent_templates.json",
  agent_template_ref="agent_template_worker@1.0.0",
  skills_dir="./skills"
)
```

### 4) Kick off
```python
# Notify source states (no upstream) or call notify_if_ready for each start state:
notify_next_worker_agent(
  workflow_id="58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1",
  reason="initial"
)
```

### 5) Worker loop (Research)
Inside the **Research** worker agent’s message handler (conceptual sequence):
```python
# 1) Ensure ready (if self-notified)
notify_if_ready("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Research")

# 2) Acquire lease
lease = acquire_state_lease("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Research", owner_agent_id=self.id)
token = lease["lease"]["token"]

# 3) Load skills
load_skill(manifest_id="…manifest-id-of-web.search…", agent_id=self.id)

# 4) Do work (call registered web_search tool, etc.) and produce output JSON
research_output = {"urls": ["https://example.com/a", "https://example.com/b"], "notes": "…"}

# 5) Update control-plane + data-plane
update_workflow_control_plane("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Research",
                              status="done",
                              output_json=json.dumps(research_output),
                              lease_token=token)

# 6) Unload skill (best-effort) + release lease
unload_skill(manifest_id="…manifest-id-of-web.search…", agent_id=self.id)
release_state_lease("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Research", token)

# 7) Notify downstream (Summarize)
notify_next_worker_agent("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", source_state="Research", reason="upstream_done")
```

### 6) Worker loop (Summarize)
```python
# 1) Wait for notify, then (optionally) ensure ready
notify_if_ready("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Summarize")

# 2) Acquire lease
lease = acquire_state_lease("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Summarize", owner_agent_id=self.id)
token = lease["lease"]["token"]

# 3) Load skill
load_skill(manifest_id="…manifest-id-of-summarize…", agent_id=self.id)

# 4) Read upstream output
cp = read_workflow_control_plane("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", state="Research")
sources = cp.get("outputs", {}).get("Research", {}).get("urls", [])

# 5) Summarize and produce output
summary = {"text": "Here’s a 200-word synthesis...", "sources": sources}

# 6) Update + release
update_workflow_control_plane("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Summarize",
                              status="done",
                              output_json=json.dumps(summary),
                              lease_token=token)
unload_skill(manifest_id="…manifest-id-of-summarize…", agent_id=self.id)
release_state_lease("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1", "Summarize", token)

# 7) Since this is terminal, the Planner can call finalize_workflow
```

### 7) Finalize
```python
finalize_workflow("58b1c4cc-74c1-4a6f-bd5b-8c6b9779d4a1",
                  delete_worker_agents=True,
                  preserve_planner=True,
                  close_open_states=True,
                  finalize_note="Completed successfully.")
```
This writes an audit record at `dp:wf:{id}:audit:finalize` and computes an overall status.

---

## Background Notes - why this works

- **ASL semantics** give a well-understood contract for branching, retries, and data paths. Our JSON schema keeps a strict subset and adds `AgentBinding` to bind states to Letta agents/skills.
- **DAG + choreography** avoids a single orchestrator bottleneck. Each worker owns its lifecycle, which scales naturally and tolerates partial failures.
- **RedisJSON** provides atomic, partial updates and fast reads for lots of small state docs. WATCH/MULTI gives optimistic concurrency for leases and status transitions.
- **Skills as manifests** decouple “how to do things” (tools, prompts, data) from “when” (workflow). They can be versioned, discovered, and reasoned about (via a knowledge graph or tags).
- **Auditability**: keeping control/data planes post-run enables traceability, benchmarking, and post-mortems.

---

## Project Layout
```
project/
├─ schemas/
│  ├─ letta-asl-workflow-2.2.0.json
│  ├─ skill-manifest-v2.0.0.json
│  ├─ data-plane-output-1.0.0.json
│  ├─ notification-payload-1.0.0.json
│  ├─ control-plane-meta.json
│  └─ control-plane-state.json
├─ af/
│  └─ agent_template.json
├─ skills/
│  ├─ <skillName>@<version>.json
│  └─ ...
├─ workflows/
│  └─ example_workflow_v2.2.0.json
└─ tools/
   ├─ acquire_state_lease.py
   ├─ create_worker_agents.py
   ├─ create_workflow_control_plane.py
   ├─ finalize_workflow.py
   ├─ get_skillset.py
   ├─ load_skill.py
   ├─ notify_if_ready.py
   ├─ notify_next_worker_agent.py
   ├─ unload_skill.py
   ├─ read_workflow_control_plane.py
   ├─ update_workflow_control_plane.py
   ├─ renew_state_lease.py
   ├─ release_state_lease.py
   ├─ validate_skill_manifest.py
   ├─ validate_workflow.py
   └─ ...   
```

---

## Operational Tips & FAQ

- **Many workers from the same .af template?** No conflict: Letta de-duplicates registered tools by name/ID. If your template includes source-defined tools, our `load_skill` checks platform registry by name first.
- **When to use `notify_if_ready` vs `notify_next_worker_agent`?**
    - Use `notify_next_worker_agent` after a state completes to fan-out to neighbors.
    - Use `notify_if_ready` as a guard when something “external” nudges a state early.
- **Leases & TTLs**: pick TTL ≥ 2× your heartbeat; renew at 1/3 TTL. On long tool calls, renew between sub-steps.
- **Error policy**: workers set `status="failed"` with `error_message` → Planner can decide to retry (re-notify), skip, or finalize as failed.
- **Security**: skills can declare `permissions.egress` and `permissions.secrets`. Enforce on load or at tool boundary.
- **Cleanup**: `finalize_workflow` deletes agents (optional) but preserves Redis keys for audits.

---

## Update Oct-2025: CSV-first prototyping & stub MCP server

**CSV-first rapid skill prototyping**
- Author many skills and their MCP tools in simple CSV files
- Generate validated skill manifests plus a registry for discovery
- Stand up a stub MCP server that exposes deterministic tools for BDD-style tests

**Stub MCP server to exercise workflows end-to-end before real tool implementations exist**
- `stub_mcp/stub_mcp_server.py` — trivial stdio/WebSocket MCP that reads `generated/stub/stub_config.json`
- `stub_mcp/Dockerfile` — containerize the stub for docker-compose
- `docker-compose.yaml` — example compose file including Letta and the stub MCP

**Local resolver in the skill loader to choose real vs. stub endpoints without editing manifests.**
- `skills_src/registry.json` — generated registry of skills
- `skills_src/resolver.json` — maps logical serverId → transport/endpoint; consumed by `load_skill_with_resolver`

---

## Change to Directory Layout

```
project/
├─ schemas/
│  ├─ ...
├─ tools/
│  ├─ csv_to_manifests.py
│  ├─ csv_to_stub_config.py
│  ├─ ... (other DCF tools)
├─ skills_src/                 # input CSVs + generated artifacts
│  ├─ skills.csv               # one row per skill
│  ├─ mcp_tools.csv            # one row per MCP tool
│  ├─ skill_tool_refs.csv
│  └─ registry.json            # generated: catalog of skills (for Planner/loader)
├─ skills/                     # generated manifests
│  ├─ <skillName>@<version>.json
│  └─ ...
├─ generated/
│  └─ stub/
│     ├─ stub_config.json      # generated MCP tool behavior config
│     └─ ...
├─ stub_mcp/
│  ├─ stub_mcp_server.py
│  └─ Dockerfile
├─ docker-compose.yaml         # runs Letta + stub MCP
└─ workflows/                  # your workflows (ASL + Letta bindings)
   └─ example_workflow_v2.2.0.json
```

---

## CSV specs

### skills_src/skills.csv
Columns
- manifestId (optional; otherwise auto)
- skillPackageId (optional)
- skillName (required)
- skillVersion (required, semver)
- description
- tags (space or comma separated)
- permissions_egress (none|intranet|internet)
- permissions_secrets (comma separated)
- skillDirectives (free text)
- requiredTools (comma-separated tool keys; see below)
- requiredDataSources (optional; JSON list or blank)

Each row → one manifest in `skills/` and an entry in `skills_src/registry.json` (with aliases and path).

### skills_src/tools.csv
Columns
- key (required; unique row id referenced by skills.csv requiredTools)
- name (tool name exposed to the agent)
- description
- serverId (logical MCP server id; NOT a URL)
- transport (stdio|websocket)
- endpoint (ignored for stdio; ws URL for websocket)
- args_schema_json (optional; JSON schema for parameters)
- behavior_type (stub|echo|fail) — testing behavior
- behavior_inputs (optional; JSON switch/case inputs for stub)
- behavior_output (optional; JSON to return)
- error_message (when behavior_type=fail)

Each row → an MCP tool definition for the stub server. The stub uses the behavior columns to respond deterministically.

---

## Quickstart

1) Prepare CSVs
```
skills_src/skills.csv
skills_src/tools.csv
```

2) Generate manifests + registry
```
python tools/csv_to_manifests.py   --skills_csv skills_src/skills.csv   --tools_csv skills_src/tools.csv   --schema schemas/skill-manifest-v2.0.0.json   --out_dir skills   --registry_out skills_src/registry.json
```

3) Generate stub MCP config
```
python tools/csv_to_stub_config.py   --tools_csv skills_src/tools.csv   --out generated/stub/stub_config.json
```

4) Create resolver for the loader (choose stub endpoints)
   Create `skills_src/resolver.json`:
```json
{
  "servers": {
    "stub://default": { "transport": "websocket", "endpoint": "ws://stub-mcp:8765" }
  },
  "aliases": {
    "web.search.svc": "stub://default",
    "db.ops.svc": "stub://default"
  }
}
```

5) Run services
- Ensure your Letta server is reachable (e.g., http://letta:8283).
- Bring up the stub MCP with docker-compose.

6) Load a skill that references logical server IDs
- Ensure your `load_skill_with_resolver` tool reads `skills_src/registry.json` and `skills_src/resolver.json`.
- When it sees a required tool with source_type=mcp_server + serverId, it maps serverId → (transport, endpoint) using the resolver and attaches the tool to the agent.

7) Execute a workflow end-to-end
- Use the Planner to validate a workflow (validate_workflow), seed the control-plane, create workers, and notify source states.
- Workers acquire leases, load skills, call MCP tools (stubbed), write outputs, and notify downstream.
- Finalize when terminals are done.

---

## Stub MCP server

Runtime behavior
- Reads `generated/stub/stub_config.json` on start.
- Exposes each tool from tools.csv.
- Behavior modes:
  - stub: match on behavior_inputs (exact or pattern) and return behavior_output
  - echo: return the input arguments under `{ "ok": true, "echo": { ... } }`
  - fail: raise a structured MCP error with error_message

Transport
- WebSocket on port 8765 (default). Stdio mode is also available for simple local runs.

Dockerfile (stub_mcp/Dockerfile)
- Minimal Python base image
- Copies `stub_mcp_server.py` and installs no heavy deps
- Entrypoint launches the WebSocket server
