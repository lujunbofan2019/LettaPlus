# Graphiti Entity Types for DCF

This document defines the entity types used by DCF agents (Reflector and Strategist) to persist institutional knowledge to the Graphiti knowledge graph.

---

## How Entity Types Work in Graphiti

Graphiti extracts **entities (nodes)** and **relationships (edges/facts)** from episodes. Entity types guide this extraction by providing:

1. **Classification hints** — Help the LLM categorize extracted entities
2. **Field schemas** — Define structured attributes for each entity type
3. **Extraction instructions** — Guide what patterns to look for

### Built-in vs Custom Entity Types

| Source | Location | Behavior |
|--------|----------|----------|
| **Built-in** | `src/models/entity_types.py` | Pydantic models with structured fields |
| **Custom** | `config/*.yaml` under `graphiti.entity_types` | Lightweight models with name + description only |

Custom entity types defined in YAML become simple Pydantic models at runtime. For structured fields, define a class in `src/models/entity_types.py`.

---

## Built-in Entity Types

These are always available from the upstream Graphiti MCP server:

| Entity Type | Purpose | Key Fields |
|-------------|---------|------------|
| `Requirement` | Product/service needs and specifications | `project_name`, `description` |
| `Preference` | User preferences, choices, opinions | (no fields) |
| `Procedure` | Sequential instructions or steps | `description` |
| `Location` | Physical or virtual places | `location_name`, `description` |
| `Event` | Time-bound activities or occurrences | `event_name`, `description` |
| `Object` | Physical items, tools, devices | `object_name`, `description` |
| `Topic` | Subjects of interest or knowledge domains | `topic_name`, `description` |
| `Organization` | Companies, institutions, groups | `org_name`, `description` |
| `Document` | Information content (books, articles, reports) | `title`, `description` |

---

## DCF Custom Entity Types

These entity types are defined in [`config/config-docker-falkordb.yaml`](config/config-docker-falkordb.yaml) for DCF-specific use cases.

### Core DCF Entities

| Entity Type | Used By | Purpose |
|-------------|---------|---------|
| `Skill` | Planner, Conductor | Reusable agent capabilities with version metadata |
| `Workflow` | Planner, Reflector | State-machine task orchestrations |
| `Agent` | All | Agent identities, capabilities, and context |

### Phase 1 Entities (Reflector)

| Entity Type | Group ID | Purpose |
|-------------|----------|---------|
| `WorkflowExecution` | `dcf_executions` | Records of completed workflow runs |
| `WorkflowState` | `dcf_executions` | Individual states within workflow executions |
| `SkillPerformanceMetric` | `dcf_metrics` | Skill success rates, latency, error patterns |
| `LearningInsight` | `dcf_insights` | Lessons learned from workflow analysis |
| `CapabilityGap` | `dcf_insights` | Missing capabilities blocking progress |
| `WorkflowAdaptation` | `dcf_insights` | Changes made to workflows based on results |

### Phase 2 Entities (Strategist)

| Entity Type | Group ID | Purpose |
|-------------|----------|---------|
| `SessionPattern` | `dcf_plus_patterns` | Behavioral patterns from delegated sessions |
| `DelegationRecord` | `dcf_plus_delegations` | Task delegation history with outcomes |
| `CompanionPattern` | `dcf_plus_companions` | Companion specialization and performance |
| `SkillMetric` | `dcf_plus_metrics` | Aggregated skill performance (daily/weekly) |
| `StrategicInsight` | `dcf_plus_insights` | Optimization insights with evidence |

### Supporting Entities

| Entity Type | Purpose |
|-------------|---------|
| `Person` | Individuals with roles, expertise, relationships |
| `Project` | Projects, products, initiatives |
| `Technology` | Tools, frameworks, platforms |
| `Bug` | Defects with severity, status, owners |
| `APIEndpoint` | API routes with methods, auth, behaviors |
| `ProblemDecomposition` | Complex problem breakdowns |

---

## Entity Schemas

### WorkflowExecution (Phase 1)

Recorded by the **Reflector** after workflow completion.

```json
{
  "entity": "WorkflowExecution",
  "workflow_id": "wf-abc123",
  "workflow_name": "Research and Summarize",
  "final_status": "succeeded",
  "total_states": 5,
  "succeeded_states": 5,
  "failed_states": 0,
  "execution_duration_s": 245.3,
  "skills_used": [
    "skill://research.web@0.2.0",
    "skill://writing.summarize@0.1.0"
  ],
  "worker_count": 3,
  "error_summary": null,
  "triggered_by": "user_request",
  "finalized_at": "2026-01-30T10:15:00Z"
}
```

**Episode Name**: `WorkflowExecution:<workflow_id>`
**Group ID**: `dcf_executions`

---

### LearningInsight (Phase 1)

Derived insights recorded by the **Reflector**.

```json
{
  "entity": "LearningInsight",
  "insight_id": "ins-xyz789",
  "category": "skill_effectiveness",
  "confidence": 0.85,
  "evidence_count": 5,
  "summary": "skill://research.web@0.2.0 has 95% success rate vs 72% for v0.1.0",
  "recommendation": "Prefer v0.2.0 for all research tasks",
  "applies_to": ["skill://research.web", "task_type:research"],
  "derived_from": ["wf-abc123", "wf-def456", "wf-ghi789"],
  "supersedes": "ins-old123",
  "created_at": "2026-01-30T10:20:00Z"
}
```

**Episode Name**: `LearningInsight:<insight_id>`
**Group ID**: `dcf_insights`

---

### SkillPerformanceMetric (Phase 1)

Skill metrics recorded by the **Reflector**.

```json
{
  "entity": "SkillPerformanceMetric",
  "skill_id": "skill://research.web@0.2.0",
  "workflow_id": "wf-abc123",
  "state_name": "Research",
  "success": true,
  "duration_s": 45.2,
  "tool_calls": 7,
  "error_code": null,
  "error_message": null,
  "recorded_at": "2026-01-30T10:15:00Z"
}
```

**Episode Name**: `SkillMetric:<skill_id>:<workflow_id>`
**Group ID**: `dcf_metrics`

---

### SessionPattern (Phase 2)

Recorded by the **Strategist** after session analysis.

```json
{
  "entity": "SessionPattern",
  "session_id": "sess-abc123",
  "conductor_id": "agent-xyz",
  "duration_s": 3600,
  "task_count": 15,
  "success_rate": 0.87,
  "companion_count_avg": 2.5,
  "companion_count_max": 4,
  "skill_usage": {
    "skill://research.web@0.2.0": {
      "count": 8,
      "success_rate": 0.95,
      "avg_duration_s": 32.5
    },
    "skill://analysis.data@0.1.0": {
      "count": 5,
      "success_rate": 0.80,
      "avg_duration_s": 45.0
    }
  },
  "patterns_observed": [
    "High parallelism with 3+ Companions improved throughput",
    "Research tasks succeeded more with specialized Companions"
  ],
  "recorded_at": "2026-01-30T11:00:00Z"
}
```

**Episode Name**: `SessionPattern:<session_id>`
**Group ID**: `dcf_plus_patterns`

---

### CompanionPattern (Phase 2)

Companion performance patterns recorded by the **Strategist**.

```json
{
  "entity": "CompanionPattern",
  "companion_id": "agent-comp-123",
  "companion_name": "companion-sess-abc-1",
  "session_id": "sess-abc123",
  "specialization": "research",
  "tasks_completed": 8,
  "tasks_failed": 0,
  "success_rate": 1.0,
  "avg_task_duration_s": 32.5,
  "skills_used": ["skill://research.web@0.2.0"],
  "specialization_fit_score": 0.95,
  "recorded_at": "2026-01-30T11:00:00Z"
}
```

**Episode Name**: `CompanionPattern:<companion_id>`
**Group ID**: `dcf_plus_companions`

---

### SkillMetric (Phase 2 - Aggregated)

Daily/weekly skill aggregations recorded by the **Strategist**.

```json
{
  "entity": "SkillMetric",
  "skill_id": "skill://research.web@0.2.0",
  "period": "2026-01-30",
  "period_type": "daily",
  "usage_count": 25,
  "success_count": 23,
  "failure_count": 2,
  "success_rate": 0.92,
  "avg_duration_s": 45.2,
  "failure_modes": [
    {"mode": "timeout", "count": 1},
    {"mode": "no_results", "count": 1}
  ],
  "sessions_used_in": 5,
  "companions_used_by": 8,
  "recorded_at": "2026-01-30T23:59:00Z"
}
```

**Episode Name**: `SkillMetric:<skill_id>:<period>`
**Group ID**: `dcf_plus_metrics`

---

### StrategicInsight (Phase 2)

Optimization insights recorded by the **Strategist**.

```json
{
  "entity": "StrategicInsight",
  "insight_id": "str-ins-456",
  "category": "skill_preference",
  "confidence": 0.90,
  "evidence_count": 12,
  "summary": "Specialized Companions outperform generalists for research tasks",
  "recommendation": "Assign research tasks to Companions with 'research' specialization",
  "applies_to": ["task_type:research", "specialization:research"],
  "derived_from_sessions": ["sess-abc123", "sess-def456"],
  "supersedes": null,
  "created_at": "2026-01-30T11:05:00Z"
}
```

**Episode Name**: `StrategicInsight:<insight_id>`
**Group ID**: `dcf_plus_insights`

---

## Usage Examples

### Reflector: Recording Workflow Execution

```python
add_episode(
    name="WorkflowExecution:wf-abc123",
    content={
        "entity": "WorkflowExecution",
        "workflow_id": "wf-abc123",
        "workflow_name": "Research and Summarize",
        "final_status": "succeeded",
        # ... full schema
    },
    source="json",
    source_description="Workflow execution record from Reflector analysis",
    group_id="dcf_executions"
)
```

### Reflector: Querying Similar Workflows

```python
search_nodes(
    query="workflows with research skills that succeeded",
    entity_types=["WorkflowExecution"],
    group_ids=["dcf_executions"],
    max_nodes=10
)
```

### Strategist: Recording Session Pattern

```python
add_episode(
    name="SessionPattern:sess-abc123",
    content={
        "entity": "SessionPattern",
        "session_id": "sess-abc123",
        # ... full schema
    },
    source="json",
    source_description="Session pattern from Strategist analysis",
    group_id="dcf_plus_patterns"
)
```

### Strategist: Querying Skill Performance History

```python
search_facts(
    query="skill://research.web success rate and failure modes",
    group_ids=["dcf_plus_metrics", "dcf_metrics"],
    max_facts=20
)
```

---

## Group ID Conventions

| Group ID | Phase | Contents |
|----------|-------|----------|
| `dcf_executions` | 1 | Workflow execution records |
| `dcf_metrics` | 1 | Per-execution skill metrics |
| `dcf_insights` | 1 | Reflector-derived insights |
| `dcf_plus_patterns` | 2 | Session behavioral patterns |
| `dcf_plus_delegations` | 2 | Task delegation records |
| `dcf_plus_companions` | 2 | Companion performance patterns |
| `dcf_plus_metrics` | 2 | Aggregated skill metrics |
| `dcf_plus_insights` | 2 | Strategist-derived insights |

---

## Configuration

Entity types are configured in [`config/config-docker-falkordb.yaml`](config/config-docker-falkordb.yaml) under `graphiti.entity_types`.

To add a new entity type:

```yaml
graphiti:
  entity_types:
    - name: "MyNewEntity"
      description: "Description guiding extraction and classification."
```

For structured fields, add a Pydantic model to `src/models/entity_types.py`:

```python
class MyNewEntity(BaseModel):
    """Description guiding extraction."""

    field_name: str = Field(..., description="Field description")
    # ... additional fields

# Add to ENTITY_TYPES dict
ENTITY_TYPES['MyNewEntity'] = MyNewEntity
```

---

## References

- [Graphiti Documentation](https://help.getzep.com/graphiti)
- [Graphiti MCP Server](https://github.com/getzep/graphiti/tree/main/mcp_server)
- [`prompts/dcf/Reflector_final.txt`](../prompts/dcf/Reflector_final.txt) — Reflector prompt
- [`prompts/dcf_plus/Strategist.md`](../prompts/dcf_plus/Strategist.md) — Strategist prompt
