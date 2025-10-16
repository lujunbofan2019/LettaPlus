# Self-Evolving Agentic AI: Unified Architecture, Workflow Grammar, and Hybrid Memory

## 1. Purpose and Vision
Autonomous agents promise to deliver end-to-end solutions rather than isolated answers. Achieving that promise requires more than a powerful language model; it demands a disciplined way to capture intent, design plans, execute tasks, and learn from the outcome. The LettaPlus architecture treats every engagement as an opportunity to refine institutional knowledge. Agents package their capabilities as reusable skills, stitch those skills into formal workflows, and preserve the results inside a layered memory fabric. Over time the system behaves like an adaptive operations team that can compose best practices, collaborate safely, and evolve in response to new requirements.

## 2. Pillars of the Architecture
LettaPlus is built on three mutually reinforcing pillars:

* **Skills** encapsulate reusable capabilities. Each skill is a bundle of directives, tools, and contextual data that can be attached to any agent that satisfies the trust requirements. Skills provide the atomic building blocks for problem solving.
* **Workflows** define repeatable operating procedures. A workflow is a JSON document that outlines the steps required to solve a problem, the skills each step needs, and the sequencing logic that coordinates a team of workers.
* **Hybrid memory** maintains context across time. Temporal knowledge graphs, hierarchical memory blocks, and external vector stores combine to capture structured facts, conversational nuance, and large source documents without overwhelming any single storage mechanism.

Together these pillars transform a collection of LLM calls into a deliberate planning-and-execution loop. Planners design workflows, workers execute them with skills loaded on demand, and memory services consolidate what happened so the next plan can be smarter.

## 3. Dynamic Capability Framework
The Dynamic Capability Framework (DCF) governs how skills are authored, distributed, and consumed.

### 3.1 Skill Manifest Anatomy
Every skill is described by a manifest that supplies:

* **Identity metadata** such as semantic version, UUID, aliases, authorship, and last-updated timestamps.
* **Directives** that inject domain-specific instructions, safety policies, or formatting requirements into the host agent's system prompt.
* **Tool definitions** that register executable assets: native Letta tool handles, Python modules callable through a sandbox, or endpoints exposed by Model Context Protocol (MCP) servers.
* **Data sources** that preload documents or embeddings into the agent's working memory so the skill starts with relevant context.
* **Permissions and guardrails** that declare the risks associated with the skill and the checks a planner must satisfy before attachment.

The schema enforces these elements, ensuring manifests stay machine readable and can be validated automatically. Because skills carry versioned identities, planners can reason about compatibility, roll back to previous releases, or run A/B comparisons.

### 3.2 Lifecycle and Governance
Skill usage follows a strict lifecycle. Discovery tooling scans directories, verifies schema compliance, and surfaces warnings without interrupting planning. When a workflow requests a skill, the runtime loads it into the target agent, augmenting the system prompt, registering tools, and staging any packaged datasets. A dedicated memory block tracks which skills are active so subsequent loads can be deduplicated and auditable. Once the step completes, the skill can be unloaded to return the agent to a clean baseline. This pattern keeps prompts lean, prevents capability drift, and produces a detailed activity log for later analysis.

### 3.3 Capability Feedback Loop
Execution metadata flows back into planning. Each run records which skills were invoked, the parameters supplied, success or failure outcomes, latency statistics, and any human interventions. Hybrid memory absorbs this telemetry, linking skills to performance metrics inside the knowledge graph. Planners can then select skills based on proven effectiveness, retire underperforming ones, or trigger retraining workflows when the environment changes.

## 4. Workflow Grammar and Runtime
Workflows translate intent into action by encoding state machines that agents can execute.

### 4.1 Declarative Workflow Schema
LettaPlus adopts a JSON grammar inspired by AWS Step Functions. A workflow document contains top-level metadata, import declarations for shared assets, an explicit starting state, and a map of named states. Each state specifies its type (task, choice, parallel, map, or wait), transition targets, and any error-handling branches. Task states add an `AgentBinding` that selects a worker template and lists the skills to load before execution. Optional agent pools allow multiple workers to compete for the same step, improving resilience.

### 4.2 Planning Process
The planner agent conducts an interactive conversation to clarify user goals, available resources, and success criteria. It surveys the skill catalog, proposes candidate steps, and iteratively refines them into a linear standard operating procedure. The SOP is then compiled into the workflow schema, complete with state transitions, retry policies, and data passing rules. Validation checks ensure the JSON conforms to the schema, resolve relative imports, and confirm that every branch leads to a terminal state. Only after the plan passes these gates is it submitted for user approval or persisted as a reusable asset.

### 4.3 Execution Control Plane
Instead of relying on a monolithic scheduler, LettaPlus uses a Redis-backed control plane. When a workflow is instantiated, the control plane materializes a document that tracks metadata, per-state status, dependencies, input payloads, output slots, and current agent assignments. Workers poll the control plane for ready states, acquire leases with time-to-live guarantees, and write back status updates. If a worker crashes or exceeds its lease, another agent can take over without duplicating work. This choreography-first approach allows multiple agents to collaborate without central coordination while still maintaining a consistent audit trail.

### 4.4 Worker Lifecycle
Workers are ephemeral agents derived from reusable `.af v2` templates. Provisioning tooling clones the template, applies any workflow-specific configuration, and records the worker in the control plane. When a worker claims a task, it loads the required skills, executes the step using the registered tools, captures structured outputs, and then unloads the skills to return to the base prompt. Completion triggers downstream states by updating dependency counters inside Redis. Once the entire workflow finishes, finalization routines close any lingering leases, record summary metrics, and optionally delete temporary workers after their logs are archived.

## 5. Hybrid Memory Architecture
Long-lived autonomy requires memory that is both rich and disciplined. LettaPlus combines three modalities to achieve this balance.

### 5.1 Temporally-Aware Knowledge Graph
The knowledge graph stores entities, events, and relationships with temporal annotations. This allows the agent to reason about causality (what action led to what outcome), detect trends (skill performance improving or degrading over time), and maintain provenance. Graph edges can link workflows, skills, users, and results, supporting multi-hop queries such as "Which skill version succeeded most often for invoice reconciliation last quarter?" The graph becomes the institutional backbone that planners consult when drafting new workflows.

### 5.2 Hierarchical Memory Blocks
Borrowing from Letta's architectural principles, memory blocks provide an explicit hierarchy:

* **Working memory** keeps the most recent conversational turns, decision rationales, and short-term commitments close at hand.
* **Long-term archival memory** stores the full history of interactions, annotated with salience scores and timestamps.
* **Task-specific scratch pads** hold intermediate computations or notes that should persist only for the lifetime of a workflow.

Agents can promote items between layers based on importance. For example, the outcome of a successful remediation workflow might graduate from working memory to the knowledge graph, while a partial calculation stays in scratch storage until the step completes. This design prevents context windows from ballooning while preserving critical facts indefinitely.

### 5.3 External Vector Store Interface
Large documents—technical manuals, meeting transcripts, codebases—live in an external vector database. When an agent needs detailed information, it issues semantic queries that retrieve the most relevant passages. The results are bundled into the agent's context alongside graph-derived facts and working-memory notes. By streaming only the necessary fragments, the system avoids overloading the base model yet still offers deep domain recall on demand.

### 5.4 Memory Orchestration
A memory controller coordinates ingestion and retrieval across modalities. After each workflow step, the controller decides whether outputs should update the graph, append to archival logs, or enrich the vector store. During planning, it assembles a "retrieval bundle" composed of salient diary entries, graph paths, and vector hits, giving the planner a holistic view of prior art before proposing the next steps. This orchestration keeps memory coherent and ensures that learning is cumulative rather than fragmented.

## 6. Knowledge Promotion and Continuous Improvement
Every workflow run produces data that can improve future performance. Logs capture context, decisions, tool invocations, and outcomes. Post-run reflection distills these artifacts into structured insights: success metrics, failure causes, remediation steps, and recommendations. Approved workflows are versioned and published to catalogs with descriptive metadata so planners can discover and reuse them. Memory services update the knowledge graph with new edges, increment counters that measure reliability, and flag anomalies requiring human review. Over time, the repository transforms into a library of living SOPs, each linked to the evidence that justifies its existence.

## 7. Multi-Agent Collaboration Protocols
LettaPlus supports teams of agents working in parallel. The control plane exposes a subscription model so observers can react to state changes—reviewers can inspect pending approvals, remediation agents can jump in when retries exceed thresholds, and graph curators can annotate significant events. Because every worker adheres to the same skill-loading conventions and memory policies, agents can hand off tasks without losing context. Structured outputs, stored alongside status metadata, allow downstream agents to consume results programmatically rather than parsing free-form text. This collaborative substrate makes it feasible to compose specialized agents into ad hoc teams tailored to each workflow.

## 8. Tooling and Operational Safeguards
The repository ships with utilities that make the system practical to operate:

* **Schema validators** ensure that skill manifests, workflows, and notification payloads comply with their contracts before deployment.
* **Skill discovery and loading tools** automate catalog management and enforce guardrails during runtime attachment.
* **Control-plane initializers** create Redis documents, seed dependency graphs, and configure worker pools.
* **Lease managers** monitor heartbeat intervals, extend or revoke leases, and trigger retries when tasks stall.
* **Finalization scripts** close workflows, archive logs, and clean up temporary agents once outputs are secured.

All tools emit structured `{ok, status, error}` responses so planners and workers can chain them together within tool-calling conversations. This uniform interface simplifies error handling and keeps agent prompts concise.

## 9. Roadmap and Future Directions
The current architecture lays the foundation for self-evolving agents, but several enhancements remain on the horizon:

* **Automated workflow promotion** that elevates high-performing runs into shared catalogs without human intervention, subject to governance rules.
* **Adaptive skill selection** that leverages knowledge-graph analytics to recommend alternative skills when performance dips.
* **Policy-aware planning** where manifests encode compliance constraints, and planners automatically route sensitive tasks through approved workflows.
* **Temporal analytics** that compare workflow variants across time, helping teams decide when to refactor, retire, or branch SOPs.
* **Proactive memory hygiene** that audits vector stores and archival logs for stale or conflicting information, maintaining a trustworthy knowledge base.

By uniting skills, workflows, and hybrid memory under a coherent governance model, LettaPlus delivers an agent platform that not only executes complex tasks but also learns from every engagement. Each run strengthens the institution's collective intelligence, moving the system closer to truly autonomous operations.