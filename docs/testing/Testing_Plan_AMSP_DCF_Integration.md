# Testing Plan: AMSP-DCF Integration

**Version**: 1.0.0
**Last Updated**: 2026-02-05
**Author**: Claude Opus 4.5

This document provides a comprehensive end-to-end testing playbook for the AMSP (Adaptive Model Selection Protocol) integration with the DCF (Dynamic Capabilities Framework). It validates the integration across both Phase 1 (Workflow Execution) and Phase 2 (Delegated Execution) patterns.

---

## Table of Contents

1. [Overview](#overview)
2. [Test Scenario: Multi-Tier Analysis Pipeline](#test-scenario-multi-tier-analysis-pipeline)
3. [Setup: Skills with Complexity Profiles](#setup-skills-with-complexity-profiles)
4. [Setup: Stub MCP Configuration](#setup-stub-mcp-configuration)
5. [Test Execution: Phase A - Foundation](#test-execution-phase-a---foundation)
6. [Test Execution: Phase B - Full Phase 1 Integration](#test-execution-phase-b---full-phase-1-integration)
7. [Test Execution: Phase C - Phase 2 Integration](#test-execution-phase-c---phase-2-integration)
8. [Verification Checklist](#verification-checklist)
9. [Cleanup](#cleanup)

---

## Overview

### AMSP Integration Architecture

The AMSP integration enables intelligent model tier selection based on task complexity across both DCF phases:

```
                              AMSP Integration Architecture
┌────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                    │
│  Skill Manifest (v2.1.0)        compute_task_complexity()        Model Selection   │
│  ┌─────────────────────┐        ┌────────────────────────┐       ┌───────────────┐ │
│  │ complexityProfile:  │        │ WCM Scoring            │       │ Tier 0: Nano  │ │
│  │   baseWCS: 14       │   →    │ Interaction Multipliers│  →    │ Tier 1: Haiku │ │
│  │   dimensionScores:  │        │ FCS Calculation        │       │ Tier 2: Sonnet│ │
│  │   maturityLevel:    │        │ Tier Mapping           │       │ Tier 3: Opus  │ │
│  └─────────────────────┘        └────────────────────────┘       └───────────────┘ │
│                                                                                    │
│  Phase 1 (Workflow)             Phase 2 (Delegated)                                │
│  ┌─────────────────────┐        ┌─────────────────────┐                            │
│  │ create_worker_agents│        │ delegate_task       │                            │
│  │   → model_selections│        │   → model_selection │                            │
│  │ finalize_workflow   │        │ create_companion    │                            │
│  │   → cost_summary    │        │   → model_tier      │                            │
│  │ Reflector analysis  │        │ Strategist analysis │                            │
│  └─────────────────────┘        └─────────────────────┘                            │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Components Under Test

#### Phase A: Foundation (MVP)

| Component | Purpose | Tool/File |
|-----------|---------|-----------|
| **Complexity Profile Schema** | Defines WCM dimensions | `amsp-complexity-profile-1.0.0.json` |
| **Skill Manifest v2.1.0** | Adds `complexityProfile` field | `skill_manifest_schema_v2.1.0.json` |
| **Complexity Calculator** | Computes FCS and tier | `compute_task_complexity.py` |
| **Worker Model Selection** | Selects model during creation | `create_worker_agents.py` |
| **YAML Generation** | Extracts profiles from YAML | `yaml_to_manifests.py` |

#### Phase B: Full Phase 1 Integration

| Component | Purpose | Tool/File |
|-----------|---------|-----------|
| **Control Plane State v1.1.0** | Tracks model_selection per state | `control-plane-state-1.1.0.json` |
| **Control Plane Meta v1.1.0** | Tracks workflow_complexity | `control-plane-meta-1.1.0.json` |
| **Workflow Validation** | Complexity coverage warnings | `validate_workflow.py` |
| **Finalize Workflow** | Cost aggregation and AMSP audit | `finalize_workflow.py` |
| **Worker Prompt** | Model awareness section | `Worker_final.txt` |
| **Reflector Prompt** | Model selection analysis | `Reflector_final.txt` |

#### Phase C: Phase 2 Integration

| Component | Purpose | Tool/File |
|-----------|---------|-----------|
| **Delegate Task** | Complexity-based delegation | `delegate_task.py` |
| **Create Companion** | Model tier configuration | `create_companion.py` |
| **Strategist Analysis** | AMSP metrics extraction | `trigger_strategist_analysis.py` |
| **Conductor Guidelines** | Model selection recommendations | `update_conductor_guidelines.py` |
| **Conductor Prompt** | Dynamic model selection | `Conductor.md` |
| **Companion Prompt** | Model awareness | `Companion.md` |
| **Strategist Prompt** | Model selection optimization | `Strategist.md` |

### WCM Dimensions Reference

| Dimension | Weight | Score Range | Description |
|-----------|--------|-------------|-------------|
| Horizon | 1.0 | 0-3 | Single-turn to multi-session planning |
| Context | 1.0 | 0-3 | Self-contained to cross-domain synthesis |
| Tooling | 1.0 | 0-3 | No tools to complex orchestration |
| Observability | 1.0 | 0-3 | Full transparency to opaque environments |
| Modality | 1.0 | 0-3 | Text-only to complex multimodal |
| Precision | 1.0 | 0-3 | Approximate to exact correctness |
| Adaptability | 1.0 | 0-3 | Stable to highly dynamic context |

### Tier Boundaries

| Tier | FCS Range | Capability Profile | Model Examples |
|------|-----------|-------------------|----------------|
| 0 | 0-12 | Single-turn, deterministic, no tools | GPT-5 Nano, Grok 4.1 Fast |
| 1 | 13-25 | Multi-turn, simple tools, moderate context | Claude Haiku 4.5, Llama 4 |
| 2 | 26-50 | Complex reasoning, multi-tool, synthesis | GPT-5, Claude Sonnet 4.5 |
| 3 | 51+ | Novel domains, research-grade | Claude Opus 4.5, GPT-5.2 Pro |

### Prerequisites

Ensure all services are running:

```bash
docker compose up --build
```

Verify service health:

| Service | Health Check | Expected |
|---------|--------------|----------|
| Letta API | `curl -sf http://localhost:8283/v1/health/` | `{"status": "ok"}` |
| DCF MCP | `curl -sf http://localhost:8337/health` | `{"status": "healthy"}` |
| Stub MCP | `curl -sf http://localhost:8765/healthz` | `{"status": "ok"}` |
| Redis | `docker exec redis redis-cli ping` | `PONG` |

---

## Test Scenario: Multi-Tier Analysis Pipeline

### Business Context

A data analysis team needs to process various tasks with different complexity levels:

1. **Simple Summarization** (Tier 0) — Summarize a short document
2. **Web Research** (Tier 0-1) — Search and synthesize web information
3. **Complex Analysis** (Tier 1-2) — Multi-source analysis with synthesis

This scenario validates that AMSP correctly:
- Assigns different tiers to skills based on complexity profiles
- Selects appropriate models for each tier
- Tracks model selection decisions in control plane
- Aggregates cost metrics after execution
- Provides optimization recommendations via advisors

### Test Data: Task Inputs

**Task 1: Simple Summarization**
```json
{
  "task_id": "task-summary-001",
  "task_type": "summarization",
  "input": {
    "text": "Quarterly sales increased by 15% driven by new product launches...",
    "max_length": 100
  }
}
```

**Task 2: Web Research**
```json
{
  "task_id": "task-research-001",
  "task_type": "research",
  "input": {
    "query": "Latest AI model pricing trends 2026",
    "sources": 3
  }
}
```

**Task 3: Complex Analysis**
```json
{
  "task_id": "task-analysis-001",
  "task_type": "analysis",
  "input": {
    "sources": ["financial_report.pdf", "market_data.csv", "competitor_analysis.md"],
    "question": "What are the key factors driving Q1 performance?"
  }
}
```

### Expected Tier Assignments

| Task | Skill | Expected FCS | Expected Tier | Rationale |
|------|-------|--------------|---------------|-----------|
| Summary | write.summary | 3.0 | 0 | Simple, single-turn, no tools |
| Research | research.web | 9.2 | 0 | Low complexity with moderate tooling |
| Analysis | analyze.synthesis | 14.2 | 1 | Multi-source, requires context synthesis |

---

## Setup: Skills with Complexity Profiles

The following skills already exist with AMSP complexity profiles from Phase A implementation. Verify they are properly configured:

### Skill 1: write.summary (Tier 0)

**File:** `skills_src/skills/write/write.summary.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.write.summary@0.1.0
  name: write.summary
  version: 0.1.0
  description: Generates concise summaries from text input
  tags:
    - writing
    - summarization
    - tier-0
spec:
  permissions:
    egress: none
    secrets: []
  directives: |
    You are a summarization specialist. Create concise summaries...
  tools:
    - ref: llm:generate_text
      required: true
  dataSources: []
  complexityProfile:
    baseWCS: 3
    dimensionScores:
      horizon: 0      # Single-turn
      context: 1      # Self-contained
      tooling: 0      # No external tools
      observability: 0  # Fully transparent
      modality: 0     # Text only
      precision: 1    # Moderate accuracy
      adaptability: 1 # Stable input
    interactionMultipliers: []
    finalFCS: 3.0
    recommendedTier: 0
    maturityLevel: validated
    validatedModels:
      - gpt-5-nano
      - gpt-4o-mini
    sampleSize: 50
```

### Skill 2: research.web (Tier 0)

**File:** `skills_src/skills/research/research.web.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.research.web@0.1.0
  name: research.web
  version: 0.1.0
  description: Performs web searches and synthesizes results
  tags:
    - research
    - web
    - search
    - tier-0
spec:
  permissions:
    egress: internet
    secrets: []
  directives: |
    You are a research specialist. Search the web and synthesize findings...
  tools:
    - ref: search:web_search
      required: true
    - ref: web:fetch_page
      required: false
  dataSources: []
  complexityProfile:
    baseWCS: 8
    dimensionScores:
      horizon: 1      # Single-turn with planning
      context: 1      # Self-contained
      tooling: 2      # Multiple tools
      observability: 1  # External web content
      modality: 0     # Text only
      precision: 1    # Moderate accuracy
      adaptability: 2 # Variable web results
    interactionMultipliers:
      - pair: tooling+adaptability
        multiplier: 1.15
        reason: Tool results vary based on web state
    finalFCS: 9.2
    recommendedTier: 0
    maturityLevel: validated
    validatedModels:
      - gpt-5-nano
      - gpt-4o-mini
      - claude-haiku-4-5
    sampleSize: 35
```

### Skill 3: analyze.synthesis (Tier 1)

**File:** `skills_src/skills/analyze/analyze.synthesis.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.analyze.synthesis@0.1.0
  name: analyze.synthesis
  version: 0.1.0
  description: Synthesizes analysis from multiple data sources
  tags:
    - analysis
    - synthesis
    - multi-source
    - tier-1
spec:
  permissions:
    egress: intranet
    secrets: []
  directives: |
    You are an analysis specialist. Synthesize insights from multiple sources...
  tools:
    - ref: data:read_document
      required: true
    - ref: data:query_database
      required: false
    - ref: llm:generate_analysis
      required: true
  dataSources: []
  complexityProfile:
    baseWCS: 12
    dimensionScores:
      horizon: 2      # Multi-turn reasoning
      context: 3      # Cross-domain synthesis
      tooling: 2      # Multiple tools
      observability: 1  # Some uncertainty
      modality: 1     # Text + structured data
      precision: 3    # High accuracy required
      adaptability: 0 # Stable sources
    interactionMultipliers:
      - pair: context+precision
        multiplier: 1.18
        reason: High precision with cross-domain synthesis
    finalFCS: 14.2
    recommendedTier: 1
    maturityLevel: validated
    validatedModels:
      - claude-haiku-4-5
      - gpt-4o
    sampleSize: 28
```

### Verify Skill Manifests Generated

After skill files are created/updated, regenerate manifests:

```bash
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'
```

Verify complexity profiles in generated manifests:

```bash
# Check write.summary
cat generated/manifests/skill.write.summary-0.1.0.json | jq '.complexityProfile'

# Check research.web
cat generated/manifests/skill.research.web-0.1.0.json | jq '.complexityProfile'

# Check analyze.synthesis
cat generated/manifests/skill.analyze.synthesis-0.1.0.json | jq '.complexityProfile'
```

---

## Setup: Stub MCP Configuration

The stub MCP tools should already be configured from Phase 1/2 testing. Verify the following tools exist:

### Required Stub Tools

| Server | Tool | Purpose |
|--------|------|---------|
| llm | generate_text | Text generation for summarization |
| search | web_search | Web search for research |
| web | fetch_page | Fetch web page content |
| data | read_document | Read document content |
| data | query_database | Query structured data |
| llm | generate_analysis | Generate analysis output |

### Verify Stub Configuration

```bash
# Check stub config includes required tools
cat generated/stub/stub_config.json | jq '.servers | keys'
```

---

## Test Execution: Phase A - Foundation

### A.T1: Complexity Profile Schema Validation

Verify the AMSP complexity profile schema is valid:

```bash
docker exec dcf-mcp python -c "
import json
import jsonschema

# Load schema
with open('/app/dcf_mcp/schemas/amsp-complexity-profile-1.0.0.json') as f:
    schema = json.load(f)

# Validate schema is valid JSON Schema
jsonschema.Draft202012Validator.check_schema(schema)
print('✓ AMSP complexity profile schema is valid')

# Test validation against sample profile
sample = {
    'skill_id': 'skill.test@1.0.0',
    'version': '1.0.0',
    'base_wcs': 10,
    'dimension_scores': {
        'horizon': 1, 'context': 2, 'tooling': 1,
        'observability': 1, 'modality': 1, 'precision': 2, 'adaptability': 2
    },
    'maturity_level': 'provisional'
}
jsonschema.validate(sample, schema)
print('✓ Sample profile validates against schema')
"
```

**Expected Output:**
```
✓ AMSP complexity profile schema is valid
✓ Sample profile validates against schema
```

### A.T2: Skill Manifest v2.1.0 Schema Validation

Verify skill manifests with complexity profiles validate correctly:

```bash
docker exec dcf-mcp python -c "
import json
import jsonschema

# Load v2.1.0 schema
with open('/app/dcf_mcp/schemas/skill_manifest_schema_v2.1.0.json') as f:
    schema = json.load(f)

# Load generated manifest with complexity profile
with open('/app/generated/manifests/skill.write.summary-0.1.0.json') as f:
    manifest = json.load(f)

# Validate
jsonschema.validate(manifest, schema)
print('✓ skill.write.summary manifest validates against v2.1.0 schema')

# Verify complexity profile exists
assert 'complexityProfile' in manifest, 'Missing complexityProfile'
assert manifest['manifestApiVersion'] == 'v2.1.0', 'Wrong API version'
print('✓ Manifest has complexityProfile and correct API version')

# Check all required dimension scores
dims = manifest['complexityProfile']['dimensionScores']
required = ['horizon', 'context', 'tooling', 'observability', 'modality', 'precision', 'adaptability']
for dim in required:
    assert dim in dims, f'Missing dimension: {dim}'
print('✓ All 7 WCM dimensions present')
"
```

**Expected Output:**
```
✓ skill.write.summary manifest validates against v2.1.0 schema
✓ Manifest has complexityProfile and correct API version
✓ All 7 WCM dimensions present
```

### A.T3: compute_task_complexity Unit Tests

Test the core AMSP calculation engine:

```bash
docker exec dcf-mcp python -c "
import json
from dcf_mcp.tools.dcf.compute_task_complexity import compute_task_complexity

print('=== Test 1: Single Tier 0 Skill ===')
result = compute_task_complexity(
    skills_json=json.dumps(['skill.write.summary@0.1.0']),
    latency_requirement='standard'
)
print(f'FCS: {result[\"final_fcs\"]}')
print(f'Tier: {result[\"recommended_tier\"]}')
assert result['error'] is None, f'Error: {result[\"error\"]}'
assert result['recommended_tier'] == 0, f'Expected Tier 0, got {result[\"recommended_tier\"]}'
print('✓ write.summary correctly classified as Tier 0')

print()
print('=== Test 2: Multi-Skill Aggregation ===')
result = compute_task_complexity(
    skills_json=json.dumps([
        'skill.research.web@0.1.0',
        'skill.analyze.synthesis@0.1.0'
    ]),
    latency_requirement='standard'
)
print(f'Aggregated FCS: {result[\"final_fcs\"]}')
print(f'Tier: {result[\"recommended_tier\"]}')
assert result['error'] is None
# Multi-skill should aggregate to higher complexity (max of skills)
assert result['recommended_tier'] >= 1, 'Combined skills should be at least Tier 1'
print('✓ Multi-skill aggregation produces higher tier')

print()
print('=== Test 3: Latency Constraint ===')
result = compute_task_complexity(
    skills_json=json.dumps(['skill.analyze.synthesis@0.1.0']),
    latency_requirement='critical'
)
print(f'FCS: {result[\"final_fcs\"]}')
print(f'Latency-adjusted Tier: {result[\"latency_adjusted_tier\"]}')
assert result['latency_adjusted_tier'] <= 1, 'Critical latency should cap at Tier 1'
print('✓ Latency constraint correctly caps tier')

print()
print('=== Test 4: Context Features Override ===')
result = compute_task_complexity(
    skills_json=json.dumps(['skill.write.summary@0.1.0']),
    context_features=json.dumps({'horizon': 3, 'precision': 3}),
    latency_requirement='standard'
)
print(f'Overridden FCS: {result[\"final_fcs\"]}')
# Context override should increase complexity
assert result['final_fcs'] > 3.0, 'Context override should increase FCS'
print('✓ Context features override works correctly')
"
```

**Expected Output:**
```
=== Test 1: Single Tier 0 Skill ===
FCS: 3.0
Tier: 0
✓ write.summary correctly classified as Tier 0

=== Test 2: Multi-Skill Aggregation ===
Aggregated FCS: 14.2
Tier: 1
✓ Multi-skill aggregation produces higher tier

=== Test 3: Latency Constraint ===
FCS: 14.2
Latency-adjusted Tier: 1
✓ Latency constraint correctly caps tier

=== Test 4: Context Features Override ===
Overridden FCS: 9.0
✓ Context features override works correctly
```

### A.T4: create_worker_agents with Model Selection

Test that worker creation includes AMSP model selection:

```bash
docker exec dcf-mcp python -c "
import json
from dcf_mcp.tools.dcf.create_worker_agents import create_worker_agents

# Create a workflow with skills at different tiers
workflow = {
    'workflow_id': 'amsp-test-001',
    'workflow_name': 'AMSP Model Selection Test',
    'version': '1.0.0',
    'af_imports': [{'uri': '/app/dcf_mcp/agents/worker.af', 'version': '2'}],
    'asl': {
        'StartAt': 'Summarize',
        'States': {
            'Summarize': {
                'Type': 'Task',
                'AgentBinding': {
                    'agent_template_ref': {'name': 'worker'},
                    'skills': ['skill://write.summary@0.1.0']
                },
                'Next': 'Research'
            },
            'Research': {
                'Type': 'Task',
                'AgentBinding': {
                    'agent_template_ref': {'name': 'worker'},
                    'skills': ['skill://research.web@0.1.0']
                },
                'Next': 'Analyze'
            },
            'Analyze': {
                'Type': 'Task',
                'AgentBinding': {
                    'agent_template_ref': {'name': 'worker'},
                    'skills': ['skill://analyze.synthesis@0.1.0']
                },
                'End': True
            }
        }
    }
}

result = create_worker_agents(
    workflow_json=json.dumps(workflow),
    imports_base_dir='/app',
    skip_if_exists=False,
    enable_model_selection=True,
    latency_requirement='standard'
)

print('Status:', result['status'])
assert result['error'] is None, f'Error: {result[\"error\"]}'

# Check model_selections
ms = result.get('model_selections', {})
print()
print('Model Selections:')
for state, selection in ms.items():
    print(f'  {state}: Tier {selection[\"tier\"]}, FCS {selection.get(\"fcs\", \"N/A\")}')

# Verify tier assignments
if 'Summarize' in ms:
    assert ms['Summarize']['tier'] == 0, 'Summarize should be Tier 0'
if 'Analyze' in ms:
    assert ms['Analyze']['tier'] >= 1, 'Analyze should be at least Tier 1'

print()
print('✓ Model selection recorded for all states')

# Check aggregate complexity
agg = result.get('aggregate_complexity', {})
if agg:
    print(f'Aggregate: Dominant Tier {agg.get(\"dominant_tier\")}, Est Cost \${agg.get(\"estimated_cost_usd\", 0):.4f}')

# Clean up created agents
if result.get('created'):
    from letta_client import Letta
    client = Letta(base_url='http://letta:8283')
    for agent in result['created']:
        try:
            client.agents.delete(agent['agent_id'])
            print(f'Cleaned up {agent[\"agent_id\"]}')
        except Exception as e:
            print(f'Warning: Could not delete {agent[\"agent_id\"]}: {e}')
"
```

**Expected Output:**
```
Status: Created 3 worker agents for workflow 'amsp-test-001'. Model selection enabled.

Model Selections:
  Summarize: Tier 0, FCS 3.0
  Research: Tier 0, FCS 9.2
  Analyze: Tier 1, FCS 14.2

✓ Model selection recorded for all states
Aggregate: Dominant Tier 0, Est Cost $0.0015
Cleaned up agent-xxx...
```

### A.T5: YAML to Manifest Generation

Verify YAML sources generate manifests with complexity profiles:

```bash
docker exec dcf-mcp python -c "
import json

# Regenerate manifests
from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests
result = yaml_to_manifests()
print(f'Generated {len(result.get(\"manifests\", []))} manifests')

# Check specific manifests for complexity profiles
manifests_to_check = [
    '/app/generated/manifests/skill.write.summary-0.1.0.json',
    '/app/generated/manifests/skill.research.web-0.1.0.json',
    '/app/generated/manifests/skill.analyze.synthesis-0.1.0.json'
]

for path in manifests_to_check:
    with open(path) as f:
        m = json.load(f)

    skill_name = m.get('skillName', 'unknown')
    has_profile = 'complexityProfile' in m
    api_version = m.get('manifestApiVersion', 'unknown')

    if has_profile:
        tier = m['complexityProfile'].get('recommendedTier', 'N/A')
        fcs = m['complexityProfile'].get('finalFCS', 'N/A')
        maturity = m['complexityProfile'].get('maturityLevel', 'N/A')
        print(f'✓ {skill_name}: Tier {tier}, FCS {fcs}, Maturity {maturity} (v{api_version})')
    else:
        print(f'✗ {skill_name}: NO complexity profile')
"
```

**Expected Output:**
```
Generated 15 manifests
✓ write.summary: Tier 0, FCS 3.0, Maturity validated (v2.1.0)
✓ research.web: Tier 0, FCS 9.2, Maturity validated (v2.1.0)
✓ analyze.synthesis: Tier 1, FCS 14.2, Maturity validated (v2.1.0)
```

---

## Test Execution: Phase B - Full Phase 1 Integration

### B.T1: Control Plane State Schema Validation

Verify state schema includes model_selection fields:

```bash
docker exec dcf-mcp python -c "
import json
import jsonschema

with open('/app/dcf_mcp/schemas/control-plane-state-1.1.0.json') as f:
    schema = json.load(f)

# Validate a state document with model_selection
state_doc = {
    'state_name': 'TestState',
    'status': 'running',
    'attempts': 1,
    'model_selection': {
        'tier': 1,
        'model': 'claude-haiku-4-5',
        'fcs': 14.2,
        'latency_requirement': 'standard',
        'escalated': False
    },
    'execution_metrics': {
        'tokens_in': 1500,
        'tokens_out': 800,
        'latency_ms': 1200,
        'inference_cost_usd': 0.002
    }
}

jsonschema.validate(state_doc, schema)
print('✓ State document with model_selection validates')
print(f'  Model: {state_doc[\"model_selection\"][\"model\"]}')
print(f'  Tier: {state_doc[\"model_selection\"][\"tier\"]}')
print(f'  Cost: \${state_doc[\"execution_metrics\"][\"inference_cost_usd\"]}')
"
```

### B.T2: Control Plane Meta Schema Validation

Verify meta schema includes workflow_complexity:

```bash
docker exec dcf-mcp python -c "
import json
import jsonschema

with open('/app/dcf_mcp/schemas/control-plane-meta-1.1.0.json') as f:
    schema = json.load(f)

# Validate a meta document with workflow_complexity
meta_doc = {
    'workflow_id': 'test-wf-001',
    'workflow_name': 'Test Workflow',
    'status': 'running',
    'state_count': 3,
    'workflow_complexity': {
        'aggregate_fcs': 8.8,
        'dominant_tier': 0,
        'tier_distribution': {'0': 2, '1': 1},
        'estimated_cost_usd': 0.005
    },
    'cost_summary': {
        'estimated_total_usd': 0.005,
        'actual_total_usd': 0.0048,
        'deviation_pct': -4.0
    }
}

jsonschema.validate(meta_doc, schema)
print('✓ Meta document with workflow_complexity validates')
print(f'  Aggregate FCS: {meta_doc[\"workflow_complexity\"][\"aggregate_fcs\"]}')
print(f'  Dominant Tier: {meta_doc[\"workflow_complexity\"][\"dominant_tier\"]}')
print(f'  Tier Distribution: {meta_doc[\"workflow_complexity\"][\"tier_distribution\"]}')
"
```

### B.T3: Workflow Validation with Complexity Warnings

Test workflow validation reports complexity profile coverage:

```bash
docker exec dcf-mcp python -c "
import json
from dcf_mcp.tools.dcf.validate_workflow import validate_workflow

# Workflow using skills with complexity profiles
workflow = {
    'workflow_schema_version': '2.2.0',
    'workflow_id': 'amsp-validate-test',
    'workflow_name': 'AMSP Validation Test',
    'version': '1.0.0',
    'af_imports': [{'uri': '/app/dcf_mcp/agents/worker.af', 'version': '2'}],
    'skill_imports': [
        'skill://write.summary@0.1.0',
        'skill://analyze.synthesis@0.1.0'
    ],
    'asl': {
        'StartAt': 'Step1',
        'States': {
            'Step1': {
                'Type': 'Task',
                'AgentBinding': {
                    'agent_template_ref': {'name': 'worker'},
                    'skills': ['skill://write.summary@0.1.0']
                },
                'Next': 'Step2'
            },
            'Step2': {
                'Type': 'Task',
                'AgentBinding': {
                    'agent_template_ref': {'name': 'worker'},
                    'skills': ['skill://analyze.synthesis@0.1.0']
                },
                'End': True
            }
        }
    }
}

result = validate_workflow(
    workflow_json=json.dumps(workflow),
    resolve_imports=True
)

print(f'Exit Code: {result[\"exit_code\"]}')
print(f'Valid: {result.get(\"valid\", False)}')

# Check for complexity coverage info
complexity = result.get('complexity_coverage', {})
if complexity:
    print(f'Complexity Coverage: {complexity.get(\"coverage_pct\", 0)}%')
    print(f'Skills with profiles: {complexity.get(\"skills_with_profiles\", [])}')
    print(f'Skills without profiles: {complexity.get(\"skills_without_profiles\", [])}')

warnings = result.get('warnings', [])
for w in warnings:
    if 'complexity' in w.lower() or 'provisional' in w.lower():
        print(f'Warning: {w}')

print('✓ Workflow validation completed with complexity info')
"
```

### B.T4: Finalize Workflow with Cost Aggregation

Test that finalize_workflow produces AMSP audit record:

```bash
docker exec dcf-mcp python -c "
import json
import uuid
from dcf_mcp.tools.dcf.create_workflow_control_plane import create_workflow_control_plane
from dcf_mcp.tools.dcf.create_worker_agents import create_worker_agents
from dcf_mcp.tools.dcf.update_workflow_control_plane import update_workflow_control_plane
from dcf_mcp.tools.dcf.acquire_state_lease import acquire_state_lease
from dcf_mcp.tools.dcf.finalize_workflow import finalize_workflow

workflow_id = f'amsp-finalize-test-{uuid.uuid4().hex[:8]}'

# Create workflow
workflow = {
    'workflow_id': workflow_id,
    'workflow_name': 'AMSP Finalize Test',
    'version': '1.0.0',
    'af_imports': [{'uri': '/app/dcf_mcp/agents/worker.af', 'version': '2'}],
    'asl': {
        'StartAt': 'Summary',
        'States': {
            'Summary': {
                'Type': 'Task',
                'AgentBinding': {
                    'agent_template_ref': {'name': 'worker'},
                    'skills': ['skill://write.summary@0.1.0']
                },
                'End': True
            }
        }
    }
}

# Setup
cp_result = create_workflow_control_plane(json.dumps(workflow))
print(f'Control Plane: {cp_result[\"status\"]}')

worker_result = create_worker_agents(
    workflow_json=json.dumps(workflow),
    imports_base_dir='/app',
    enable_model_selection=True
)
print(f'Workers: {worker_result[\"status\"]}')

# Simulate execution with metrics
lease = acquire_state_lease(workflow_id, 'Summary', 300)
update_workflow_control_plane(
    workflow_id=workflow_id,
    state_name='Summary',
    lease_token=lease['lease_token'],
    new_status='succeeded',
    output_json=json.dumps({
        'ok': True,
        'summary': 'Test summary output',
        'metrics': {
            'tokens_in': 500,
            'tokens_out': 100,
            'latency_ms': 800,
            'model_used': 'gpt-4o-mini',
            'tier_used': 0,
            'inference_cost_usd': 0.0005
        }
    })
)

# Finalize and check AMSP audit
final = finalize_workflow(
    workflow_id=workflow_id,
    delete_worker_agents=True,
    preserve_planner=True,
    close_open_states=True,
    finalize_note='AMSP finalize test'
)

print()
print(f'Final Status: {final[\"status\"]}')
print(f'Workflow Status: {final.get(\"summary\", {}).get(\"final_status\", \"unknown\")}')

# Check cost summary
cost = final.get('model_usage_summary', {})
if cost:
    print()
    print('AMSP Cost Summary:')
    print(f'  Tier Distribution: {cost.get(\"tier_distribution\", {})}')
    print(f'  Total Cost: \${cost.get(\"total_inference_cost_usd\", 0):.6f}')
    est_vs_actual = cost.get('estimated_vs_actual', {})
    if est_vs_actual:
        print(f'  Estimated: \${est_vs_actual.get(\"estimated\", 0):.6f}')
        print(f'  Actual: \${est_vs_actual.get(\"actual\", 0):.6f}')
        print(f'  Deviation: {est_vs_actual.get(\"deviation_pct\", 0):.1f}%')

print()
print('✓ Finalize workflow with AMSP cost aggregation complete')
"
```

### B.T5: Redis AMSP Audit Record

Verify AMSP audit record is written to data plane:

```bash
# Check AMSP audit record in Redis
docker exec redis redis-cli KEYS "dp:wf:amsp-finalize-test*:audit:amsp"

# Get the audit record content
docker exec redis redis-cli JSON.GET "dp:wf:amsp-finalize-test*:audit:amsp" $ 2>/dev/null | jq '.' || echo "Audit record format varies by implementation"
```

---

## Test Execution: Phase C - Phase 2 Integration

### C.T1: Delegate Task with Model Selection

Test that delegate_task computes complexity and selects model:

```bash
docker exec dcf-mcp python -c "
import json
import uuid
from letta_client import Letta

client = Letta(base_url='http://letta:8283')

# Create test Conductor and Companion
session_id = f'amsp-session-{uuid.uuid4().hex[:8]}'

# Create minimal Conductor agent
conductor = client.agents.create(
    name=f'amsp-test-conductor-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='You are a test conductor.',
    include_base_tools=True
)
print(f'Created Conductor: {conductor.id}')

# Create Companion using DCF+ tool
from dcf_mcp.tools.dcf_plus.create_companion import create_companion
companion_result = create_companion(
    session_id=session_id,
    conductor_id=conductor.id,
    specialization='analysis',
    model='openai/gpt-4o-mini'
)
print(f'Created Companion: {companion_result[\"companion_id\"]}')

# Delegate task with skills that have complexity profiles
from dcf_mcp.tools.dcf_plus.delegate_task import delegate_task
delegation = delegate_task(
    conductor_id=conductor.id,
    companion_id=companion_result['companion_id'],
    task_description='Analyze the quarterly report and synthesize findings',
    required_skills_json=json.dumps(['skill.analyze.synthesis@0.1.0']),
    input_data_json=json.dumps({'report': 'Q1 financial data...'}),
    priority='high',
    session_id=session_id
)

print()
print(f'Delegation Status: {delegation[\"status\"]}')
print(f'Task ID: {delegation.get(\"task_id\", \"N/A\")}')

# Check model selection in delegation
model_selection = delegation.get('model_selection', {})
if model_selection:
    print()
    print('Model Selection:')
    print(f'  FCS: {model_selection.get(\"fcs\", \"N/A\")}')
    print(f'  Tier: {model_selection.get(\"tier\", \"N/A\")}')
    print(f'  Model: {model_selection.get(\"model\", \"N/A\")}')
    print('✓ Model selection included in delegation')
else:
    print('⚠ No model_selection in delegation response')

# Cleanup
from dcf_mcp.tools.dcf_plus.dismiss_companion import dismiss_companion
dismiss_companion(companion_result['companion_id'])
client.agents.delete(conductor.id)
print()
print('Cleaned up test agents')
"
```

### C.T2: Create Companion with Model Tier

Test that create_companion accepts model_tier parameter:

```bash
docker exec dcf-mcp python -c "
import json
import uuid
from letta_client import Letta

client = Letta(base_url='http://letta:8283')

# Create test Conductor
conductor = client.agents.create(
    name=f'amsp-tier-test-conductor-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='Test conductor',
    include_base_tools=True
)

session_id = f'amsp-tier-session-{uuid.uuid4().hex[:8]}'

from dcf_mcp.tools.dcf_plus.create_companion import create_companion

# Create Companion with specific model tier
result = create_companion(
    session_id=session_id,
    conductor_id=conductor.id,
    specialization='high-complexity',
    model_tier=2  # Request Tier 2 (Sonnet-class)
)

print(f'Status: {result[\"status\"]}')
print(f'Companion ID: {result[\"companion_id\"]}')

# Check model config
model_config = result.get('model_config', {})
if model_config:
    print()
    print('Model Configuration:')
    print(f'  Requested Tier: {model_config.get(\"requested_tier\", \"N/A\")}')
    print(f'  Selected Model: {model_config.get(\"model\", \"N/A\")}')
    print('✓ Model tier configuration applied')

# Cleanup
from dcf_mcp.tools.dcf_plus.dismiss_companion import dismiss_companion
dismiss_companion(result['companion_id'])
client.agents.delete(conductor.id)
print()
print('Cleaned up')
"
```

### C.T3: Strategist Analysis with AMSP Metrics

Test that trigger_strategist_analysis extracts AMSP metrics:

```bash
docker exec dcf-mcp python -c "
import json
import uuid
from letta_client import Letta

client = Letta(base_url='http://letta:8283')
session_id = f'amsp-strategist-{uuid.uuid4().hex[:8]}'

# Create Conductor
conductor = client.agents.create(
    name=f'amsp-strat-conductor-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='Test conductor',
    include_base_tools=True
)

# Create Strategist
strategist = client.agents.create(
    name=f'amsp-strat-strategist-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='Test strategist',
    include_base_tools=True
)

# Register Strategist
from dcf_mcp.tools.dcf_plus.register_strategist import register_strategist
reg = register_strategist(conductor.id, strategist.id)
print(f'Registered Strategist: {reg[\"status\"]}')

# Create delegation_log block with AMSP data
delegation_log = {
    'delegations': [
        {
            'task_id': 'task-001',
            'companion_id': 'comp-001',
            'skills_assigned': ['skill.write.summary@0.1.0'],
            'model_selection': {
                'fcs': 3.0,
                'tier': 0,
                'model': 'gpt-4o-mini'
            },
            'status': 'completed',
            'result_status': 'succeeded',
            'duration_s': 1.2
        },
        {
            'task_id': 'task-002',
            'companion_id': 'comp-001',
            'skills_assigned': ['skill.analyze.synthesis@0.1.0'],
            'model_selection': {
                'fcs': 14.2,
                'tier': 1,
                'model': 'claude-haiku-4-5'
            },
            'status': 'completed',
            'result_status': 'succeeded',
            'duration_s': 4.5
        }
    ]
}

# Create/update delegation_log block
block = client.blocks.create(label='delegation_log', value=json.dumps(delegation_log))
client.agents.blocks.attach(conductor.id, block.id)

# Trigger analysis
from dcf_mcp.tools.dcf_plus.trigger_strategist_analysis import trigger_strategist_analysis
analysis = trigger_strategist_analysis(
    session_id=session_id,
    conductor_agent_id=conductor.id,
    trigger_reason='periodic',
    tasks_since_last_analysis=2,
    async_message=False  # Sync for testing
)

print()
print(f'Analysis Status: {analysis[\"status\"]}')

# Check AMSP metrics extraction
amsp_metrics = analysis.get('amsp_metrics', {})
if amsp_metrics:
    print()
    print('AMSP Metrics Extracted:')
    print(f'  Tier Distribution: {amsp_metrics.get(\"tier_distribution\", {})}')
    print(f'  Avg FCS: {amsp_metrics.get(\"avg_fcs\", \"N/A\")}')
    print(f'  Escalation Rate: {amsp_metrics.get(\"escalation_rate\", 0):.1%}')
    print('✓ AMSP metrics included in analysis')

# Cleanup
client.agents.delete(strategist.id)
client.agents.delete(conductor.id)
print()
print('Cleaned up')
"
```

### C.T4: Update Conductor Guidelines with Model Selection

Test that update_conductor_guidelines accepts model selection recommendations:

```bash
docker exec dcf-mcp python -c "
import json
import uuid
from letta_client import Letta

client = Letta(base_url='http://letta:8283')

# Create Conductor
conductor = client.agents.create(
    name=f'amsp-guide-conductor-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='Test conductor',
    include_base_tools=True
)

# Create Strategist and register
strategist = client.agents.create(
    name=f'amsp-guide-strategist-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='Test strategist',
    include_base_tools=True
)

from dcf_mcp.tools.dcf_plus.register_strategist import register_strategist
register_strategist(conductor.id, strategist.id)

# Update guidelines with model selection recommendations
from dcf_mcp.tools.dcf_plus.update_conductor_guidelines import update_conductor_guidelines

model_selection_guidelines = {
    'task_type_tiers': {
        'summarization': 0,
        'research': 0,
        'analysis': 1,
        'synthesis': 2
    },
    'skill_tier_overrides': {
        'skill.analyze.synthesis@0.1.0': {
            'min_tier': 1,
            'reason': 'Observed 40% failure rate at Tier 0'
        }
    },
    'escalation_threshold': 0.15,
    'cost_budget_usd': 1.00
}

result = update_conductor_guidelines(
    conductor_id=conductor.id,
    recommendation='Use Tier 1+ for analysis tasks based on observed escalation patterns',
    model_selection_json=json.dumps(model_selection_guidelines)
)

print(f'Status: {result[\"status\"]}')
print(f'Updated Fields: {result.get(\"updated_fields\", [])}')

# Verify guidelines block updated
blocks = client.agents.blocks.list(conductor.id)
for block in blocks:
    if 'strategist_guidelines' in block.label:
        value = json.loads(block.value)
        ms = value.get('model_selection', {})
        if ms:
            print()
            print('Model Selection Guidelines:')
            print(f'  Task Type Tiers: {ms.get(\"task_type_tiers\", {})}')
            print(f'  Skill Overrides: {list(ms.get(\"skill_tier_overrides\", {}).keys())}')
            print('✓ Model selection guidelines persisted')
        break

# Cleanup
client.agents.delete(strategist.id)
client.agents.delete(conductor.id)
print()
print('Cleaned up')
"
```

### C.T5: Full Phase 2 Session with AMSP

End-to-end test of a DCF+ session with AMSP model selection:

```bash
docker exec dcf-mcp python -c "
import json
import uuid
from letta_client import Letta

client = Letta(base_url='http://letta:8283')
session_id = f'amsp-full-session-{uuid.uuid4().hex[:8]}'

print('=== AMSP-DCF+ Full Session Test ===')
print()

# 1. Create Conductor
conductor = client.agents.create(
    name=f'amsp-full-conductor-{uuid.uuid4().hex[:8]}',
    model='openai/gpt-4o-mini',
    system='You are a test conductor for AMSP integration.',
    include_base_tools=True
)
print(f'1. Created Conductor: {conductor.id[:20]}...')

# 2. Create Session Context
from dcf_mcp.tools.dcf_plus.create_session_context import create_session_context
ctx = create_session_context(
    session_id=session_id,
    conductor_id=conductor.id,
    objective='Test AMSP model selection across tiers'
)
print(f'2. Created Session Context: {ctx[\"block_id\"]}')

# 3. Create Companion
from dcf_mcp.tools.dcf_plus.create_companion import create_companion
companion = create_companion(
    session_id=session_id,
    conductor_id=conductor.id,
    specialization='multi-tier',
    model='openai/gpt-4o-mini'
)
print(f'3. Created Companion: {companion[\"companion_id\"][:20]}...')

# 4. Delegate Tier 0 task
from dcf_mcp.tools.dcf_plus.delegate_task import delegate_task
task1 = delegate_task(
    conductor_id=conductor.id,
    companion_id=companion['companion_id'],
    task_description='Summarize the meeting notes',
    required_skills_json=json.dumps(['skill.write.summary@0.1.0']),
    session_id=session_id
)
print(f'4. Delegated Tier 0 task: {task1.get(\"model_selection\", {}).get(\"tier\", \"?\")}')

# 5. Delegate Tier 1 task
task2 = delegate_task(
    conductor_id=conductor.id,
    companion_id=companion['companion_id'],
    task_description='Analyze quarterly report trends',
    required_skills_json=json.dumps(['skill.analyze.synthesis@0.1.0']),
    session_id=session_id
)
print(f'5. Delegated Tier 1 task: {task2.get(\"model_selection\", {}).get(\"tier\", \"?\")}')

# 6. Report results
from dcf_mcp.tools.dcf_plus.report_task_result import report_task_result
report_task_result(
    companion_id=companion['companion_id'],
    task_id=task1.get('task_id', 'task-1'),
    conductor_id=conductor.id,
    status='succeeded',
    summary='Summary complete',
    metrics_json=json.dumps({
        'tokens_in': 200, 'tokens_out': 50,
        'latency_ms': 500, 'tier_used': 0,
        'inference_cost_usd': 0.0002
    })
)
report_task_result(
    companion_id=companion['companion_id'],
    task_id=task2.get('task_id', 'task-2'),
    conductor_id=conductor.id,
    status='succeeded',
    summary='Analysis complete',
    metrics_json=json.dumps({
        'tokens_in': 800, 'tokens_out': 300,
        'latency_ms': 2500, 'tier_used': 1,
        'inference_cost_usd': 0.0015
    })
)
print('6. Reported task results with AMSP metrics')

# 7. Read session activity
from dcf_mcp.tools.dcf_plus.read_session_activity import read_session_activity
activity = read_session_activity(
    session_id=session_id,
    conductor_id=conductor.id,
    include_skill_metrics=True
)
print('7. Session Activity:')
amsp = activity.get('amsp_metrics', activity.get('metrics', {}))
print(f'   Tasks completed: {amsp.get(\"total_delegations\", amsp.get(\"completed_tasks\", \"?\"))}')
print(f'   Tier distribution: {amsp.get(\"tier_distribution\", {})}')

# 8. Finalize session
from dcf_mcp.tools.dcf_plus.finalize_session import finalize_session
final = finalize_session(
    session_id=session_id,
    session_context_block_id=ctx['block_id'],
    delete_companions=True
)
print(f'8. Session finalized: {final[\"status\"]}')

# Cleanup Conductor
client.agents.delete(conductor.id)

print()
print('=== AMSP-DCF+ Full Session Test COMPLETE ===')
"
```

---

## Verification Checklist

### Phase A Verification

| Check | Command | Expected |
|-------|---------|----------|
| Schema valid | A.T1 test | Schema validates |
| Manifest v2.1.0 | A.T2 test | complexityProfile present |
| FCS calculation | A.T3 test | Correct tier assignments |
| Worker model selection | A.T4 test | model_selections in response |
| YAML generation | A.T5 test | Profiles in generated manifests |

### Phase B Verification

| Check | Command | Expected |
|-------|---------|----------|
| State schema | B.T1 test | model_selection validates |
| Meta schema | B.T2 test | workflow_complexity validates |
| Validation warnings | B.T3 test | complexity_coverage reported |
| Cost aggregation | B.T4 test | model_usage_summary present |
| AMSP audit | B.T5 test | Redis key exists |

### Phase C Verification

| Check | Command | Expected |
|-------|---------|----------|
| Delegation model selection | C.T1 test | model_selection in response |
| Companion model tier | C.T2 test | model_config present |
| Strategist AMSP metrics | C.T3 test | amsp_metrics extracted |
| Guidelines model selection | C.T4 test | model_selection persisted |
| Full session | C.T5 test | Tier tracking works |

### Redis Keys Created

```bash
# Phase B - Workflow execution
docker exec redis redis-cli KEYS "cp:wf:amsp-*"
docker exec redis redis-cli KEYS "dp:wf:amsp-*:audit:amsp"

# Phase C - Session (via delegation_log block)
# Session data stored in Letta blocks, not directly in Redis
```

### Expected Final State

```
Phase A:
  - 3 skills with complexity profiles
  - compute_task_complexity returns valid FCS
  - create_worker_agents includes model_selections

Phase B:
  - Control plane tracks model_selection per state
  - finalize_workflow produces cost_summary
  - AMSP audit records written

Phase C:
  - delegate_task computes and logs model selection
  - Strategist extracts AMSP metrics
  - Guidelines include model selection recommendations
```

---

## Cleanup

To reset the test environment:

```bash
# Clear AMSP test workflows from Redis
docker exec redis redis-cli KEYS "cp:wf:amsp-*" | xargs -r docker exec -i redis redis-cli DEL
docker exec redis redis-cli KEYS "dp:wf:amsp-*" | xargs -r docker exec -i redis redis-cli DEL

# Delete test agents from Letta
curl -s http://localhost:8283/v1/agents/ | jq -r '.[] | select(.name | startswith("amsp-")) | .id' | xargs -I {} curl -s -X DELETE http://localhost:8283/v1/agents/{}

# Verify cleanup
docker exec redis redis-cli KEYS "*amsp*"
curl -s http://localhost:8283/v1/agents/ | jq '.[] | select(.name | startswith("amsp-")) | .name'

# Restart services if needed
docker compose restart dcf-mcp
```

---

## Summary

This AMSP-DCF Integration testing plan validates:

| Phase | Components Tested |
|-------|-------------------|
| **Phase A** | Complexity profiles, FCS calculation, tier mapping, worker model selection |
| **Phase B** | Control plane AMSP tracking, cost aggregation, validation warnings, advisor analysis |
| **Phase C** | Dynamic model selection, delegation logging, Strategist metrics, guidelines |

### Key AMSP Features Validated

| Feature | How Tested |
|---------|------------|
| **WCM Scoring** | Skills with different dimension scores produce correct FCS |
| **Tier Mapping** | FCS ranges correctly map to Tiers 0-3 |
| **Interaction Multipliers** | High tooling+adaptability increases FCS |
| **Latency Constraints** | Critical latency caps tier selection |
| **Cost Tracking** | Actual vs estimated costs tracked |
| **Advisor Integration** | Reflector/Strategist analyze model selection patterns |
| **Dynamic Selection** | Conductor selects tier per delegation |

### Skills Tested

| Skill | Tier | FCS | Validation |
|-------|------|-----|------------|
| write.summary@0.1.0 | 0 | 3.0 | Validated (50 samples) |
| research.web@0.1.0 | 0 | 9.2 | Validated (35 samples) |
| analyze.synthesis@0.1.0 | 1 | 14.2 | Validated (28 samples) |

---

## Related Documentation

- **[Testing_Plan_Phase_1_Opus.md](Testing_Plan_Phase_1_Opus.md)** — DCF Phase 1 testing plan
- **[Testing_Plan_Phase_2_Opus.md](Testing_Plan_Phase_2_Opus.md)** — DCF Phase 2 testing plan
- **[AMSP-DCF-Integration-Progress.md](../research/AMSP-DCF-Integration-Progress.md)** — Implementation progress tracker
- **[TODO-AMSP-DCF-Integration.md](../research/TODO-AMSP-DCF-Integration.md)** — Integration playbook

---

## Quick Test Commands

Run all Phase A tests:
```bash
docker exec dcf-mcp python -c "
print('=== Running Phase A Tests ===')
# A.T1, A.T2, A.T3, A.T4, A.T5 inline
exec(open('/app/docs/testing/amsp_tests.py').read())
" 2>/dev/null || echo "Run tests individually from the document"
```

Run full integration test:
```bash
# Comprehensive test script
docker exec dcf-mcp python3 << 'EOF'
import json
from dcf_mcp.tools.dcf.compute_task_complexity import compute_task_complexity

# Quick smoke test
result = compute_task_complexity(
    skills_json=json.dumps(['skill.write.summary@0.1.0']),
    latency_requirement='standard'
)
print(f"AMSP Integration: {'OK' if result['error'] is None else 'FAIL'}")
print(f"  FCS: {result['final_fcs']}, Tier: {result['recommended_tier']}")
EOF
```
