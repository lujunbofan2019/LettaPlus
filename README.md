# Letta–ASL Workflows + Skills (DAG + Ephemeral Workers)

**Purpose:** A practical kit for planning and executing multi-step workflows with:
- **AWS Step Functions–style (ASL)** state machines,
- **ephemeral Letta agents** spawned from **.af v2** templates,
- **dynamically loadable skills** (skill manifests).

Everything is **composition-first**: workflows import `.af v2` bundles and **skill manifests** via filesystem paths (`file://` allowed). No HTTP imports.

---

## Background

- **Choreography, not orchestration** — Workers coordinate themselves through a small **control-plane** persisted in Redis. This cuts single points of failure, scales horizontally, and keeps Planner logic simple.
- **Ephemeral workers** — Each `Task` spawns a short-lived agent from a `.af v2` template, loads only the needed **skills**, runs, then tears down. Clean resource usage and fewer long-lived side effects.
- **Skills as modular capabilities** — A skill manifest bundles LLM directives, required tools, data sources, and permissions, making capabilities portable across agents and workflows.
- **Knowledge Graph for reuse** — Recording edges like `TaskState —uses→ Skill`, `Skill —requires→ Tool`, `State —produced→ Output`, `TaskState —executed_by→ AgentTemplate` enables planning-time retrieval of proven tactics, provenance, and post-mortems. The KG is implementation-agnostic (graph DB or document index).

---

## What’s in this project

### Schemas
- **Workflow (planning)** — `schemas/letta-asl-workflow-2.2.0.json`
- **Skill Manifest (planning)** — `schemas/skill-manifest-v2.0.0.json`
- **Control-plane (execution)**
  - Workflow Meta — `schemas/control-plane-meta-1.0.0.json`
  - State Record — `schemas/control-plane-state-1.0.0.json`
  - Notification Payload — `schemas/notification-payload-1.0.0.json`
- **Data-plane (execution)**
  - Output Envelope — `schemas/data-plane-output-1.0.0.json`

### Planning tools
- `validate_workflow` — validate against `v2.2.0`, resolve imports, check ASL graph.
- `validate_skill_manifest` — validate a single skill manifest against `v2.0.0`.
- `get_skillset` — scan a directory of skills; optional previews for LLM selection.
- `load_skill` / `unload_skill` — attach/detach a skill to an agent (directives, tools, data sources).

### Execution tools (choreography)
- `create_worker_agents` — create one worker agent **per Task state** from `.af v2` templates.
- `create_workflow_control_plane` — seed Redis **control-plane** keys for DAG coordination.
- `notify_next_worker_agent` — send start nudges to source or downstream states.
- `read_workflow_control_plane` — worker reads meta/state and determines **readiness**.
- `acquire_state_lease` — worker acquires a lease (avoid duplicate runs).
- `update_workflow_control_plane` — write `running/done/failed`, timestamps; write output to **data-plane**.
- `finalize_workflow` *(optional)* — verify completion, aggregate outputs, cleanup.

> All tools: single-function, Google-style docstrings, stdlib-only signatures, `file://` allowed, **no HTTP**.

---

## How it fits together

### 1) Plan
1. Planner chats with the user and drafts an ASL workflow.
2. Run **`validate_workflow`**. Fix issues until it passes.

### 2) Execute (choreography)
1. **`create_worker_agents`** → one agent per `Task` from `.af v2`.
2. **`create_workflow_control_plane`** → write:
  - `cp:wf:{workflow_id}:meta` (see `schemas/control-plane-meta-1.0.0.json`)
  - `cp:wf:{workflow_id}:state:{state}` (see `schemas/control-plane-state-1.0.0.json`)
3. **`notify_next_worker_agent`** → nudge **source** states using `schemas/notification-payload-1.0.0.json`.
4. Each worker:
  - **`read_workflow_control_plane`** → ready when *all upstream are `done`*.
  - **`acquire_state_lease`** → **`load_skill`** → run task → **`unload_skill`**.
  - **`update_workflow_control_plane`** (`running/done/failed`) and write output to:
    - `dp:wf:{id}:output:{state}` (see `schemas/data-plane-output-1.0.0.json`)
  - **`notify_next_worker_agent`** for downstream neighbors.
5. **`finalize_workflow`** (optional): confirm terminal states `done`, aggregate outputs, cleanup.

---

## Suggested layout

```
project/
├─ schemas/
│  ├─ letta-asl-workflow-2.2.0.json
│  ├─ skill-manifest-v2.0.0.json
│  ├─ control-plane-meta-1.0.0.json
│  ├─ control-plane-state-1.0.0.json
│  ├─ notification-payload-1.0.0.json
│  └─ data-plane-output-1.0.0.json
├─ af/
│  └─ agent_templates.json
├─ skills/
│  ├─ web.search.json
│  └─ summarize.json
├─ workflows/
│  └─ example_workflow_v220.json
└─ tools/
   ├─ validate_workflow.py
   ├─ validate_skill_manifest.py
   ├─ get_skill_set.py
   ├─ load_skill.py
   ├─ unload_skill.py
   ├─ create_worker_agents.py
   ├─ create_workflow_control_plane.py
   ├─ notify_next_worker_agent.py
   ├─ read_workflow_control_plane.py
   ├─ acquire_state_lease.py
   ├─ update_workflow_control_plane.py
   └─ finalize_workflow.py
```

---

## Notes & guardrails

- **Idempotency**: notifications can duplicate; updates must verify lease token.
- **Security**: enforce `permissions` at skill load; restrict Redis write access.
- **Observability**: log control-plane transitions and skill (un)loads; optional event stream.
- **Portability**: `.af v2` + ASL keep definitions reusable; no HTTP imports. KG is optional and storage-agnostic.
