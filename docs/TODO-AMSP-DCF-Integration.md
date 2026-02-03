# AMSP-DCF Integration Playbook

**Version:** 1.0.1
**Status:** Planning
**Created:** 2026-02-03
**Last Updated:** 2026-02-03
**Authors:** Human + Claude Opus 4.5

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#part-i-current-state-analysis)
3. [Integration Gap Analysis](#part-ii-integration-gap-analysis)
4. [Blast Radius: Required DCF Modifications](#part-iii-blast-radius-required-dcf-modifications)
5. [Implementation Playbook](#part-iv-implementation-playbook)
6. [Verification & Testing](#part-v-verification--testing)
7. [References](#part-vi-references)

---

## Executive Summary

This document serves as the comprehensive playbook for integrating AMSP (Adaptive Model Selection Protocol) v3.0 with the DCF (Dynamic Capabilities Framework). It captures:

- **Weaknesses & Gaps**: 8 fundamental integration issues requiring resolution
- **Blast Radius**: 18 files to modify, 3 new files to create
- **Phased Plan**: 4-phase implementation from MVP to full optimization

### Key Metrics

| Metric | Value |
|--------|-------|
| JSON Schemas Affected | 6 (all require version bumps) |
| Python Tools Modified | 8 (4 Phase 1 + 4 Phase 2) |
| Agent Prompts Modified | 6 (all agents) |
| New Files Created | 3 |
| Implementation Phases | 4 (A through D) |

### Critical Finding

**No existing DCF components reference AMSP concepts.** Grep analysis confirms zero mentions of complexity tiers, model selection, FCS, or WCM in any prompts or tools. This means AMSP integration is an entirely **new capability addition**, not an enhancement to existing functionality.

---

# Part I: Current State Analysis

## 1.1 AMSP v3.0 Capabilities

AMSP provides a systematic framework for matching task complexity to model tiers:

| Component | Description | Status |
|-----------|-------------|--------|
| **WCM (Weighted Complexity Matrix)** | 7-dimension scoring system | ✅ Defined |
| **FCS (Final Complexity Score)** | Base WCS × Interaction Multipliers | ✅ Defined |
| **Tier Mapping** | FCS → Model Tier (0-3) | ✅ Capability-based |
| **LVP (Lightweight Validation Probe)** | 30-case stratified test set | ✅ Statistically valid |
| **Bootstrap Protocol** | New skill onboarding | ✅ Maturity levels defined |
| **Interaction Multipliers** | 21 dimension pairs analyzed | ✅ Complete |
| **Latency Constraints** | First-class requirement | ✅ 4 levels defined |

### WCM Dimensions (for reference)

| Dimension | Weight | Score Range | Description |
|-----------|--------|-------------|-------------|
| Horizon | 1.0 | 0-3 | Single-turn to multi-session planning |
| Context | 1.0 | 0-3 | Self-contained to cross-domain synthesis |
| Tooling | 1.0 | 0-3 | No tools to complex orchestration |
| Observability | 1.0 | 0-3 | Full transparency to opaque environments |
| Modality | 1.0 | 0-3 | Text-only to complex multimodal |
| Precision | 1.0 | 0-3 | Approximate to exact correctness |
| Adaptability | 1.0 | 0-3 | Stable to highly dynamic context |

### Tier Boundaries (Capability-Based)

| Tier | FCS Range | Capability Profile |
|------|-----------|-------------------|
| 0 | 0-12 | Single-turn, deterministic, no tools |
| 1 | 13-25 | Multi-turn, simple tools, moderate context |
| 2 | 26-50 | Complex reasoning, multi-tool, synthesis |
| 3 | 51+ | Novel domains, research-grade, maximum capability |

### Model-Tier Mapping with Pricing (as of February 2026)

| Tier | Example Models | Input ($/1M) | Output ($/1M) | Notes |
|------|----------------|--------------|---------------|-------|
| **0** | GPT-4o-mini | $0.15 | $0.60 | Best value for simple tasks |
| **0** | DeepSeek-V3 | $0.27 | $0.42 | Cache hits: $0.07 input |
| **0** | Gemini 3 Flash | $0.50 | $3.00 | 1M context, fast |
| **0-1** | Claude Haiku 4.5 | $1.00 | $5.00 | Good balance |
| **1** | Claude Sonnet 4 | $3.00 | $15.00 | Strong reasoning |
| **1-2** | GPT-4o | $2.50 | $10.00 | 128K context |
| **1-2** | Gemini 3 Pro | $2.00 | $12.00 | 2M context; $4/$18 >200K |
| **2** | Claude Sonnet 4.5 | $3.00 | $15.00 | Extended reasoning |
| **3** | GPT-5 | $1.25 | $10.00 | 400K context, best value frontier |
| **3** | Claude Opus 4.5 | $5.00 | $25.00 | Strongest reasoning |
| **3** | Gemini 3 Deep Think | $2.00 | $12.00 | Extended reasoning mode |

*Note: The 10-50× cost difference between tiers makes AMSP model selection economically critical. A task processed 10,000 times monthly could cost $15 with GPT-4o-mini or $500 with Claude Opus 4.5.*

## 1.2 DCF Current Architecture

DCF provides the execution framework for agentic workflows:

### Phase 1 (Workflow Execution)

| Component | Role | Model Selection? |
|-----------|------|------------------|
| **Planner** | Workflow compilation, skill discovery | ❌ No |
| **Worker** | Task execution, skill loading | ❌ No |
| **Reflector** | Post-workflow analysis | ❌ No |

### Phase 2 (Delegated Execution)

| Component | Role | Model Selection? |
|-----------|------|------------------|
| **Conductor** | Dynamic task delegation | ❌ No |
| **Companion** | Session-scoped execution | ❌ No |
| **Strategist** | Real-time optimization | ❌ No |

### Current Skill Manifest Schema (v2.0.0)

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "...",
  "skillName": "...",
  "skillVersion": "1.0.0",
  "permissions": { "egress": "none", "secrets": [] },
  "skillDirectives": "...",
  "requiredTools": [...],
  "requiredDataSources": [...]
}
```

**Note**: No `complexityProfile` field exists.

## 1.3 The Integration Gap

AMSP and DCF currently operate independently:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT STATE                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   AMSP v3.0                          DCF                                    │
│   ┌─────────────────┐               ┌─────────────────┐                     │
│   │ WCM Scoring     │               │ Planner Agent   │                     │
│   │ Tier Mapping    │   [NO LINK]   │ Worker Agents   │                     │
│   │ LVP Validation  │ ──────────────│ Control Plane   │                     │
│   │ Bootstrap       │               │ Skill Loading   │                     │
│   └─────────────────┘               └─────────────────┘                     │
│                                                                             │
│   Skills have NO complexity profiles                                        │
│   Agents have NO model selection logic                                      │
│   Control plane has NO tier tracking                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What's Missing

1. **Skill manifests** lack complexity metadata
2. **Tools** don't compute or use FCS
3. **Prompts** don't guide model selection
4. **Control plane** doesn't track model choices
5. **Data plane** doesn't capture inference metrics
6. **Graphiti** doesn't store complexity profiles
7. **Advisors** (Reflector/Strategist) don't analyze model efficiency

---

# Part II: Integration Gap Analysis

This section documents 8 fundamental weaknesses that must be addressed for proper AMSP-DCF integration.

## Gap 1: Decomposition Decision Boundary Paradox

**Priority:** HIGH
**Affects:** Phase 1 workflow decomposition, Planner agent
**Category:** Algorithmic

### Problem

The AMSP decomposition logic creates a circular dependency:

```
┌─────────────────────────────────────────────────────────────────┐
│ AMSP Rule: "If FCS 26-50, decompose if ≥30% of subtasks         │
│             can be handled by Tier 0-1"                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────────┐                                          │
│   │ Should I         │                                          │
│   │ decompose?       │                                          │
│   └────────┬─────────┘                                          │
│            │                                                    │
│            ▼                                                    │
│   ┌──────────────────┐       ┌──────────────────┐               │
│   │ Need subtask     │──────▶│ Must decompose   │               │
│   │ complexities     │       │ first to assess  │               │
│   └──────────────────┘       └────────┬─────────┘               │
│            ▲                          │                         │
│            │                          │                         │
│            └──────────────────────────┘                         │
│                    CIRCULAR DEPENDENCY                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Impact

- Speculative decomposition → assessment → decision loops
- Computational overhead for every Tier 2 task
- No heuristics for "decomposition likelihood" from holistic features

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Add decomposition cache | Control Plane (Redis) | Medium |
| Implement quick-probe approach | `validate_workflow.py` | Medium |
| Add decomposition heuristics | Planner prompt | Low |

### Proposed Solutions

- [ ] Develop heuristics predicting decomposition benefit from holistic FCS features
- [ ] Cache decomposition patterns for similar task types in Graphiti
- [ ] Implement "quick probe": assess 2-3 representative subtasks before full decomposition
- [ ] Train classifier on historical (task, decomposition, cost_savings) data

---

## Gap 2: Missing Coordination Complexity Dimension

**Priority:** HIGH
**Affects:** WCM scoring for decomposed workflows
**Category:** Scoring Model

### Problem

The 7-dimension WCM scores individual task complexity but ignores coordination overhead between decomposed steps:

```
Example: Two workflows with identical individual task FCS

Workflow A (4 steps, tight coupling):
┌────┐    ┌────┐    ┌────┐    ┌────┐
│ S1 │───▶│ S2 │───▶│ S3 │───▶│ S4 │
└────┘    └────┘    └────┘    └────┘
   │         │         │         │
   └─────────┴─────────┴─────────┘
         Shared state, transactions

Workflow B (6 steps, loose coupling):
┌────┐    ┌────┐    ┌────┐    ┌────┐    ┌────┐    ┌────┐
│ S1 │───▶│ S2 │───▶│ S3 │───▶│ S4 │───▶│ S5 │───▶│ S6 │
└────┘    └────┘    └────┘    └────┘    └────┘    └────┘
              Simple JSON handoffs, no shared state

Workflow A may be HARDER despite fewer steps!
```

### Current Gap

AMSP estimates ~$0.05 + 200-500ms per handoff, but actual overhead depends on:
- Data serialization/deserialization complexity
- State management requirements
- Error propagation handling
- Compensating transactions for partial failures

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Add workflow-level complexity assessment | New tool | High |
| Track coordination metrics | Data Plane schema | Medium |
| Include in cost-benefit analysis | Planner prompt | Medium |

### Proposed Solutions

- [ ] Add "Coordination Complexity" as 8th WCM dimension for workflow-level assessment
- [ ] Define scoring rubric:

| Score | Description | Examples |
|-------|-------------|----------|
| 0 | No inter-step dependencies, stateless handoffs | Independent parallel tasks |
| 1 | Simple JSON data passing, linear flow | Sequential file processing |
| 2 | Complex state objects, branching dependencies | Conditional workflows |
| 3 | Tight coupling, shared resources, transactions | Multi-step database operations |

- [ ] Model overhead as function of data volume and coupling tightness
- [ ] Include coordination cost in decomposition cost-benefit analysis

---

## Gap 3: Error Propagation and Rollback Semantics

**Priority:** HIGH
**Affects:** Workflow reliability, fault tolerance
**Category:** Reliability

### Problem

AMSP mentions "better failure isolation" as a decomposition benefit but DCF lacks specification for:

```
Step 1 (Tier 0): Completed successfully ✓
Step 2 (Tier 2): Failed after partial work ✗
    │
    ▼
┌─────────────────────────────────────────────┐
│ UNDEFINED BEHAVIOR                          │
│                                             │
│ • How is partial state cleaned up?          │
│ • How is workflow restarted?                │
│ • Is Step 1 re-executed or skipped?         │
│ • Who owns compensation logic?              │
└─────────────────────────────────────────────┘
```

### Current State

- Redis control plane provides atomicity at step level (via leases)
- Cross-step transaction semantics are undefined
- No saga pattern or compensation handlers

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Define state management patterns | Documentation | Medium |
| Add checkpoint/resume capability | Control Plane tools | High |
| Add `rollback_action` field | ASL schema | Medium |
| Idempotency requirements | Skill manifest schema | Low |

### Proposed Solutions

- [ ] Define explicit state management patterns (saga pattern, compensation handlers)
- [ ] Add checkpoint/resume capability for long workflows
- [ ] Specify idempotency requirements in skill manifests:
  ```json
  {
    "idempotency": {
      "safe_to_retry": true,
      "deduplication_key": "$.input.request_id"
    }
  }
  ```
- [ ] Implement compensation handler registration in workflow definition
- [ ] Add `rollback_action` field to AgentBinding specification

---

## Gap 4: Cross-Step Transaction Semantics

**Priority:** MEDIUM
**Affects:** Data consistency, workflow correctness
**Category:** Data Integrity

### Problem

No formal specification for transactional guarantees across workflow steps:

| Question | Current Answer |
|----------|----------------|
| What isolation level do parallel steps have? | Undefined |
| How are read-after-write dependencies enforced? | Implicit via DAG |
| What happens if two steps write to same output path? | Last write wins (race) |
| Can a step read uncommitted output from another? | Yes (no isolation) |

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Define isolation levels | Documentation + schema | Medium |
| Explicit dependency declarations | ASL schema | Medium |
| Conflict detection | Control Plane tools | High |

### Proposed Solutions

- [ ] Define transaction isolation levels for workflows:
  - **Read-Uncommitted**: Default, maximum parallelism
  - **Read-Committed**: Wait for upstream completion
  - **Serializable**: Full ordering guarantees
- [ ] Add explicit dependency declarations in ASL workflow definition
- [ ] Implement conflict detection in control plane
- [ ] Support optimistic vs pessimistic locking modes

---

## Gap 5: Multi-Agent Complexity Gap (Phase 2)

**Priority:** MEDIUM
**Affects:** Conductor/Companion patterns, Phase 2 DCF+
**Category:** Scoring Model

### Problem

AMSP's WCM scores "Tooling" complexity but not "Agent Coordination" complexity:

```
Conductor delegating to 5 Companions:

┌───────────────────────────────────────────────────────────────┐
│                       CONDUCTOR                               │
│  • Which Companion?          (decision complexity)            │
│  • Which skill set?          (capability matching)            │
│  • How to merge results?     (synthesis overhead)             │
│  • Handle conflicts?         (coordination density)           │
└───────────────────────────────────────────────────────────────┘
        │         │         │         │         │
        ▼         ▼         ▼         ▼         ▼
    ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐
    │ C1  │   │ C2  │   │ C3  │   │ C4  │   │ C5  │
    └─────┘   └─────┘   └─────┘   └─────┘   └─────┘

Current WCM scores each Companion task independently.
Conductor overhead is NOT captured!
```

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Extend WCM for Phase 2 | AMSP document | Medium |
| Add session complexity assessment | Conductor tools | Medium |
| Separate Conductor vs Companion profiles | Skill manifests | Medium |

### Proposed Solutions

- [ ] Extend WCM for Phase 2 with new dimensions:
  - **Delegation Depth** (0-3): How many levels of agent delegation?
  - **Coordination Density** (0-3): How much inter-agent communication required?
- [ ] Define separate complexity profiles for Conductor-level orchestration vs Companion-level execution
- [ ] Add `agent_coordination_overhead` field to session complexity assessment

---

## Gap 6: Graphiti Query Scalability

**Priority:** MEDIUM
**Affects:** Knowledge graph performance, runtime decisions
**Category:** Performance

### Problem

AMSP documentation shows Cypher queries for skill performance analysis without addressing scale:

```
Scale calculation (90-day retention):
  500 analyses/month × 4 steps × 90 days = 180,000 execution nodes per skill

Query pattern:
  MATCH (s:Skill)-[:EXECUTED_IN]->(e:Execution)
  WHERE e.timestamp > datetime() - duration('P90D')
  RETURN s.id, avg(e.success_rate), avg(e.latency_ms)

At scale: O(n) traversal per query → latency impact on runtime decisions
```

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Materialized views | Graphiti schema | High |
| Caching layer | New component | Medium |
| Time-partitioned subgraphs | Graphiti architecture | High |

### Proposed Solutions

- [ ] Define materialized views or precomputed aggregates for common queries
- [ ] Specify batch vs real-time query patterns
- [ ] Consider time-partitioned subgraphs (hot/warm/cold data)
- [ ] Add query latency budgets for runtime complexity lookups (<50ms)
- [ ] Implement caching layer for frequently-accessed skill complexity profiles

---

## Gap 7: Reflector/Strategist Feedback Paths

**Priority:** MEDIUM
**Affects:** Continuous improvement, complexity recalibration
**Category:** Feedback Loops

### Problem

Phase 1 has Reflector (post-workflow), Phase 2 has Strategist (real-time), but AMSP integration is undefined:

```
Current state:
┌──────────────┐                    ┌──────────────┐
│  Reflector   │                    │  Strategist  │
│              │                    │              │
│  Analyzes    │                    │  Observes    │
│  workflow    │   [NO FEEDBACK]    │  session     │
│  outcomes    │ ──────────────────▶│  activity    │
│              │                    │              │
└──────────────┘                    └──────────────┘
       │                                   │
       ▼                                   ▼
   Guidelines                          Guidelines
   (workflow)                          (session)
       │                                   │
       └───────────────┬───────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │ Skill Complexity│
              │ Profiles        │
              │                 │
              │ NOT UPDATED!    │
              └────────────────┘
```

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Complexity feedback event type | Reflector/Strategist schemas | Medium |
| Recalibration trigger | `finalize_workflow.py` | Medium |
| Dynamic tier escalation | `delegate_task.py` | Medium |

### Proposed Solutions

- [ ] Define explicit feedback paths from Reflector → skill complexity recalibration
- [ ] Enable Strategist to trigger dynamic tier escalation mid-session
- [ ] Create "advisor-influenced complexity adjustment" protocol
- [ ] Add `complexity_feedback` event type to Reflector/Strategist output schemas:
  ```json
  {
    "type": "complexity_feedback",
    "skill_id": "skill.research.web@0.1.0",
    "observed_tier": 2,
    "expected_tier": 1,
    "success": false,
    "recommendation": "escalate_minimum_tier"
  }
  ```
- [ ] Implement automatic `validated_models` updates based on advisor insights

---

## Gap 8: Coordination Overhead Modeling

**Priority:** LOW
**Affects:** Cost accuracy, decomposition decisions
**Category:** Cost Model

### Problem

The fixed estimate of ~$0.05 + 200-500ms per handoff is oversimplified:

| Factor | Impact | Current Model |
|--------|--------|---------------|
| Data payload size | 10KB vs 10MB → 10x difference | Ignored |
| Serialization format | JSON vs Protobuf → 5x difference | Ignored |
| Network latency | Local vs distributed → 100x difference | Ignored |
| Redis load | Light vs heavy → 3x difference | Ignored |
| Worker state | Cold vs warm → 2x difference | Ignored |

### Required DCF Changes

| Change | Component | Effort |
|--------|-----------|--------|
| Parametric overhead model | Cost calculation | Medium |
| Empirical data collection | Metrics pipeline | Medium |

### Proposed Solutions

- [ ] Develop parametric overhead model:
  ```
  overhead = base_cost
           + (data_size × serialization_factor)
           + network_latency
           + cold_start_penalty
  ```
- [ ] Collect empirical data on actual coordination costs
- [ ] Add overhead estimation to decomposition cost-benefit calculator
- [ ] Consider amortization for workflows with many executions

---

# Part III: Blast Radius (Required DCF Modifications)

This section details every file that must be modified or created to integrate AMSP with DCF.

## 3.1 Component Impact Matrix

| Component | Files Affected | Impact Level | Breaking Change? |
|-----------|---------------|--------------|------------------|
| **JSON Schemas** | 6 | HIGH | Version bumps only |
| **Phase 1 Tools** | 4 | HIGH | Backward compatible |
| **Phase 2 Tools** | 4 | HIGH | Backward compatible |
| **Agent Prompts** | 6 | HIGH | Additive |
| **Redis Control Plane** | N/A (schema) | MEDIUM | Additive fields |
| **Graphiti** | 2 new entities | MEDIUM | Additive |

## 3.2 JSON Schema Modifications (6 files)

### 3.2.1 `skill_manifest_schema_v2.0.0.json` → v2.1.0

**Path:** `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json`

**New fields to add:**

```json
{
  "complexityProfile": {
    "type": "object",
    "description": "AMSP complexity assessment for this skill",
    "properties": {
      "baseWCS": {
        "type": "integer",
        "minimum": 0,
        "maximum": 21,
        "description": "Base Weighted Complexity Score (sum of 7 dimensions)"
      },
      "dimensionScores": {
        "type": "object",
        "properties": {
          "horizon": { "type": "integer", "minimum": 0, "maximum": 3 },
          "context": { "type": "integer", "minimum": 0, "maximum": 3 },
          "tooling": { "type": "integer", "minimum": 0, "maximum": 3 },
          "observability": { "type": "integer", "minimum": 0, "maximum": 3 },
          "modality": { "type": "integer", "minimum": 0, "maximum": 3 },
          "precision": { "type": "integer", "minimum": 0, "maximum": 3 },
          "adaptability": { "type": "integer", "minimum": 0, "maximum": 3 }
        },
        "required": ["horizon", "context", "tooling", "observability", "modality", "precision", "adaptability"]
      },
      "maturityLevel": {
        "type": "string",
        "enum": ["provisional", "emerging", "validated", "stable"],
        "description": "Bootstrap Protocol maturity level"
      },
      "validatedModels": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Models confirmed to work for this skill"
      },
      "sampleSize": {
        "type": "integer",
        "minimum": 0,
        "description": "Number of executions used for calibration"
      },
      "lastCalibrated": {
        "type": "string",
        "format": "date-time"
      }
    }
  }
}
```

### 3.2.2 `control-plane-state-1.0.0.json` → v1.1.0

**Path:** `dcf_mcp/schemas/control-plane-state-1.0.0.json`

**New fields to add:**

```json
{
  "model_selection": {
    "type": "object",
    "description": "AMSP model selection for this state",
    "properties": {
      "computed_fcs": {
        "type": "number",
        "description": "Final Complexity Score at selection time"
      },
      "selected_tier": {
        "type": "integer",
        "enum": [0, 1, 2, 3]
      },
      "selected_model": {
        "type": "string",
        "description": "Model ID selected for execution"
      },
      "selection_reason": {
        "type": "string",
        "description": "Human-readable explanation"
      },
      "latency_constraint": {
        "type": "string",
        "enum": ["critical", "standard", "relaxed", "batch"]
      },
      "escalated": {
        "type": "boolean",
        "default": false,
        "description": "Whether tier was escalated during execution"
      }
    }
  }
}
```

### 3.2.3 `control-plane-meta-1.0.0.json` → v1.1.0

**Path:** `dcf_mcp/schemas/control-plane-meta-1.0.0.json`

**New fields to add:**

```json
{
  "workflow_complexity": {
    "type": "object",
    "description": "Aggregate complexity assessment for workflow",
    "properties": {
      "aggregate_fcs": {
        "type": "number",
        "description": "Weighted average FCS across states"
      },
      "dominant_tier": {
        "type": "integer",
        "description": "Most common tier in workflow"
      },
      "tier_distribution": {
        "type": "object",
        "description": "Count of states per tier",
        "additionalProperties": { "type": "integer" }
      },
      "estimated_cost_usd": {
        "type": "number",
        "description": "Pre-execution cost estimate"
      }
    }
  }
}
```

### 3.2.4 `data-plane-output-1.0.0.json` → v1.1.0

**Path:** `dcf_mcp/schemas/data-plane-output-1.0.0.json`

**Extended `metrics` object:**

```json
{
  "metrics": {
    "type": "object",
    "properties": {
      "latency_ms": { "type": "number", "minimum": 0 },
      "model_used": {
        "type": "string",
        "description": "Actual model that executed the task"
      },
      "tier_used": {
        "type": "integer",
        "description": "Actual tier (may differ from selected if escalated)"
      },
      "inference_cost_usd": {
        "type": "number",
        "description": "Actual inference cost"
      },
      "tokens_in": { "type": "integer" },
      "tokens_out": { "type": "integer" },
      "escalation_reason": {
        "type": ["string", "null"],
        "description": "If tier was escalated, why"
      }
    }
  }
}
```

### 3.2.5 `letta_asl_workflow_schema_v2.2.0.json` → v2.3.0

**Path:** `dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json`

**New fields in `AgentBinding`:**

```json
{
  "AgentBinding": {
    "model_selection_policy": {
      "type": "object",
      "description": "Override default AMSP behavior for this binding",
      "properties": {
        "override_tier": {
          "type": "integer",
          "enum": [0, 1, 2, 3],
          "description": "Force specific tier (skip FCS calculation)"
        },
        "latency_requirement": {
          "type": "string",
          "enum": ["critical", "standard", "relaxed", "batch"],
          "default": "standard"
        },
        "allow_tier_escalation": {
          "type": "boolean",
          "default": true,
          "description": "Allow dynamic escalation if task complexity exceeds expectation"
        },
        "cost_ceiling_usd": {
          "type": "number",
          "description": "Maximum acceptable inference cost"
        }
      }
    }
  }
}
```

### 3.2.6 New Schema: `amsp-complexity-profile-1.0.0.json`

**Path:** `dcf_mcp/schemas/amsp-complexity-profile-1.0.0.json`

**Purpose:** Standalone schema for skill complexity profiles (can be referenced by skill manifests)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/amsp-complexity-profile-1.0.0.json",
  "title": "AMSP Complexity Profile v1.0.0",
  "type": "object",
  "properties": {
    "skill_id": { "type": "string" },
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "base_wcs": { "type": "integer", "minimum": 0, "maximum": 21 },
    "dimension_scores": {
      "type": "object",
      "properties": {
        "horizon": { "type": "integer", "minimum": 0, "maximum": 3 },
        "context": { "type": "integer", "minimum": 0, "maximum": 3 },
        "tooling": { "type": "integer", "minimum": 0, "maximum": 3 },
        "observability": { "type": "integer", "minimum": 0, "maximum": 3 },
        "modality": { "type": "integer", "minimum": 0, "maximum": 3 },
        "precision": { "type": "integer", "minimum": 0, "maximum": 3 },
        "adaptability": { "type": "integer", "minimum": 0, "maximum": 3 }
      },
      "required": ["horizon", "context", "tooling", "observability", "modality", "precision", "adaptability"]
    },
    "interaction_multipliers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "pair": { "type": "string", "description": "e.g., 'horizon+context'" },
          "multiplier": { "type": "number" }
        }
      }
    },
    "final_fcs": { "type": "number" },
    "recommended_tier": { "type": "integer", "enum": [0, 1, 2, 3] },
    "maturity_level": { "type": "string", "enum": ["provisional", "emerging", "validated", "stable"] },
    "validated_models": {
      "type": "array",
      "items": { "type": "string" }
    },
    "success_rate_by_tier": {
      "type": "object",
      "additionalProperties": { "type": "number" }
    },
    "sample_size": { "type": "integer" },
    "confidence_interval": {
      "type": "object",
      "properties": {
        "lower": { "type": "number" },
        "upper": { "type": "number" }
      }
    },
    "last_calibrated": { "type": "string", "format": "date-time" },
    "calibration_notes": { "type": "string" }
  },
  "required": ["skill_id", "version", "base_wcs", "dimension_scores", "maturity_level"]
}
```

---

## 3.3 Python Tool Modifications (8 files)

### Phase 1 Tools (4 files)

#### 3.3.1 `create_worker_agents.py`

**Path:** `dcf_mcp/tools/dcf/create_worker_agents.py`

**Changes Required:**

1. Add `compute_skill_complexity()` call before agent creation
2. Select model tier based on FCS calculation
3. Pass model selection to Letta agent creation API
4. Record selection rationale in control plane

**New Parameters:**

```python
def create_worker_agents(
    workflow_json: str,
    imports_base_dir: str = None,
    agent_name_prefix: str = None,
    agent_name_suffix: str = ".af",
    default_tags_json: str = None,
    skip_if_exists: bool = True,
    # NEW PARAMETERS
    model_selection_policy: str = None,  # JSON: {"override_tier": 2, "latency_requirement": "critical"}
    latency_requirement: str = "standard",  # Default for all states
    enable_model_selection: bool = True  # Feature flag for gradual rollout
) -> Dict[str, Any]:
```

**New Return Fields:**

```python
{
    "status": "ok",
    "workflow_id": "...",
    "agents_map": {...},
    "created": [...],
    # NEW FIELDS
    "model_selections": {
        "StateA": {
            "computed_fcs": 16.1,
            "selected_tier": 1,
            "selected_model": "claude-haiku-4-5",
            "latency_constraint": "standard"
        }
    },
    "aggregate_complexity": {
        "dominant_tier": 1,
        "estimated_cost_usd": 0.15
    }
}
```

#### 3.3.2 `validate_workflow.py`

**Path:** `dcf_mcp/tools/dcf/validate_workflow.py`

**Changes Required:**

1. Validate `model_selection_policy` in AgentBinding (if present)
2. Validate skill complexity profiles exist for referenced skills
3. Add warning (not error) if skills have `provisional` maturity level
4. Add new exit code for complexity validation issues

**New Exit Code:**

| Code | Meaning |
|------|---------|
| 4 | Complexity validation issues (warnings, not blocking) |

#### 3.3.3 `finalize_workflow.py`

**Path:** `dcf_mcp/tools/dcf/finalize_workflow.py`

**Changes Required:**

1. Aggregate model usage metrics from all states
2. Compute total actual inference cost
3. Compare estimated vs actual costs
4. Trigger complexity profile recalibration if significant deviation
5. Write model selection audit data to data plane

**New Return Fields:**

```python
{
    "status": "ok",
    "workflow_id": "...",
    "workflow_status": "succeeded",
    # NEW FIELDS
    "model_usage_summary": {
        "tier_distribution": {"0": 2, "1": 3, "2": 1},
        "total_inference_cost_usd": 0.18,
        "estimated_vs_actual": {
            "estimated": 0.15,
            "actual": 0.18,
            "deviation_pct": 20.0
        },
        "escalations": [
            {"state": "StateC", "from_tier": 1, "to_tier": 2, "reason": "context_overflow"}
        ]
    },
    "recalibration_triggered": false
}
```

#### 3.3.4 New Tool: `compute_task_complexity.py`

**Path:** `dcf_mcp/tools/dcf/compute_task_complexity.py`

**Purpose:** Core AMSP calculation engine

```python
def compute_task_complexity(
    skills_json: str,           # JSON array of skill manifest IDs or full manifests
    context_features: str = None,  # JSON: optional context overrides
    latency_requirement: str = "standard"
) -> Dict[str, Any]:
    """
    Compute AMSP complexity score for a task based on required skills.

    Args:
        skills_json: JSON array of skill IDs (e.g., ["skill.research.web@0.1.0"])
                     or full skill manifest objects
        context_features: Optional JSON with context overrides:
                         {"horizon": 3, "context": 2}  # Override specific dimensions
        latency_requirement: "critical" | "standard" | "relaxed" | "batch"

    Returns:
        {
            "status": "ok",
            "error": null,
            "base_wcs": 14,
            "dimension_breakdown": {
                "horizon": 2,
                "context": 2,
                "tooling": 3,
                "observability": 2,
                "modality": 1,
                "precision": 2,
                "adaptability": 2
            },
            "interaction_multipliers": [
                {"pair": "tooling+context", "multiplier": 1.15, "reason": "High Tooling + High Context"}
            ],
            "total_multiplier": 1.15,
            "final_fcs": 16.1,
            "confidence_interval": {"lower": 14.2, "upper": 18.0},
            "recommended_tier": 1,
            "tier_reasoning": "FCS 16.1 falls in Tier 1 range (13-25)",
            "recommended_model": "claude-haiku-4-5",
            "latency_adjusted_tier": 1,  # May differ if latency_requirement is "critical"
            "maturity_levels": {
                "skill.research.web@0.1.0": "validated"
            },
            "warnings": []
        }
    """
```

### Phase 2 Tools (4 files)

#### 3.3.5 `delegate_task.py`

**Path:** `dcf_mcp/tools/dcf_plus/delegate_task.py`

**Changes Required:**

1. Add `compute_task_complexity()` call before delegation
2. Pass model selection to Companion via delegation message
3. Record selection in session activity log
4. Support latency requirement override

**New Parameters:**

```python
def delegate_task(
    companion_id: str,
    task_description: str,
    skills_required: list,
    task_context: str = None,
    priority: str = "normal",
    # NEW PARAMETERS
    latency_requirement: str = "standard",
    tier_override: int = None,
    cost_ceiling_usd: float = None
) -> Dict[str, Any]:
```

#### 3.3.6 `create_companion.py`

**Path:** `dcf_mcp/tools/dcf_plus/create_companion.py`

**Changes Required:**

1. Accept default model tier for session
2. Configure Companion with appropriate model
3. Record model selection rationale in session context

**New Parameters:**

```python
def create_companion(
    session_id: str,
    companion_name: str = None,
    specialization: str = None,
    # NEW PARAMETERS
    default_tier: int = None,  # Default tier for this Companion's tasks
    latency_profile: str = "standard"
) -> Dict[str, Any]:
```

#### 3.3.7 `trigger_strategist_analysis.py`

**Path:** `dcf_mcp/tools/dcf_plus/trigger_strategist_analysis.py`

**Changes Required:**

1. Include model selection patterns in analysis payload
2. Pass cost and latency metrics for Strategist review
3. Add complexity profile accuracy metrics

**New Fields in Analysis Payload:**

```json
{
  "analysis_event": {
    "session_id": "...",
    "trigger_reason": "periodic",
    "model_selection_summary": {
      "tier_distribution": {"1": 5, "2": 2},
      "total_cost_usd": 0.25,
      "avg_latency_ms": 1500,
      "escalation_rate": 0.15,
      "accuracy_metrics": {
        "predicted_vs_actual_tier_match": 0.85
      }
    }
  }
}
```

#### 3.3.8 `update_conductor_guidelines.py`

**Path:** `dcf_mcp/tools/dcf_plus/update_conductor_guidelines.py`

**Changes Required:**

1. Add model selection recommendations schema
2. Support tier preference guidelines from Strategist

**New Guideline Types:**

```json
{
  "model_selection_guidelines": {
    "skill_preferences": {
      "skill.research.web": {
        "min_tier": 1,
        "reason": "Observed 40% failure rate at Tier 0"
      }
    },
    "session_cost_budget_usd": 1.00,
    "prefer_latency_over_cost": false,
    "escalation_policy": "aggressive"  // "conservative" | "aggressive" | "default"
  }
}
```

---

## 3.4 Agent Prompt Modifications (6 files)

**Critical Context:** All prompts currently have ZERO references to complexity, tiers, model selection, FCS, or WCM. These are entirely new sections.

### 3.4.1 `Planner_final.txt` (Phase 1)

**Path:** `prompts/dcf/Planner_final.txt`

**New Section: "Model Selection"**

```markdown
---

## Model Selection

After assigning skills to workflow states, compute the optimal model tier for each state.

### Step 1: Compute Complexity

For each Task state, call:
```
compute_task_complexity(
    skills_json=<skills for this state>,
    latency_requirement=<from user requirements>
)
```

### Step 2: Review Recommendations

Present model selection summary to user:
| State | Skills | FCS | Tier | Model | Est. Cost |
|-------|--------|-----|------|-------|-----------|
| StateA | [research.web] | 16.1 | 1 | haiku | $0.02 |

### Step 3: Allow Overrides

User may override tier selection:
- "Use Tier 2 for StateB" → Set `override_tier: 2` in AgentBinding
- "This is time-sensitive" → Set `latency_requirement: critical`

### Step 4: Record in Workflow

Add `model_selection_policy` to AgentBinding:
```json
{
  "AgentBinding": {
    "agent_template_ref": { "name": "worker" },
    "skills": ["skill://research.web@0.1.0"],
    "model_selection_policy": {
      "latency_requirement": "standard",
      "allow_tier_escalation": true
    }
  }
}
```

### Maturity Warnings

If any skill has `maturity_level: provisional`:
- Warn user: "Skill X has provisional complexity profile (N samples). Results may vary."
- Recommend validation run before production use
```

### 3.4.2 `Worker_final.txt` (Phase 1)

**Path:** `prompts/dcf/Worker_final.txt`

**New Section: "Model Awareness"**

```markdown
---

## Model Awareness

You are executing with a specific model tier selected by AMSP.

### Your Assignment

Check control plane for your model selection:
- `selected_tier`: Your assigned capability level
- `selected_model`: The specific model you're running as
- `allow_tier_escalation`: Whether you can request upgrade

### Execution Metrics

After completing your task, report metrics in output:
```json
{
  "ok": true,
  "metrics": {
    "tokens_in": 1500,
    "tokens_out": 800,
    "latency_ms": 1200,
    "model_used": "claude-haiku-4-5",
    "tier_used": 1
  }
}
```

### Tier Escalation

If task complexity exceeds your capability:
1. Recognize signs: repeated failures, context overflow, reasoning loops
2. If `allow_tier_escalation: true`, request escalation:
   - Set `escalated: true` in state update
   - Document reason: "context_overflow" | "reasoning_complexity" | "tool_failure"
3. Planner will handle re-execution at higher tier
```

### 3.4.3 `Reflector_final.txt` (Phase 1)

**Path:** `prompts/dcf/Reflector_final.txt`

**New Section: "Model Selection Analysis"**

```markdown
---

## Model Selection Analysis

Analyze model selection efficiency across the workflow.

### Metrics to Examine

From workflow execution data:
- `tier_distribution`: How many states at each tier?
- `escalation_rate`: What % of states needed tier upgrade?
- `estimated_vs_actual_cost`: Was cost prediction accurate?
- `success_rate_by_tier`: Did lower tiers fail more often?

### Analysis Questions

1. **Over-provisioning**: Were any states assigned Tier 2 that succeeded trivially?
   - Sign: High success rate, low token usage, fast completion
   - Recommendation: Consider Tier 1 for similar tasks

2. **Under-provisioning**: Did Tier 0/1 states fail or escalate frequently?
   - Sign: Escalation rate > 20%
   - Recommendation: Increase minimum tier for affected skills

3. **Complexity Profile Accuracy**: Did FCS predictions match outcomes?
   - Compare predicted tier vs actual needed tier
   - Flag skills with >30% mismatch for recalibration

### Output Guidelines

Add to `reflector_guidelines` block:
```json
{
  "model_selection_insights": {
    "skill_adjustments": [
      {
        "skill": "skill.research.web@0.1.0",
        "current_fcs": 16.1,
        "observed_behavior": "escalated 40% of time",
        "recommendation": "increase_base_wcs",
        "suggested_wcs": 18
      }
    ],
    "cost_optimization": {
      "potential_savings": "$0.05/workflow",
      "action": "downgrade_stateless_tasks_to_tier_0"
    }
  }
}
```
```

### 3.4.4 `Conductor.md` (Phase 2)

**Path:** `prompts/dcf+/Conductor.md`

**New Section: "Dynamic Model Selection"**

```markdown
---

## Dynamic Model Selection

Select optimal model tier at each task delegation.

### Pre-Delegation Complexity Check

Before calling `delegate_task`, compute complexity:
```
complexity = compute_task_complexity(
    skills_json=<skills_required>,
    latency_requirement=<based on user urgency>
)
```

### Apply Strategist Guidelines

Check `strategist_guidelines` block for model selection advice:
- `skill_preferences`: Minimum tiers for specific skills
- `session_cost_budget_usd`: Stay within budget
- `escalation_policy`: How aggressively to upgrade tiers

### Delegation with Model Selection

```
delegate_task(
    companion_id=<selected companion>,
    task_description=<task>,
    skills_required=<skills>,
    latency_requirement="standard",  # or "critical" for urgent
    tier_override=None  # Only if Strategist recommends override
)
```

### Real-Time Tier Escalation

If Companion reports task too complex:
1. Receive escalation signal in result
2. Create new Companion at higher tier (or use existing high-tier Companion)
3. Re-delegate task
4. Update Strategist with escalation event

### Cost Tracking

Track cumulative session cost:
- Sum `inference_cost_usd` from all Companion results
- Alert user if approaching budget limit
- Consider tier downgrade for remaining tasks if over budget
```

### 3.4.5 `Companion.md` (Phase 2)

**Path:** `prompts/dcf+/Companion.md`

**New Section: "Model Awareness"**

```markdown
---

## Model Awareness

You are a session-scoped Companion executing at a specific model tier.

### Your Configuration

From your delegation message:
- `assigned_tier`: Your capability level for this task
- `latency_requirement`: Expected response time class

### Execution Reporting

Always include metrics in your task result:
```json
{
  "task_id": "...",
  "status": "completed",
  "result": {...},
  "metrics": {
    "tokens_in": 1200,
    "tokens_out": 600,
    "latency_ms": 900,
    "model_used": "claude-haiku-4-5",
    "tier_used": 1
  }
}
```

### Signaling Complexity Issues

If task exceeds your capability:
1. Attempt execution (don't pre-emptively fail)
2. If struggling: context overflow, repeated errors, reasoning loops
3. Return with escalation signal:
```json
{
  "status": "needs_escalation",
  "escalation_reason": "context_overflow",
  "partial_result": {...}
}
```

Conductor will handle re-delegation at higher tier.
```

### 3.4.6 `Strategist.md` (Phase 2)

**Path:** `prompts/dcf+/Strategist.md`

**New Section: "Model Selection Optimization"**

```markdown
---

## Model Selection Optimization

Analyze and optimize model selection patterns across the session.

### Analysis Triggers

When `trigger_strategist_analysis` is called, examine:
1. `model_selection_summary` in analysis payload
2. Historical patterns from previous sessions (via Graphiti)

### Key Metrics

| Metric | Healthy Range | Action if Outside |
|--------|---------------|-------------------|
| Escalation rate | <15% | Recommend higher base tiers |
| Tier 0 failure rate | <10% | Flag skills for recalibration |
| Cost vs estimate | ±20% | Adjust FCS for affected skills |
| Latency violations | <5% | Recommend faster tiers |

### Optimization Recommendations

Publish to `strategist_guidelines` block:

```json
{
  "model_selection_guidelines": {
    "skill_preferences": {
      "skill.analysis.financial": {
        "min_tier": 2,
        "reason": "Observed 60% escalation rate at Tier 1"
      }
    },
    "session_recommendations": {
      "remaining_budget_usd": 0.75,
      "prefer_cost_optimization": true,
      "suggested_tier_ceiling": 2
    },
    "complexity_recalibration": [
      {
        "skill": "skill.research.web@0.1.0",
        "action": "increase_wcs",
        "evidence": "40% escalation rate over 20 tasks"
      }
    ]
  }
}
```

### Graphiti Persistence

Write significant patterns to knowledge graph:
```cypher
CREATE (p:ModelSelectionPattern {
  session_id: $session_id,
  skill_id: $skill_id,
  observed_tier: $tier,
  success_rate: $rate,
  sample_size: $n,
  timestamp: datetime()
})
```
```

---

## 3.5 Redis Control Plane Extensions

### 3.5.1 New Key Pattern: Model Selection Audit

**Key:** `cp:wf:{workflow_id}:model_selection`

**Purpose:** Centralized record of all model selection decisions for a workflow

```json
{
  "computed_at": "2026-02-03T10:30:00Z",
  "computation_method": "amsp_v3",
  "states": {
    "StateA": {
      "skills": ["skill.research.web@0.1.0"],
      "fcs": 16.1,
      "tier": 1,
      "model": "claude-haiku-4-5",
      "latency_req": "standard",
      "confidence_interval": [14.2, 18.0]
    },
    "StateB": {
      "skills": ["skill.analysis.financial@1.0.0"],
      "fcs": 28.5,
      "tier": 2,
      "model": "claude-sonnet-4",
      "latency_req": "standard",
      "confidence_interval": [25.0, 32.0]
    }
  },
  "aggregate": {
    "total_estimated_cost_usd": 0.15,
    "dominant_tier": 1,
    "tier_distribution": {"0": 0, "1": 3, "2": 1, "3": 0},
    "avg_fcs": 19.2
  }
}
```

### 3.5.2 Extended State Document Fields

**Key:** `cp:wf:{workflow_id}:state:{state_name}`

**Additional fields:**

```json
{
  "status": "done",
  "attempts": 1,
  "lease": {...},
  "model_selection": {
    "tier": 1,
    "model": "claude-haiku-4-5",
    "escalated": false,
    "escalation_reason": null,
    "actual_cost_usd": 0.02,
    "actual_tokens_in": 1500,
    "actual_tokens_out": 800
  }
}
```

### 3.5.3 Session-Level Model Tracking (Phase 2)

**Key:** `session:{session_id}:model_usage`

```json
{
  "session_id": "...",
  "started_at": "2026-02-03T10:00:00Z",
  "cumulative_cost_usd": 0.45,
  "task_count": 12,
  "tier_distribution": {"0": 2, "1": 8, "2": 2},
  "escalation_count": 2,
  "avg_latency_ms": 1100,
  "cost_budget_usd": 1.00,
  "budget_remaining_usd": 0.55
}
```

---

## 3.6 Graphiti Entity Types (2 new)

### 3.6.1 SkillComplexityProfile Entity

**Purpose:** Store and track skill complexity calibration data

```cypher
CREATE (p:SkillComplexityProfile {
  skill_id: "skill.research.web",
  version: "0.1.0",
  base_wcs: 14,
  dimension_scores: {
    horizon: 2, context: 2, tooling: 3,
    observability: 2, modality: 1, precision: 2, adaptability: 2
  },
  final_fcs: 16.1,
  maturity_level: "validated",
  sample_size: 47,
  success_rate_by_tier: {
    "0": 0.0, "1": 0.89, "2": 0.95, "3": 1.0
  },
  validated_models: ["claude-haiku-4-5", "claude-sonnet-4"],
  last_calibrated: datetime(),
  calibration_source: "production_executions"
})
```

### 3.6.2 ModelSelectionEvent Entity

**Purpose:** Track individual model selection decisions for analysis

```cypher
CREATE (e:ModelSelectionEvent {
  event_id: $uuid,
  workflow_id: "...",
  session_id: "...",  // null for Phase 1
  state_name: "StateA",
  skill_ids: ["skill.research.web@0.1.0"],
  computed_fcs: 16.1,
  selected_tier: 1,
  selected_model: "claude-haiku-4-5",
  latency_requirement: "standard",
  actual_tier: 1,
  escalated: false,
  success: true,
  inference_cost_usd: 0.02,
  tokens_in: 1500,
  tokens_out: 800,
  latency_ms: 1200,
  created_at: datetime()
})

// Relationship to skill profile
MATCH (e:ModelSelectionEvent {event_id: $id})
MATCH (p:SkillComplexityProfile {skill_id: $skill})
CREATE (e)-[:USED_PROFILE]->(p)
```

---

# Part IV: Implementation Playbook

## 4.1 Phase Overview

| Phase | Name | Scope | Files | Risk |
|-------|------|-------|-------|------|
| A | Foundation (MVP) | Basic model selection | 7 | LOW |
| B | Full Phase 1 | Complete workflow integration | 8 | MEDIUM |
| C | Phase 2 Integration | Delegated execution | 8 | MEDIUM |
| D | Optimization | Continuous improvement | 4 | LOW |

## 4.2 Phase A: Foundation (Minimum Viable Integration)

**Goal:** Basic model selection working for Phase 1 workflows

**Duration:** 1-2 weeks

### Tasks

- [ ] **A.1** Create `amsp-complexity-profile-1.0.0.json` schema
- [ ] **A.2** Add `complexityProfile` to skill manifest schema (v2.1.0)
- [ ] **A.3** Implement `compute_task_complexity.py` tool
- [ ] **A.4** Modify `create_worker_agents.py` to use complexity-based selection
- [ ] **A.5** Add basic metrics to data plane output schema (v1.1.0)
- [ ] **A.6** Update Planner prompt with model selection section
- [ ] **A.7** Add complexity profiles to 2-3 existing skills (for testing)

### Files Modified/Created

| File | Action | Notes |
|------|--------|-------|
| `dcf_mcp/schemas/amsp-complexity-profile-1.0.0.json` | CREATE | New schema |
| `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json` | MODIFY | Add complexityProfile |
| `dcf_mcp/schemas/data-plane-output-1.0.0.json` | MODIFY | Add metrics |
| `dcf_mcp/tools/dcf/compute_task_complexity.py` | CREATE | New tool |
| `dcf_mcp/tools/dcf/create_worker_agents.py` | MODIFY | Add model selection |
| `prompts/dcf/Planner_final.txt` | MODIFY | Add section |
| `skills_src/skills/*.skill.yaml` | MODIFY | Add complexity profiles |

### Verification

1. Run `validate_skill_manifest` on updated skills
2. Test `compute_task_complexity` with known skill profiles
3. Execute simple workflow with model selection enabled
4. Verify model selection recorded in data plane output

### Exit Criteria

- [ ] `compute_task_complexity` returns valid FCS for test skills
- [ ] `create_worker_agents` logs model selection decisions
- [ ] Workflow execution completes with model metrics in output
- [ ] No regressions in existing workflow tests

---

## 4.3 Phase B: Full Phase 1 Integration

**Goal:** Complete workflow execution with model selection, tracking, and analysis

**Duration:** 2-3 weeks

**Prerequisites:** Phase A complete and validated

### Tasks

- [ ] **B.1** Update control-plane-state schema (v1.1.0) with model_selection
- [ ] **B.2** Update control-plane-meta schema (v1.1.0) with workflow_complexity
- [ ] **B.3** Modify `validate_workflow.py` for complexity validation
- [ ] **B.4** Modify `finalize_workflow.py` for cost aggregation and recalibration triggers
- [ ] **B.5** Add Redis key pattern for model selection audit
- [ ] **B.6** Update Worker prompt with model awareness section
- [ ] **B.7** Update Reflector prompt with model selection analysis section
- [ ] **B.8** Add Graphiti entity types (SkillComplexityProfile, ModelSelectionEvent)

### Files Modified

| File | Action |
|------|--------|
| `dcf_mcp/schemas/control-plane-state-1.0.0.json` | MODIFY |
| `dcf_mcp/schemas/control-plane-meta-1.0.0.json` | MODIFY |
| `dcf_mcp/tools/dcf/validate_workflow.py` | MODIFY |
| `dcf_mcp/tools/dcf/finalize_workflow.py` | MODIFY |
| `prompts/dcf/Worker_final.txt` | MODIFY |
| `prompts/dcf/Reflector_final.txt` | MODIFY |
| Graphiti schema definitions | MODIFY |

### Verification

1. Run workflow with multiple tiers, verify state-level tracking
2. Trigger Reflector analysis, verify model selection insights
3. Verify Redis control plane contains model_selection data
4. Query Graphiti for ModelSelectionEvent entities

### Exit Criteria

- [ ] Control plane tracks model selection per state
- [ ] Finalize aggregates cost and detects estimation errors
- [ ] Reflector produces model selection recommendations
- [ ] Graphiti stores execution events

---

## 4.4 Phase C: Phase 2 Integration

**Goal:** Delegated execution with dynamic model selection

**Duration:** 2-3 weeks

**Prerequisites:** Phase B complete and validated

### Tasks

- [ ] **C.1** Modify `delegate_task.py` for complexity-based delegation
- [ ] **C.2** Modify `create_companion.py` for model tier configuration
- [ ] **C.3** Modify `trigger_strategist_analysis.py` with model selection metrics
- [ ] **C.4** Modify `update_conductor_guidelines.py` with model recommendations
- [ ] **C.5** Update Conductor prompt with dynamic model selection section
- [ ] **C.6** Update Companion prompt with model awareness section
- [ ] **C.7** Update Strategist prompt with model selection optimization section
- [ ] **C.8** Add session-level model tracking in Redis

### Files Modified

| File | Action |
|------|--------|
| `dcf_mcp/tools/dcf_plus/delegate_task.py` | MODIFY |
| `dcf_mcp/tools/dcf_plus/create_companion.py` | MODIFY |
| `dcf_mcp/tools/dcf_plus/trigger_strategist_analysis.py` | MODIFY |
| `dcf_mcp/tools/dcf_plus/update_conductor_guidelines.py` | MODIFY |
| `prompts/dcf+/Conductor.md` | MODIFY |
| `prompts/dcf+/Companion.md` | MODIFY |
| `prompts/dcf+/Strategist.md` | MODIFY |

### Verification

1. Create session, delegate tasks with varying complexity
2. Verify Companions report model metrics
3. Trigger Strategist analysis, verify optimization recommendations
4. Test tier escalation flow (Companion signals → Conductor re-delegates)

### Exit Criteria

- [ ] Conductor selects model tier at each delegation
- [ ] Companions report execution metrics
- [ ] Strategist produces model selection guidelines
- [ ] Session-level cost tracking works

---

## 4.5 Phase D: Optimization & Learning

**Goal:** Continuous improvement based on execution outcomes

**Duration:** 2-3 weeks

**Prerequisites:** Phase C complete and validated

### Tasks

- [ ] **D.1** Implement complexity profile recalibration logic
- [ ] **D.2** Add Reflector → skill profile feedback loop
- [ ] **D.3** Add Strategist → Conductor guideline updates
- [ ] **D.4** Build materialized views in Graphiti for common queries
- [ ] **D.5** Implement caching layer for complexity profiles
- [ ] **D.6** Add confidence interval tracking and reporting

### Focus Areas

1. **Recalibration Triggers**
   - Automatic when escalation rate > 20%
   - Automatic when cost deviation > 30%
   - Manual via Reflector recommendation

2. **Performance Optimization**
   - Cache computed FCS for repeated skill combinations
   - Precompute aggregates for common Graphiti queries
   - Batch recalibration jobs (not real-time)

3. **Confidence Tracking**
   - Track FCS confidence intervals per skill
   - Widen intervals for provisional skills
   - Narrow intervals as sample size grows

### Verification

1. Execute 50+ workflows/tasks, verify recalibration triggers
2. Measure Graphiti query latency, verify <50ms for common queries
3. Verify confidence intervals update with sample size

### Exit Criteria

- [ ] Skill profiles auto-recalibrate based on outcomes
- [ ] Graphiti queries meet latency budget
- [ ] Confidence intervals reflect actual uncertainty

---

# Part V: Verification & Testing

## 5.1 Unit Tests

| Component | Test Cases |
|-----------|------------|
| `compute_task_complexity.py` | WCS calculation, interaction multipliers, tier mapping |
| Schema validation | All new fields validate correctly |
| Prompt parsing | New sections don't break existing prompt loading |

## 5.2 Integration Tests

| Scenario | Expected Outcome |
|----------|------------------|
| Simple workflow (all Tier 0) | All states use Tier 0 model |
| Mixed workflow (Tier 0-2) | States use appropriate tiers |
| Tier escalation | Worker signals, Planner re-executes |
| Cost tracking | Actual cost within 30% of estimate |
| Reflector analysis | Produces valid recommendations |

## 5.3 End-to-End Tests

| Test | Steps |
|------|-------|
| Phase 1 full cycle | Planner → Workers → Reflector with model selection |
| Phase 2 full cycle | Conductor → Companions → Strategist with model selection |
| Recalibration | Execute 30+ tasks, verify profile updates |

## 5.4 Performance Tests

| Metric | Target |
|--------|--------|
| `compute_task_complexity` latency | <100ms |
| Graphiti complexity profile lookup | <50ms |
| Model selection overhead per state | <5% of execution time |

---

# Part VI: References

## Documents

| Document | Path | Description |
|----------|------|-------------|
| AMSP v3.0 | `docs/Practical Foundation Model Selection for Agentic AI - The Adaptive Model Selection Protocol (AMSP).md` | Full AMSP specification |
| DCF Integration | `docs/Complexity-Aware Workflow Decomposition - Unifying Model Selection with Dynamic Capabilities for Cost-Effective Agentic AI.md` | AMSP-DCF integration design |
| DCF Architecture | `docs/Architectural_Evolution_Opus.md` | Phase 1 to Phase 2 evolution |
| Phase 1 Tools | `dcf_mcp/tools/dcf/TOOLS.md` | Planner, Worker, Reflector tools |
| Phase 2 Tools | `dcf_mcp/tools/dcf_plus/TOOLS.md` | Conductor, Companion, Strategist tools |

## Schemas

| Schema | Path | Version |
|--------|------|---------|
| Skill Manifest | `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json` | 2.0.0 → 2.1.0 |
| Control Plane State | `dcf_mcp/schemas/control-plane-state-1.0.0.json` | 1.0.0 → 1.1.0 |
| Control Plane Meta | `dcf_mcp/schemas/control-plane-meta-1.0.0.json` | 1.0.0 → 1.1.0 |
| Data Plane Output | `dcf_mcp/schemas/data-plane-output-1.0.0.json` | 1.0.0 → 1.1.0 |
| ASL Workflow | `dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json` | 2.2.0 → 2.3.0 |

## Agent Prompts

| Prompt | Path | Phase |
|--------|------|-------|
| Planner | `prompts/dcf/Planner_final.txt` | 1 |
| Worker | `prompts/dcf/Worker_final.txt` | 1 |
| Reflector | `prompts/dcf/Reflector_final.txt` | 1 |
| Conductor | `prompts/dcf+/Conductor.md` | 2 |
| Companion | `prompts/dcf+/Companion.md` | 2 |
| Strategist | `prompts/dcf+/Strategist.md` | 2 |

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.1 | 2026-02-03 | Added model-tier pricing reference table with February 2026 data |
| 1.0.0 | 2026-02-03 | Initial playbook created from blast radius analysis |
