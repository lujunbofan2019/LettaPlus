# Self‑Evolving Tool‑Using AI Agent with Triangulated Memory and Policy‑Driven Adaptation

## Abstract

Disclosed herein is a computer-implemented system and method for constructing an artificial intelligence (AI) agent that **learns from prior experiences** to improve future performance on substantially similar tasks. The agent executes tasks by selecting and invoking external software tools through a standardized tool layer, records outcomes, consolidates experience into a multi‑tier memory substrate, and **adapts** subsequent behavior through a policy service that optimizes tool and strategy selection subject to constraints (e.g., cost, latency, and reliability). The system integrates (i) a *sequential episodic* memory (diary), (ii) a *knowledge graph* of entities, relations, and statistical performance, and (iii) a *vector store* of semantically embedded lessons and procedures. A planner composes executable plans or selects Standard Operating Procedures (SOPs), an executor enforces resilience mechanisms and telemetry, a validator checks success criteria, and a reflector promotes reusable lessons and SOPs through statistically governed rules. The architecture and end‑to‑end workflow are depicted in **Figure 1** and **Figure 2**, respectively.

## Technical Field

The disclosure relates to machine intelligence, and more specifically to memory‑augmented, tool‑using agents that learn online from execution feedback and human guidance.

## Background

General‑purpose language model agents frequently fail to translate intent into reliable action in production environments due to (a) insufficient memory structures, (b) brittle tool selection, and (c) weak feedback loops. Conventional retrieval‑augmented generation (RAG) pipelines and single‑store memories lack **credit assignment** between context, chosen tools, and observed outcomes, producing repeated mistakes and unstable behavior. There is a need for a system that (1) **captures** experiences at the right granularity, (2) **consolidates** them into durable, queryable knowledge, and (3) **changes** future behavior in a controlled, auditable, and testable manner.

## Summary

The system comprises an **Orchestrator**, **Planner**, **Executor**, **Validator**, **Memory Manager**, **Policy Service**, **SOP Registry**, **Reflector/Consolidation jobs**, **Evaluator/A‑B Router**, and a **Guardrails** layer, operating over a **Data Plane** that includes an **Experience Log**, **Knowledge Graph**, **Vector Store**, **Episodic Diary**, and **Object Storage** for artifacts. During a task run, the Orchestrator obtains a retrieval bundle from the Memory Manager (triangulated across all memories), queries the Policy Service for ranked tool strategies, and asks the Planner to output an executable plan or SOP selection. The Executor runs the plan with resilience and emits structured telemetry; the Validator determines pass/fail against data contracts. Post‑run, the Reflector synthesizes lessons, candidates for SOPs, and performance deltas, which the Memory Manager persists per a salience‑gated write policy. The Evaluator and Policy Service update online and offline policies. See **Figure 1** (System Architecture) and **Figure 2** (Sequence Workflow).

## Brief Description of the Drawings

- **Figure 1 (System Architecture)** — Depicts services (Orchestrator, Planner, Executor, Validator, Memory Manager, Policy Service, SOP Registry, Reflector, Evaluator, Guardrails) and data plane components (Experience Log, Knowledge Graph, Vector Store, Episodic Diary, Object Storage), and their interconnections.  
  *[Insert the System Architecture Mermaid diagram here]*

- **Figure 2 (Sequence Workflow)** — Depicts the end‑to‑end task lifecycle from user submission through planning, execution, validation, logging, consolidation, and policy updates.  
  *[Insert the Sequence Mermaid diagram here]*

## Detailed Description

### 1. Architecture Overview

Referring to **Figure 1**, the system enforces policy and budgetary limits at ingress via **Guardrails** and then orchestrates a deterministic task lifecycle through the **Orchestrator**. The Orchestrator coordinates: (a) **triangulated retrieval** via the **Memory Manager**, (b) **strategy ranking** via the **Policy Service**, (c) **plan generation** via the **Planner**, (d) **plan execution** via the **Executor** using a standardized tool layer, and (e) **result validation** via the **Validator**. Telemetry is appended to the **Experience Log**; artifacts are placed in **Object Storage** with controlled retention. The **Reflector** converts raw traces into lessons and SOP candidates, while the **Evaluator** performs offline model training and regression checks. An **A/B Router** optionally partitions traffic for controlled evolution.

### 2. Components

#### 2.1 Guardrails

The Guardrails component applies redaction and policy checks to inputs and planned actions: personally identifiable information (PII) handling, spend/latency ceilings, compliance constraints, and permission scopes. Guardrails produce hard failures or suggest sanitized alternatives.

#### 2.2 Orchestrator

The Orchestrator initializes a `run_id`, materializes a `task_context` (user, tenant, file types, SLA), invokes the **Memory Manager** for retrieval, consults the **Policy Service**, sends inputs to the **Planner**, dispatches the output plan to the **Executor**, and finally aggregates validation results and provenance for return to the client. The Orchestrator is the single source of truth for run state transitions.

#### 2.3 Memory Manager

The Memory Manager offers a unified API over three heterogeneous memories:

- **Episodic Diary** (e.g., Letta/MemGPT): sequential traces and reflective notes.  
- **Knowledge Graph** (e.g., Graphiti + Neo4j): normalized entities (Tasks, Tools, Strategies, SOPs, Environments, ErrorClasses) and edges with statistics (e.g., `p_success`, `p95_latency`, `n`).  
- **Vector Store** (e.g., Chroma): embeddings of consolidated lessons, SOP text, postmortems, and human critiques, queryable via k‑nearest neighbors with metadata filters.

**Triangulated Retrieval (plan‑time).** Given the `task_context`, the Memory Manager: (i) retrieves top‑k semantic neighbors from the vector store, (ii) issues Cypher queries to the knowledge graph for best‑known strategies and failure modes, and (iii) fetches a bounded set of reflective diary snippets. The Manager composes a **retrieval bundle** for the Planner.

**Salience‑Gated Writes (finish‑time).** The Manager appends to the Experience Log unconditionally, but only updates the vector store and graph when novelty or material performance deltas are detected. It writes diary summaries for human interpretability.

#### 2.4 Policy Service

The Policy Service computes a context‑dependent ranking over `(tool, strategy)` arms using an online **contextual bandit** (e.g., Thompson Sampling) and a periodically retrained offline **ranker** (policy distillation) trained on logged interactions with propensity scores. The Planner consumes these rankings as hints; the Orchestrator records propensities and realized rewards for unbiased evaluation.

#### 2.5 Planner

The Planner transforms a natural language goal and the retrieval bundle into either (a) an SOP reference when preconditions match, or (b) an executable **Plan JSON** consisting of steps with explicit tools, parameters, timeouts, retry/fallback graphs, and expected cost/latency ranges. The Planner never invents tools and must satisfy Guardrails and SLA constraints.

#### 2.6 Executor and Tool Layer

The Executor faithfully executes the plan: enforcing **idempotency keys**, **exponential backoff with jitter**, **circuit breakers** per tool, and **budget‑aware retries**. A standardized **tool layer** (e.g., MCP adapters) defines each tool’s capability schema, rate limits, error mapping to canonical **ErrorClasses** (`Timeout`, `RateLimit`, `Auth`, `SchemaMismatch`, `NotFound`, `ToolNotFit`, `TransientNetwork`, `DeterministicFailure`). Step‑level telemetry is emitted to the Experience Log; large artifacts are stored with short TTL.

#### 2.7 Validator

The Validator compares produced artifacts against **success criteria** and **data contracts** (e.g., schema checks, row counts, checksums, or task‑specific quality metrics) and returns pass/fail with reasons.

#### 2.8 SOP Registry

An SOP is a versioned, parameterized, validated procedure with defined preconditions, steps, budgets, and postconditions. SOPs include evidence (supporting run IDs and uplift metrics) and linked **tests/fixtures**. The Registry exposes read APIs for the Planner and write‑once promote APIs gated by Evaluator checks.

#### 2.9 Reflector / Consolidation

The Reflector consumes recent runs, synthesizes **lessons** (preconditions → recommended actions) with confidence scores, deduplicates near‑duplicates, and nominates SOP candidates. Promotion requires statistical uplift against baseline, sufficient sample size, and absence of recent critical incidents.

#### 2.10 Evaluator and A/B Router

The Evaluator supports offline training, **off‑policy evaluation**, drift and regression detection, and composes dashboards from the Experience Log. The A/B Router optionally allocates traffic to candidate policies or SOPs for online validation.

### 3. Data Models

#### 3.1 Experience Tuple

```json
{
  "run_id": "uuid",
  "task_id": "uuid",
  "plan_id": "uuid",
  "user_id": "anonymized",
  "context_features": {
    "tenant": "A",
    "filetype": "pdf",
    "size_bucket": "50-100MB",
    "sla_class": "standard",
    "recent_error_class": "Timeout"
  },
  "steps": [
    {
      "step_id": "s1",
      "tool": "ocr_v3",
      "params": {"chunk_mb": 1},
      "start_ts": "…",
      "end_ts": "…",
      "outcome": {"success": true},
      "cost": 0.012,
      "latency_ms": 3200
    }
  ],
  "result": {"success": true, "artifact_refs": ["obj://…"], "metrics": {"latency_ms": 9200}},
  "reward": 0.83,
  "user_feedback": 5
}
```

#### 3.2 SOP Schema (Registry)

```json
{
  "id": "sop-123",
  "name": "BankStatementPDF_to_CSV_v3",
  "version": "3.1.0",
  "owners": ["team-data-ingest"],
  "preconditions": {"filetype": ["pdf"], "size_mb": {"gt": 0, "lt": 50}, "tenant": ["A","B"]},
  "steps": [
    {"tool": "ocr_v3", "params": {"chunk_mb": 1, "timeout_ms": 15000}},
    {"op": "normalize_tables"},
    {"validate": "schema_bank_statement_v3"}
  ],
  "budget": {"max_latency_ms": 10000, "max_cost": 0.05},
  "postconditions": ["csv.rows>0", "schema==bank_statement_v3"],
  "evidence": {"runs": ["…"], "uplift_vs_baseline": 0.32},
  "tests": [{"fixture_id": "fx-01", "expected_hash": "…", "max_latency_ms": 12000}],
  "status": "stable"
}
```

#### 3.3 Knowledge Graph (Selected Relations)

- `(:TaskCluster)-[:BEST_WITH {p_success, p95_latency, n}]->(:Strategy)`  
- `(:Tool)-[:FAILS_WITH {ctx_hash, p}]->(:ErrorClass)`  
- `(:SOP)-[:APPLIES_TO]->(:TaskCluster)`  
- `(:Strategy)-[:USES]->(:Tool)`  
- `(:Env)-[:LIMITS]->(:Tool)`

### 4. Operational Workflow

Referring to **Figure 2**, the workflow comprises:

1. **Ingress and Guarding.** The client submits a goal and constraints; Guardrails sanitize or reject non‑compliant inputs.  
2. **Run Initialization.** The Orchestrator creates `run_id` and `task_context`.  
3. **Retrieval.** The Memory Manager returns a retrieval bundle: top‑k semantic neighbors, graph‑level best strategies and failure modes, and diary snippets.  
4. **Policy Suggestion.** The Policy Service returns ranked `(tool, strategy)` arms with uncertainty.  
5. **Planning.** The Planner outputs either an SOP reference or a Plan JSON conforming to constraints and hints.  
6. **Execution.** The Executor invokes tools with resilience; each step is logged; artifacts are persisted with short TTL.  
7. **Validation.** The Validator applies success criteria; results are reported to the Orchestrator.  
8. **Experience Logging.** The Orchestrator writes the Experience Tuple to the Experience Log.  
9. **Consolidation.** The Reflector synthesizes lessons and SOP candidates and writes consolidated knowledge to the graph, vector store, and diary.  
10. **Policy Update.** Online bandit updates and offline policy distillation occur; Evaluator monitors regressions.  
11. **Response.** The Orchestrator returns outputs and provenance (e.g., `run_id`, `sop_id`) to the client.

### 5. Algorithms

#### 5.1 Triangulated Retrieval

Given `goal` and `task_context`, compute:

- **Vector Retrieval:** embed `(goal ⊕ constraints)` and query vector store for top‑k lessons/SOPs/postmortems with metadata filters.  
- **Graph Query:** select candidate strategies maximizing `p_success` subject to latency/cost bounds for the matched `TaskCluster`.  
- **Diary Snippets:** select at most N recent reflective notes tagged to the cluster.

The Planner receives a merged, deduplicated bundle with citations.

#### 5.2 Contextual Bandit for Tool/Strategy Selection

Let each arm be a `(tool, strategy)` pair. The context is a hashed feature vector derived from the task context (tenant, filetype, size bucket, SLA class, recent error class, time bucket). The reward is a weighted sum of success, negative latency, negative cost, and user satisfaction. The online learner (e.g., Thompson Sampling) returns a ranking and uncertainty; the Orchestrator logs propensities for unbiased offline evaluation. Periodically, logs are distilled into a supervised ranker used as a stable scoring function.

#### 5.3 Consolidation and Promotion

The Reflector generates candidate **lessons** with preconditions and actions. Candidates are deduplicated (cosine similarity > 0.92) and **promoted** to SOPs upon meeting thresholds: minimum sample size, statistically significant uplift versus baseline (e.g., p‑value < 0.05), and no critical incidents within a window. Promoted SOPs become first‑class choices for the Planner.

### 6. Implementation Details

- **Languages and Frameworks.** Services implemented in Java (Spring Boot). Resilience patterns (circuit breakers, retries, bulkheads) via Resilience4j.  
- **Tool Integrations.** Tool calls executed through a standardized MCP adapter layer with JSON schemas, idempotency keys, and structured error mapping.  
- **Data Plane.** Experience Log in Postgres/BigQuery; Knowledge Graph in Neo4j via Graphiti; Vector Store in Chroma with metadata filters; Episodic Diary in Letta/MemGPT; artifacts in object storage with short TTL.  
- **APIs.** gRPC/HTTP endpoints: `/orchestrate`, `/plan`, `/execute`, `/validate`, `/memory/retrieve`, `/policy/suggest`, `/policy/update`, `/sop/{id}`.  
- **Telemetry.** Step‑level logs include timestamps, latency, cost, token usage, error class; run‑level logs include success, artifacts, CSAT.  
- **Security and Compliance.** PII filtering before vectorization or diary writes; encryption at rest and in transit; role‑based access to SOP promotion; audit trails linking outputs to `(run_id, plan_id, sop_id)`.  
- **Governance.** Feature flags and A/B Router for controlled rollout of new SOPs/policies; auto‑rollback on regression alarms.

### 7. Evaluation and KPIs

- **Success Rate** per TaskCluster.  
- **Latency** (median and p95).  
- **Cost per Task**.  
- **SOP Coverage** (% of tasks resolved via promoted SOPs).  
- **Time‑to‑First‑Success** on novel clusters.  
- **Repeat Error Rate** by ErrorClass.  
- **User Satisfaction** (CSAT).  
- **Exploration Rate** (should decrease in mature clusters).

### 8. Advantages

- **Faster Convergence.** Bandit‑guided selection and SOP promotion reduce time‑to‑optimal behavior.  
- **Reduced Repeat Failures.** Error classes and preconditioned lessons minimize recurrence.  
- **Explainability.** SOPs and graph edges provide human‑readable rationale.  
- **Governed Evolution.** A/B gating and promotion criteria ensure stability under change.  
- **Auditable Provenance.** Every result is traceable to plan, tools, and data used.

### 9. Limitations and Mitigations

- **Credit Assignment Complexity.** Multi‑step runs confound attribution; mitigation via logged propensities, per‑step rewards, and off‑policy evaluation.  
- **Memory Bloat.** Addressed through salience gating, deduplication, and consolidation.  
- **Tool Drift.** Monitored through live health statistics and circuit breakers; Planner avoids degraded tools based on graph signals.  
- **Cold Start.** Bootstrapped with curated seed SOPs and higher exploration rates.

### 10. Industrial Applicability

Applicable to enterprise workflows requiring robust tool use: document ingestion, data extraction, customer support triage, financial operations, and MLOps pipelines, where reliability, cost, and latency are first‑class constraints.

### 11. Example Use Case (Bank Statement Ingestion)

For multi‑page bank statement PDFs, the system selects a chunking strategy and OCR tool based on file size and tenant, validates schema conformance, and logs outcomes. After repeated success with a specific configuration, the Reflector promotes an SOP that the Planner subsequently selects by default when preconditions match, reducing latency variance and failure rate.

### 12. Related Work and Distinction

Prior systems include memory‑augmented agents, RAG pipelines, tool‑use frameworks, and autonomous agents. Unlike prior art, the disclosed system (i) **triangulates retrieval** across three distinct memory substrates (episodic, graph, vector) with a unified retrieval bundle, (ii) **learns selection policies online** via contextual bandits with logged propensities and **distills** them offline into a stable ranker, (iii) **promotes SOPs** via statistically governed criteria (uplift, incidents, sample size) rather than ad‑hoc heuristics, and (iv) integrates **structured error classes** into the knowledge graph to drive preconditioned avoidance and fallback planning.

### 13. Glossary

- **TaskCluster:** A grouping of tasks with similar context features.  
- **Strategy:** A parameterized way of using a tool.  
- **SOP:** Standard Operating Procedure; a validated, reusable plan.  
- **ErrorClass:** Canonical category of tool failure.  
- **Retrieval Bundle:** Aggregated results from vector, graph, and diary memories.

---

## Key Claims (Non‑Limiting)

1. A system that retrieves planning context by **triangulating** across an episodic diary, a knowledge graph with performance statistics, and a vector store of consolidated lessons.  
2. A **Policy Service** implementing contextual bandits for online selection of `(tool, strategy)` arms and offline policy distillation into a stable ranker.  
3. A **Reflector** that promotes lessons to **SOPs** based on statistically significant uplift and incident checks, where SOPs are versioned and enforced by the Planner.  
4. An **Executor** that enforces resilience and emits structured telemetry enabling unbiased off‑policy evaluation.  
5. A governed **A/B Router** that safely introduces policy/SOP changes with automatic rollback on regression.

---

## Reference to Drawings

- **Figure 1:** System Architecture (services and data plane). *[Insert diagram here]*  
- **Figure 2:** Sequence Workflow (end‑to‑end lifecycle). *[Insert diagram here]*

