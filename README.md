# Letta–ASL Workflows + Skills (DAG + Ephemeral Workers)

> **Goal**: Plan, validate, and execute multi-step workflows using AWS Step Functions–style (ASL) state machines and **ephemeral Letta agents** equipped with **dynamically loadable skills**.

This project provides:
- **Workflow Schema** — `letta_asl_workflow_schema_v2.2.0`
- **Skill Manifest Schema** — `skill_manifest_schema_v2.0.0`
- Tools (single-function, Letta-friendly):
  1) `validate_workflow`
  2) `validate_skill_manifest`
  3) `get_skillset`
  4) `load_skill`
  5) `unload_skill`

Everything is designed for **composition**: workflows import `.af v2` bundles and skill manifests by file path (`file://` allowed) without inlining.

---

## Architecture Overview

### Conversational Planning → ASL Workflow
A planning agent converses with the user to clarify intent and success criteria, then drafts an **ASL** state machine. Each `Task` state binds to an **ephemeral worker**:

- `agent_template_ref` → a Letta **.af v2 template** for spawning the worker.
- `skills` → a list of **skill IDs** (skill manifests) to load before the task runs.
- Optional `lifecycle` → defaults to `{"mode":"ephemeral","destroy_on_end":true}`.

The workflow can start as SOP-style `steps[]` and compile to `asl` once stabilized.

### Skills as Reusable Building Blocks
A **skill manifest** packages:
- **Directives** (LLM instructions)
- **Required tools** (registered tools by default; `python_source`/`mcp_server` feature-gated)
- **Required data sources** (attached to archival memory, chunked)
- **Permissions** (egress level, secrets)

### Execution (DAG + Ephemeral Workers)
At runtime, for each `Task`:
1. Spawn worker from `.af v2` template.
2. Load skills.
3. Execute task logic (tools/prompts/Parameters).
4. Unload skills and destroy worker.
5. Pass results via ASL `ResultPath`/`ResultSelector`.

Per-agent bookkeeping is stored in a `dcf_active_skills` state block, enabling clean unloads.

---

## Schemas

### Workflow Schema — `letta_asl_workflow_schema_v2.2.0`
- **ASL required** (`asl.StartAt`, `asl.States`).
- `af_imports[]` — file paths/`file://` to `.af v2` bundles (agents/tools).
- `skill_imports[]` — file paths/`file://` to skill manifests (single or `{ "skills": [...] }` bundle).
- Every `Task` requires an `AgentBinding` with:
  - `agent_template_ref` *or* `agent_ref`
  - `skills` (list of skill IDs)
  - optional `lifecycle`, `tool_name`

**Skill ID aliases** supported:
- `skill://{skillName}@{version}`
- `{skillName}@{version}`
- `skill://{skillPackageId}@{version}`
- `{manifestId}`

**File:** `schemas/letta-asl-workflow-2.2.0.json` (also provided below for download)

### Skill Manifest Schema — `skill_manifest_schema_v2.0.0`
- `manifestApiVersion: "v2"`
- `skillName`, `skillVersion` (semver), `description`, optional `tags`
- `skillDirectives` (core behavior)
- `requiredTools[]` (registered tools by default; others feature-gated)
- `requiredDataSources[]` (e.g., inline text)
- `permissions` (`egress: none|intranet|internet`, `secrets: []`)

**File (recommended path):** `schemas/skill-manifest-v2.0.0.json` (ask me to generate if you want it created here)

---

## Tools

### `validate_workflow(workflow_json, schema_path, imports_base_dir=None, skills_base_dir=None) -> dict`
- JSON Schema validation against workflow v2.2.0
- Loads `.af` and skills, indexes agents/skills, resolves every `Task`’s `AgentBinding` and skills
- ASL graph checks (StartAt, transitions, branches, terminals)

**File:** `tools/workflow_validator_v220.py` (download link below)

### `validate_skill_manifest(manifest_json, schema_path) -> dict`
- Validate one skill manifest against `skill_manifest_schema_v2.0.0` + static checks (unique tool names, permissions)

### `get_skillset(manifests_dir=None, schema_path=None, include_previews=False, preview_chars=None) -> dict`
- Scan a directory for skills, optionally validate, return a catalog with aliases and directive previews
- **File:** `tools/skill_discovery_tool.py`

### `load_skill(manifest_id, agent_id) -> dict`
- Load directives, attach tools, attach data sources, update `dcf_active_skills` state; feature gates for `python_source`/`mcp_server`

### `unload_skill(manifest_id, agent_id) -> dict`
- Idempotent teardown; detaches tools/blocks, removes or empties state block

---

## Example

**Workflow:** `workflows/example_workflow_v220.json`  
- Imports `.af` bundle `af/agent_templates.json` (expects `agent_template_worker@1.0.0`)
- Imports two skills: `skills/web.search.json`, `skills/summarize.json`
- Two tasks: **Research → Summarize**, each spawns a worker and loads appropriate skills

**Skills:**  
- `skills/web.search.json` (uses a registered web search tool; replace placeholder `platformToolId`)  
- `skills/summarize.json` (pure LLM directive skill)

---

## Suggested Layout

```
project/
├─ schemas/
│  ├─ letta-asl-workflow-2.2.0.json
│  └─ skill-manifest-v2.0.0.json
├─ af/
│  └─ agent_templates.json
├─ skills/
│  ├─ web.search.json
│  └─ summarize.json
├─ workflows/
│  └─ example_workflow_v220.json
└─ tools/
   ├─ workflow_validator_v220.py
   └─ skill_discovery_tool.py
```