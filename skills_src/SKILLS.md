# DCF Skills Authoring & Simulation Guide

This document explains the skill simulation and authoring infrastructure for the Dynamic Capabilities Framework (DCF). It covers the complete testing methodology, from YAML authoring through artifact generation to runtime simulation.

## Overview

The DCF skill system enables agents to dynamically load and unload capabilities at runtime. Skills are defined as declarative manifests that specify:

- **Directives**: Behavioral instructions for the agent
- **Tools**: MCP tools the skill requires
- **Data Sources**: Context injected into agent memory
- **Permissions**: Network access and secret requirements

### Testing Methodology

The DCF testing infrastructure provides **deterministic, reproducible testing** of agent workflows without requiring real external services. The methodology follows this flow:

1. **Author** skills and tool specifications in YAML format
2. **Generate** JSON manifests and stub server configuration
3. **Simulate** tool responses via the stub MCP server
4. **Execute** agent workflows with predictable, verifiable outcomes
5. **Validate** results against expected test case responses

This approach enables:
- **Isolation**: Tests run without network dependencies
- **Determinism**: Same inputs always produce same outputs
- **Speed**: No external API latency
- **Coverage**: Error scenarios and edge cases can be explicitly tested

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      AUTHORING LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│  skills_src/                                                    │
│  ├── skills/*.skill.yaml    # Individual skill definitions      │
│  ├── tools.yaml             # Tool specs + test cases           │
│  ├── registry.yaml          # Server endpoint mappings          │
│  └── schemas/               # YAML schema documentation         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GENERATION LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│  dcf_mcp/tools/dcf/                                            │
│  ├── generate.py            # Unified generator                 │
│  ├── yaml_to_manifests.py   # YAML → JSON manifests            │
│  └── yaml_to_stub_config.py # YAML → stub config               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GENERATED ARTIFACTS                         │
├─────────────────────────────────────────────────────────────────┤
│  generated/                                                     │
│  ├── manifests/*.json       # Skill manifest files             │
│  ├── catalogs/skills_catalog.json  # Discovery index           │
│  └── stub/stub_config.json  # Stub MCP server config           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RUNTIME LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  stub_mcp/stub_mcp_server.py   # Deterministic test server     │
│  dcf_mcp/tools/dcf/load_skill.py    # Skill loader             │
│  dcf_mcp/tools/dcf/unload_skill.py  # Skill unloader           │
│  dcf_mcp/tools/dcf/get_skillset.py  # Skill discovery          │
└─────────────────────────────────────────────────────────────────┘
```

### Two-Schema Architecture

The DCF skill system uses **two distinct schemas** optimized for different stages of the skill lifecycle:

| Schema | Location | Purpose | Format |
|--------|----------|---------|--------|
| **YAML Authoring Schema** | `skills_src/schemas/skill.schema.yaml` | Human-friendly skill authoring | Documentation (not yet enforceable) |
| **JSON Runtime Schema** | `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json` | Runtime validation & loading | JSON Schema 2020-12 (machine-enforceable) |

**Why two schemas?**

1. **Authoring (YAML)**: Optimized for humans writing skills
   - Compact tool references: `ref: search:search_query`
   - File-based data sources: `file: ./data/guidelines.txt`
   - Kubernetes-style structure: `apiVersion`, `kind`, `metadata`, `spec`
   - Future features: skill dependencies

2. **Runtime (JSON)**: Optimized for machine processing
   - Full tool definitions with embedded JSON schemas
   - Inline content only (files resolved at generation time)
   - Flat structure matching Letta agent requirements
   - Strict validation for reliable skill loading

**The generator bridges these schemas:**

```
┌──────────────────┐                         ┌──────────────────┐
│  .skill.yaml     │   yaml_to_manifests()   │  manifest.json   │
│  (authoring)     │ ──────────────────────▶ │  (runtime)       │
│                  │                         │                  │
│  Human-friendly  │   + tools.yaml for      │  Machine-ready   │
│  shorthand       │     schema enrichment   │  full definition │
└──────────────────┘                         └──────────────────┘
```

See [Schema Transformation Details](#schema-transformation-details) for a complete comparison.

## Quick Start

### Using the CLI (Recommended)

The `skill` CLI provides commands for all common operations:

```bash
# Install the CLI (from project root)
pip install -e .

# Create a new skill interactively
skill init

# Or with options
skill init my.skill --template research --egress internet

# Validate all skills
skill validate

# Generate manifests and stub config
skill generate

# List all skills
skill list

# Run tests against stub server
skill test
```

See [CLI Reference](#cli-reference) for detailed command documentation.

### Manual Approach

### 1. Create a New Skill

Create a file `skills_src/skills/my.skill.skill.yaml`:

```yaml
apiVersion: skill/v1
kind: Skill

metadata:
  manifestId: skill.my.skill@0.1.0
  name: my.skill
  version: 0.1.0
  description: My custom skill
  tags: [custom, example]

spec:
  permissions:
    egress: none
    secrets: []

  directives: |
    Follow user instructions precisely.
    Provide clear, structured output.

  tools:
    - ref: llm:llm_summarize
      required: true
      description: Summarize content
```

### 2. Generate Artifacts

```bash
# Inside Docker container
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'

# Or using environment variables
SKILLS_SRC_DIR=/app/skills_src GENERATED_DIR=/app/generated python -m dcf_mcp.tools.dcf.generate
```

### 3. Load the Skill

```python
from dcf_mcp.tools.dcf.load_skill import load_skill

result = load_skill(
    skill_manifest="generated/manifests/skill.my.skill-0.1.0.json",
    agent_id="your-agent-id"
)
```

---

## File Formats

### Skill Definition (`.skill.yaml`)

Each skill is defined in a separate YAML file under `skills_src/skills/`.

```yaml
# Required header
apiVersion: skill/v1
kind: Skill

# Skill metadata
metadata:
  manifestId: skill.research.web@0.1.0   # Unique ID: skill.<domain>.<name>@<semver>
  name: research.web                      # Dot-separated name
  version: 0.1.0                          # Semantic version
  description: Lightweight web research   # Human-readable description
  tags: [research, web]                   # Categorization tags

# Skill specification
spec:
  # Network and security permissions
  permissions:
    egress: internet          # none | intranet | internet
    secrets: [BING_API_KEY]   # Required API keys/secrets

  # Behavioral directives for the agent
  directives: |
    Follow queries precisely.
    Extract key facts from search results.
    Provide citations with source URLs.

  # Required MCP tools
  tools:
    - ref: search:search_query    # Format: serverId:toolName
      required: true              # Is this tool mandatory?
      description: Core search    # How this tool is used

    - ref: web:web_fetch
      required: false             # Optional tools marked false

  # Data sources injected into agent memory
  dataSources:
    - id: guidelines              # Unique ID within skill
      description: Usage notes    # What this contains
      destination: archival_memory  # Where to inject
      text: |                     # Inline content
        Always cite your sources.
        Use bullet points for clarity.

    # Alternative: load from file
    - id: reference
      file: ./data/reference.txt  # Relative to skill file
```

### Tools Registry (`tools.yaml`)

Defines tool specifications and test cases for simulation.

```yaml
apiVersion: tools/v1
kind: ToolsRegistry

servers:
  # Server ID (referenced in skill tool refs)
  search:
    description: Search and discovery tools

    tools:
      # Tool name
      search_query:
        version: 0.1.0
        description: Web search query tool

        # Input parameters (JSON Schema)
        params:
          type: object
          properties:
            q:
              type: string
              description: Search query
          required: [q]

        # Output schema (optional)
        result:
          type: object
          properties:
            hits:
              type: array
              items:
                type: object
                properties:
                  title: { type: string }
                  url: { type: string }

        # Simulation defaults
        defaults:
          response: { hits: [] }    # Default when no case matches
          latencyMs: 150            # Simulated latency
          rateLimit: { rps: 2 }     # Rate limiting

        # Test cases for deterministic responses
        cases:
          - id: case_python
            match:
              strategy: exact       # Match strategy
              path: q               # Path to value
              value: python         # Expected value
            response:
              hits:
                - title: Python.org
                  url: https://python.org

          - id: case_any_query
            match:
              strategy: always      # Always matches (fallback)
            response:
              hits:
                - title: "Search result for: {{ q }}"
                  url: "https://search.example?q={{ q }}"
              generated_at: "{{ now_iso }}"
```

### Server Registry (`registry.yaml`)

Maps logical server IDs to actual MCP endpoints. In test mode, all servers point to the stub MCP server for deterministic simulation.

**Current Servers:**

| Server ID | Purpose | Tools |
|-----------|---------|-------|
| `search` | Web and news search | `search_query`, `news_headlines` |
| `web` | Web content fetching | `web_fetch` |
| `llm` | LLM operations | `llm_summarize`, `llm_qa` |
| `datasets` | Dataset access | `load_dataset`, `query_dataset` |
| `analysis` | Data analysis | `analyze_sentiment`, `extract_entities` |
| `orders` | Order validation (Phase 1) | `verify_customer`, `check_inventory`, `validate_address` |
| `pricing` | Pricing calculation (Phase 1) | `calculate_subtotal`, `apply_discount`, `calculate_tax`, `calculate_shipping` |
| `documents` | Document generation (Phase 1) | `create_invoice` |
| `support` | Customer support (Phase 2) | `get_customer_profile`, `get_interaction_history`, `search_known_issues`, `check_system_status`, `analyze_account_logs`, `get_response_templates` |

```yaml
apiVersion: registry/v1
kind: ServerRegistry

env: test   # test | staging | production

servers:
  # Core research servers
  search:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  web:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  llm:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  # Phase 1 Testing - Order Processing
  orders:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  pricing:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  documents:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  # Phase 2 Testing - Customer Support
  support:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

# Production overrides (example)
# overrides:
#   production:
#     search:
#       endpoint: https://api.bing.microsoft.com
#       headers:
#         Ocp-Apim-Subscription-Key: ${BING_API_KEY}
```

**Important**: When adding new skills that reference new servers, you must add the server to `registry.yaml` before regenerating artifacts.

---

## Matching Strategies

The stub server supports several strategies for matching test cases:

| Strategy | Description | Example |
|----------|-------------|---------|
| `exact` | Exact string match | `match: { strategy: exact, path: q, value: python }` |
| `regex` | Regex on JSON-serialized args | `match: { strategy: regex, path: q, value: ".*robot.*" }` |
| `contains` | Substring match | `match: { strategy: contains, path: q, value: AI }` |
| `always` | Always matches (fallback) | `match: { strategy: always }` |
| `jsonpath` | JSONPath expression | `match: { strategy: jsonpath, path: data.items[0], value: "test" }` |

### Matching Priority

Cases are matched in order of:
1. **Weight** (higher weight = higher priority)
2. **Definition order** (first match wins if weights are equal)

```yaml
cases:
  - id: specific_case
    weight: 100           # Checked first
    match: { strategy: exact, path: q, value: "specific query" }
    response: { ... }

  - id: fallback_case
    weight: 0             # Checked last
    match: { strategy: always }
    response: { ... }
```

---

## Response Templating

The stub server supports dynamic response generation using templates.

### Template Variables

| Variable | Description | Example Output |
|----------|-------------|----------------|
| `{{ now_iso }}` | Current ISO timestamp | `2025-01-28T10:30:00+00:00` |
| `{{ uuid }}` | Random UUID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `{{ random_int(min, max) }}` | Random integer | `42` |
| `{{ args.param }}` or `{{ param }}` | Input argument | Value from request |

### Example Usage

```yaml
cases:
  - id: dynamic_response
    match: { strategy: always }
    response:
      requestId: "{{ uuid }}"
      timestamp: "{{ now_iso }}"
      query: "{{ q }}"
      results:
        - title: "Result for {{ q }}"
          relevance: "{{ random_int(70, 100) }}"
```

---

## Error Injection

Test error handling with built-in error modes:

```yaml
cases:
  - id: timeout_case
    match: { strategy: exact, path: q, value: "slow query" }
    errorMode: timeout      # Sleep 10s then timeout

  - id: error_case
    match: { strategy: exact, path: q, value: "bad query" }
    errorMode: throw        # Return error response

  - id: server_error
    match: { strategy: exact, path: q, value: "crash" }
    errorMode: http_500     # Return 500 error

  - id: flaky_case
    match: { strategy: exact, path: q, value: "unreliable" }
    errorMode: flaky        # Random failures
    flakyRate: 0.3          # 30% failure rate
```

---

## Metrics Endpoint

The stub server exposes metrics for monitoring test coverage:

```bash
# Get current metrics
curl http://localhost:8765/metrics

# Response:
{
  "ok": true,
  "metrics": {
    "tool_calls": { "search_query": 15, "web_fetch": 8 },
    "case_hits": { "search:search_query:case_python": 5 },
    "errors": { "flaky": 2 }
  },
  "totals": {
    "tool_calls": 23,
    "case_hits": 23,
    "errors": 2
  }
}

# Reset metrics
curl -X POST http://localhost:8765/metrics/reset
```

---

## Artifact Generation

### Generated Artifacts

The generation pipeline produces three types of artifacts:

#### 1. Skill Manifests (`generated/manifests/*.json`)

JSON files consumed by `load_skill()` at runtime. Each manifest contains:

| Field | Description |
|-------|-------------|
| `manifestId` | Unique identifier: `skill.<domain>.<name>@<version>` |
| `skillName` | Dot-separated skill name |
| `skillVersion` | Semantic version |
| `skillDirectives` | Agent behavioral instructions |
| `requiredTools` | Array of tool definitions with full JSON schemas |
| `requiredDataSources` | Context injected into agent memory |
| `permissions` | Network egress and secret requirements |

**Tool Definition Expansion:**

YAML compact reference:
```yaml
- ref: orders:verify_customer
  required: true
```

Expands to full definition in JSON:
```json
{
  "toolName": "verify_customer",
  "json_schema": {
    "name": "verify_customer",
    "parameters": { ... }
  },
  "definition": {
    "type": "mcp_server",
    "serverId": "orders",
    "toolName": "verify_customer"
  },
  "required": true
}
```

#### 2. Skills Catalog (`generated/catalogs/skills_catalog.json`)

Index file used by `get_skillset()` for skill discovery:

```json
{
  "skills": [
    {
      "manifestId": "skill.validate.order@0.1.0",
      "skillName": "validate.order",
      "skillVersion": "0.1.0",
      "path": "generated/manifests/skill.validate.order-0.1.0.json"
    }
  ]
}
```

#### 3. Stub Configuration (`generated/stub/stub_config.json`)

Configuration for the stub MCP server, containing all tool definitions and test cases:

```json
{
  "servers": {
    "orders": {
      "tools": {
        "verify_customer": {
          "version": "0.1.0",
          "description": "...",
          "paramsSchema": { ... },
          "resultSchema": { ... },
          "defaultResponse": { ... },
          "latencyMs": { "default": 100 },
          "rateLimit": { "rps": 5 },
          "cases": [ ... ]
        }
      }
    }
  }
}
```

### Generation Commands

#### Unified Generator (Recommended)

```python
from dcf_mcp.tools.dcf.generate import generate_all

# Generate everything
result = generate_all()

# Custom paths (useful outside Docker)
result = generate_all(
    skills_src_dir="/Users/me/project/skills_src",
    generated_dir="/Users/me/project/generated"
)

# Result:
# {
#   "ok": True,
#   "manifests_result": { "ok": True, "manifests": [...] },
#   "stub_config_result": { "ok": True, "tool_count": 24, "case_count": 54 },
#   "summary": "Generated: 15 skill manifest(s), 24 tool(s) with 54 case(s)"
# }
```

#### Individual Generators

```python
from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests
from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config

# Generate only manifests
yaml_to_manifests(
    skills_dir="/path/to/skills_src/skills",
    tools_yaml_path="/path/to/skills_src/tools.yaml",
    out_dir="/path/to/generated/manifests",
    catalog_path="/path/to/generated/catalogs/skills_catalog.json"
)

# Generate only stub config
yaml_to_stub_config(
    tools_yaml_path="/path/to/skills_src/tools.yaml",
    out_path="/path/to/generated/stub/stub_config.json"
)
```

#### Docker vs Local Paths

Default paths are configured for Docker (`/app/skills_src`, `/app/generated`). When running locally:

```python
# Local development
from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests
from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config

yaml_to_manifests(
    skills_dir="./skills_src/skills",
    tools_yaml_path="./skills_src/tools.yaml",
    out_dir="./generated/manifests",
    catalog_path="./generated/catalogs/skills_catalog.json"
)

yaml_to_stub_config(
    tools_yaml_path="./skills_src/tools.yaml",
    out_path="./generated/stub/stub_config.json"
)
```

---

## Directory Structure

```
skills_src/
├── SKILLS.md                   # This documentation
├── tools.yaml                  # Tool specifications + test cases (24 tools)
├── registry.yaml               # Server endpoint mappings (9 servers)
├── skills/                     # Individual skill definitions (15 skills)
│   │
│   │ # Research & Analysis Skills
│   ├── research.web.skill.yaml
│   ├── research.news.skill.yaml
│   ├── research.company.skill.yaml
│   ├── analyze.synthesis.skill.yaml
│   │
│   │ # Planning & QA Skills
│   ├── plan.actions.skill.yaml
│   ├── plan.research_scope.skill.yaml
│   ├── qa.review.skill.yaml
│   │
│   │ # Writing Skills
│   ├── write.summary.skill.yaml
│   ├── write.briefing.skill.yaml
│   │
│   │ # Phase 1 Testing: Order Processing Pipeline
│   ├── validate.order.skill.yaml      # orders server tools
│   ├── calculate.pricing.skill.yaml   # pricing server tools
│   ├── generate.invoice.skill.yaml    # documents server tools
│   │
│   │ # Phase 2 Testing: Customer Support Session
│   ├── lookup.customer.skill.yaml     # support server tools
│   ├── diagnose.issue.skill.yaml      # support server tools
│   └── compose.response.skill.yaml    # support server tools
│
└── schemas/                    # YAML schema documentation
    ├── skill.schema.yaml
    ├── tools.schema.yaml
    └── registry.schema.yaml

generated/
├── manifests/                  # Generated skill manifests (15 files)
│   ├── skill.research.web-0.1.0.json
│   ├── skill.validate.order-0.1.0.json
│   └── ...
├── catalogs/
│   └── skills_catalog.json     # Discovery index for get_skillset()
└── stub/
    └── stub_config.json        # Stub MCP server configuration
```

---

## Testing Infrastructure

### The Stub MCP Server

The stub MCP server (`stub_mcp/stub_mcp_server.py`) provides deterministic tool simulation for testing agent workflows. It:

1. **Loads configuration** from `generated/stub/stub_config.json` at startup
2. **Hot-reloads** configuration when the file changes (no restart needed)
3. **Matches test cases** against tool arguments using configurable strategies
4. **Processes templates** in responses for dynamic values
5. **Simulates latency** and rate limits as specified
6. **Injects errors** for testing error handling paths

**Docker Compose Configuration:**
```yaml
stub-mcp:
  build: ./stub_mcp
  ports:
    - "8765:8765"
  volumes:
    - ./generated:/app/generated:ro
  environment:
    - STUB_CONFIG=/app/generated/stub/stub_config.json
```

**Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp` | POST | MCP Streamable HTTP transport |
| `/healthz` | GET | Health check (`{"ok": true}`) |
| `/metrics` | GET | Tool call and case hit statistics |
| `/metrics/reset` | POST | Reset metrics counters |

### Testing Scenarios

The project includes two complete testing scenarios:

#### Phase 1: Order Processing Pipeline (Workflow Execution)

Tests the Planner → Worker → Reflector pattern with a three-stage workflow:

| Stage | Skill | Server | Tools |
|-------|-------|--------|-------|
| 1 | `validate.order` | orders | `verify_customer`, `check_inventory`, `validate_address` |
| 2 | `calculate.pricing` | pricing | `calculate_subtotal`, `apply_discount`, `calculate_tax`, `calculate_shipping` |
| 3 | `generate.invoice` | documents | `create_invoice` |

**Test Flow:**
1. Planner compiles workflow from skill requirements
2. Workers execute sequentially with Redis coordination
3. Reflector analyzes execution outcomes

#### Phase 2: Customer Support Session (Delegated Execution)

Tests the Conductor → Companion → Strategist pattern with parallel task handling:

| Task | Skill | Server | Tools |
|------|-------|--------|-------|
| Lookup | `lookup.customer` | support | `get_customer_profile`, `get_interaction_history` |
| Diagnose | `diagnose.issue` | support | `search_known_issues`, `check_system_status`, `analyze_account_logs` |
| Respond | `compose.response` | support | `get_response_templates` |

**Test Flow:**
1. Conductor creates Companions with skill assignments
2. Companions execute tasks concurrently
3. Strategist observes and provides optimization guidelines

### Designing Test Cases

Test cases in `tools.yaml` define how the stub server responds to specific inputs:

```yaml
cases:
  - id: happy_path           # Unique case identifier
    match:
      strategy: exact        # Matching strategy
      path: customer_id      # Parameter path to match
      value: "CUST-1234"     # Expected value
    response:                # Response when matched
      status: "active"
      name: "Jane Smith"

  - id: not_found
    match:
      strategy: regex
      path: customer_id
      value: "UNKNOWN-.*"
    response:
      status: "not_found"
      error: "Customer not found"

  - id: fallback
    match:
      strategy: always       # Matches any input
    response:
      status: "active"
      name: "Default Customer"
```

**Best Practices:**
1. Include a happy path case with realistic data
2. Add error cases (not found, validation failure, etc.)
3. Always include a fallback (`strategy: always`) case
4. Use `weight` to prioritize specific cases over general ones
5. Test template variables work correctly (`{{ uuid }}`, `{{ now_iso }}`)

### JSON Schema Requirements

The stub MCP server validates tool schemas. Common issues:

1. **Array properties** must have `items` schema:
   ```yaml
   items:
     type: array
     items:           # Required!
       type: object
       properties:
         sku: { type: string }
   ```

2. **Object properties** must have `properties` defined:
   ```yaml
   customer_info:
     type: object
     properties:      # Required!
       id: { type: string }
       name: { type: string }
     required: [id]   # Recommended
   ```

3. **Avoid reserved JSON Schema keywords** as property names:
   - Use `item_description` instead of `description`
   - Use `value_type` instead of `type`

---

## Simulated vs Real Skills

### Simulated Skills (Testing)

1. All servers in `registry.yaml` point to `http://stub-mcp:8765`
2. `tools.yaml` contains test cases with deterministic responses
3. Stub server returns matching case responses
4. Use for: unit tests, integration tests, workflow validation

### Real Skills (Production)

1. Update `registry.yaml` to point to real endpoints:
   ```yaml
   servers:
     search:
       transport: streamable_http
       endpoint: https://api.bing.microsoft.com
       path: /v7.0/search
       headers:
         Ocp-Apim-Subscription-Key: ${BING_API_KEY}
   ```
2. Tools are called against actual APIs
3. Test cases are ignored (only used by stub server)
4. Use for: production deployments, real API integration

---

## End-to-End Workflow

This section illustrates the complete flow from authoring a new skill to executing it in a test workflow.

### Step 1: Author the Skill

Create `skills_src/skills/my.skill.skill.yaml`:

```yaml
apiVersion: skill/v1
kind: Skill

metadata:
  manifestId: skill.my.skill@0.1.0
  name: my.skill
  version: 0.1.0
  description: My custom skill
  tags: [custom, testing]

spec:
  permissions:
    egress: intranet
    secrets: []

  directives: |
    You are a specialized agent for my task.
    Follow these steps:
    1. Use `myserver:my_tool` to get data
    2. Process the results
    3. Return structured output

  tools:
    - ref: myserver:my_tool
      required: true
      description: Gets data for processing
```

### Step 2: Define Tools and Test Cases

Add to `skills_src/tools.yaml`:

```yaml
servers:
  myserver:
    description: My custom server
    tools:
      my_tool:
        version: 0.1.0
        description: Gets data for processing
        params:
          type: object
          properties:
            query:
              type: string
              description: Query parameter
          required: [query]
        result:
          type: object
          properties:
            data:
              type: array
              items:
                type: object
                properties:
                  id: { type: string }
                  value: { type: string }
                required: [id, value]
        defaults:
          response: { data: [] }
          latencyMs: 100
        cases:
          - id: happy_path
            match:
              strategy: exact
              path: query
              value: "test"
            response:
              data:
                - id: "1"
                  value: "Test result"
          - id: fallback
            match:
              strategy: always
            response:
              data: []
```

### Step 3: Register the Server

Add to `skills_src/registry.yaml`:

```yaml
servers:
  myserver:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp
```

### Step 4: Generate Artifacts

```python
from dcf_mcp.tools.dcf.generate import generate_all

result = generate_all(
    skills_src_dir="./skills_src",
    generated_dir="./generated"
)
print(result["summary"])
# Generated: 16 skill manifest(s), 25 tool(s) with 56 case(s)
```

### Step 5: Verify Generation

```bash
# Check manifest was created
ls generated/manifests/skill.my.skill-0.1.0.json

# Check tool is in stub config
cat generated/stub/stub_config.json | jq '.servers.myserver.tools | keys'

# Check skill is in catalog
cat generated/catalogs/skills_catalog.json | jq '.skills[] | select(.skillName == "my.skill")'
```

### Step 6: Start Services

```bash
docker compose up -d

# Verify stub server loaded the new tool
docker compose logs stub-mcp | grep "loaded"
# [stub-mcp] loaded 25 tools from /app/generated/stub/stub_config.json
```

### Step 7: Test the Skill

```python
from dcf_mcp.tools.dcf.load_skill import load_skill
from dcf_mcp.tools.dcf.unload_skill import unload_skill

# Load the skill onto an agent
result = load_skill(
    skill_manifest="generated/manifests/skill.my.skill-0.1.0.json",
    agent_id="test-agent-123"
)

# Agent can now use my_tool via MCP
# ... execute workflow ...

# Unload when done
unload_skill(skill_manifest_id="skill.my.skill@0.1.0", agent_id="test-agent-123")
```

### Step 8: Verify Test Cases

```bash
# Check which cases were hit
curl -s http://localhost:8765/metrics | jq '.metrics.case_hits'
# { "myserver:my_tool:happy_path": 3, "myserver:my_tool:fallback": 1 }
```

---

## Best Practices

### Skill Design

1. **Single Responsibility**: Each skill should do one thing well
2. **Clear Directives**: Write unambiguous instructions for agents
3. **Minimal Permissions**: Only request the egress/secrets you need
4. **Version Semantics**: Use semver for backwards compatibility

### Test Cases

1. **Cover Edge Cases**: Include error scenarios and empty results
2. **Use Realistic Data**: Test cases should reflect production responses
3. **Add Fallbacks**: Include an `always` case as a catch-all
4. **Test Templates**: Verify template variables work correctly

### Organization

1. **One Skill Per File**: Easier to review and version control
2. **Consistent Naming**: `<domain>.<name>.skill.yaml`
3. **Document Tools**: Add descriptions to tool references
4. **Keep Cases Focused**: Each case tests one specific scenario

---

## Troubleshooting

### Common Issues

**"YAML not installed"**
```bash
pip install pyyaml
```

**"Tool not found"**
- Verify the tool exists in `tools.yaml` under the correct server
- Check the `ref` format: `serverId:toolName`
- Ensure the server is registered in `registry.yaml`
- Regenerate artifacts after adding tools

**"No case matched"**
- Check match strategy and path
- Verify input arguments match expected values
- Add an `always` fallback case
- Check the stub server metrics: `curl http://localhost:8765/metrics`

**"Invalid Schema" in stub server UI**
- Ensure array properties have `items` schema defined
- Ensure object properties have `properties` defined
- Add `required` arrays to nested objects
- Avoid reserved JSON Schema keywords as property names (`description`, `type`, etc.)

**"Manifest validation failed"**
- Ensure `manifestId` matches pattern: `skill.<domain>.<name>@<version>`
- Verify all required fields are present
- Check permissions have valid egress values (`none`, `intranet`, `internet`)

**"Server not found" when loading skill**
- Verify the server ID in skill's tool refs exists in `registry.yaml`
- Run `generate_all()` after updating `registry.yaml`
- Restart the stub MCP server to pick up new configuration

**Generation fails with Docker paths**
When running generation outside Docker, specify local paths:
```python
yaml_to_manifests(
    skills_dir="./skills_src/skills",
    tools_yaml_path="./skills_src/tools.yaml",
    out_dir="./generated/manifests",
    catalog_path="./generated/catalogs/skills_catalog.json"
)
```

### Debug Commands

```bash
# List all servers in stub config
cat generated/stub/stub_config.json | jq '.servers | keys'

# List tools for a specific server
cat generated/stub/stub_config.json | jq '.servers.orders.tools | keys'

# Check skill manifest tools
cat generated/manifests/skill.validate.order-0.1.0.json | jq '.requiredTools[].toolName'

# Verify stub server health
curl -sf http://localhost:8765/healthz

# Check stub server metrics (tool calls, case hits)
curl -s http://localhost:8765/metrics | jq

# Reset metrics before test run
curl -X POST http://localhost:8765/metrics/reset

# Check stub server logs
docker compose logs -f stub-mcp

# Rebuild and restart stub server after config changes
docker compose restart stub-mcp

# Test MCP connection (requires proper headers)
curl -s -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

### Verification Checklist

When adding new skills or tools:

1. **YAML Authoring**
   - [ ] Created `skills_src/skills/<name>.skill.yaml`
   - [ ] Added tools to `skills_src/tools.yaml` under correct server
   - [ ] Added server to `skills_src/registry.yaml` (if new)

2. **Generation**
   - [ ] Ran `generate_all()` successfully
   - [ ] Verified manifest created in `generated/manifests/`
   - [ ] Verified tools in `generated/stub/stub_config.json`

3. **Runtime**
   - [ ] Stub server restarted or auto-reloaded config
   - [ ] Tool appears in stub server tool list (no "Invalid Schema")
   - [ ] Test cases return expected responses

---

## Schema Transformation Details

This section provides a detailed comparison of how YAML authoring files are transformed into JSON runtime manifests.

### Document Structure

**YAML Authoring Format:**
```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.research.web@0.1.0
  name: research.web
  version: 0.1.0
  description: Lightweight web research
  tags: [research, web]
spec:
  permissions:
    egress: internet
    secrets: [BING_API_KEY]
  directives: |
    Follow queries precisely.
  tools:
    - ref: search:search_query
      required: true
  dataSources:
    - id: guidelines
      text: Always cite sources.
```

**JSON Runtime Format (generated):**
```json
{
  "manifestApiVersion": "v2.0.0",
  "manifestId": "skill.research.web@0.1.0",
  "skillPackageId": null,
  "skillName": "research.web",
  "skillVersion": "0.1.0",
  "description": "Lightweight web research",
  "tags": ["research", "web"],
  "permissions": {
    "egress": "internet",
    "secrets": ["BING_API_KEY"]
  },
  "skillDirectives": "Follow queries precisely.\n",
  "requiredTools": [...],
  "requiredDataSources": [...]
}
```

### Tool Reference Transformation

**YAML (compact):**
```yaml
tools:
  - ref: search:search_query
    required: true
    description: Core search tool
```

**JSON (expanded with schema from tools.yaml):**
```json
"requiredTools": [{
  "toolName": "search_query",
  "description": "Core search tool",
  "json_schema": {
    "name": "search_query",
    "description": "Mock web search query tool",
    "parameters": {
      "type": "object",
      "properties": {
        "q": { "type": "string", "description": "Search query" }
      },
      "required": ["q"]
    }
  },
  "definition": {
    "type": "mcp_server",
    "serverId": "search",
    "toolName": "search_query"
  },
  "required": true
}]
```

### Data Source Transformation

**YAML (supports file references):**
```yaml
dataSources:
  - id: guidelines
    text: Always cite sources.

  - id: reference
    file: ./data/reference.txt   # Resolved at generation
```

**JSON (inline content only):**
```json
"requiredDataSources": [
  {
    "dataSourceId": "guidelines",
    "destination": "archival_memory",
    "content": {
      "type": "text_content",
      "text": "Always cite sources."
    }
  },
  {
    "dataSourceId": "reference",
    "destination": "archival_memory",
    "content": {
      "type": "text_content",
      "text": "... contents of reference.txt ..."
    }
  }
]
```

### Field Mapping Reference

| YAML Path | JSON Path | Notes |
|-----------|-----------|-------|
| `apiVersion` | `manifestApiVersion` | `skill/v1` → `v2.0.0` |
| `kind` | (none) | Used for validation only |
| `metadata.manifestId` | `manifestId` | Direct mapping |
| `metadata.name` | `skillName` | Direct mapping |
| `metadata.version` | `skillVersion` | Direct mapping |
| `metadata.description` | `description` | Direct mapping |
| `metadata.tags` | `tags` | Direct mapping |
| `spec.permissions` | `permissions` | Direct mapping |
| `spec.directives` | `skillDirectives` | Direct mapping |
| `spec.tools[].ref` | `requiredTools[].definition` | Expanded to full object |
| `spec.tools[].ref` | `requiredTools[].json_schema` | Enriched from tools.yaml |
| `spec.dataSources[].text` | `requiredDataSources[].content.text` | Wrapped in content object |
| `spec.dataSources[].file` | `requiredDataSources[].content.text` | File contents inlined |
| `spec.dependencies` | (none) | Future feature, not yet in JSON schema |
| (none) | `skillPackageId` | Always `null` in generated manifests |

### Features Comparison

| Feature | YAML Authoring | JSON Runtime |
|---------|---------------|--------------|
| Tool definition types | Logical refs only (`serverId:toolName`) | Multiple: `mcp_server`, `registered`, `python_source` |
| Data source files | Supported (`file: ./path`) | Not supported (resolved at generation) |
| Embedded tool schemas | No (pulled from tools.yaml) | Yes (required for Letta) |
| Skill dependencies | Supported (future) | Not supported |
| skillPackageId | Not used | Required (set to null) |
| Validation | Documentation only | JSON Schema enforceable |
| IDE support | Limited | Full (JSON Schema) |

### Why This Design?

1. **Separation of concerns**: Authors focus on *what* a skill does; the generator handles *how* it's represented for the runtime.

2. **DRY principle**: Tool schemas are defined once in `tools.yaml` and reused across skills, rather than duplicated in every skill file.

3. **File references**: Authors can organize data sources in external files for readability; the generator inlines them for portability.

4. **Future extensibility**: The YAML format can evolve (e.g., skill dependencies) without changing the runtime schema until features are ready.

5. **Human ergonomics**: YAML's multi-line strings, comments, and concise syntax are friendlier for authoring than JSON.

---

## CLI Reference

The `skill` CLI provides commands for authoring, validating, and testing skills.

### Installation

```bash
# From project root
pip install -e .

# Or run as module
python -m skill_cli <command>
```

### Global Options

| Option | Description |
|--------|-------------|
| `--skills-dir PATH` | Path to skills_src directory (default: auto-detect) |
| `--generated-dir PATH` | Path to generated output directory (default: auto-detect) |
| `-q, --quiet` | Suppress non-essential output |
| `-v, --verbose` | Increase verbosity (can be repeated) |
| `-V, --version` | Show version and exit |

### Commands

#### `skill init`

Create a new skill from a template:

```bash
skill init [NAME] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `NAME` | Skill name in dot notation (e.g., `research.arxiv`) |
| `-t, --template` | Template: `blank`, `research`, `write`, `plan`, `analyze`, `qa` |
| `-d, --description` | Skill description |
| `--tags` | Comma-separated tags |
| `--egress` | Network permission: `none`, `intranet`, `internet` |
| `-f, --force` | Overwrite existing skill |
| `--no-interactive` | Disable interactive prompts |

#### `skill validate`

Validate skill YAML files:

```bash
skill validate [SKILLS...] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `SKILLS` | Specific skills to validate (default: all) |
| `--strict` | Treat warnings as errors |
| `--format` | Output format: `text`, `json` |

#### `skill generate`

Generate JSON manifests and stub configuration:

```bash
skill generate [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--manifests-only` | Only generate skill manifests |
| `--stub-only` | Only generate stub server config |
| `--clean` | Clean generated directory first |
| `-w, --watch` | Watch for changes (not yet implemented) |

#### `skill list`

List available skills:

```bash
skill list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--format` | Output format: `table`, `json`, `yaml`, `names` |
| `--tags` | Filter by tags (comma-separated) |
| `--tools` | Include tool information |

#### `skill test`

Run test cases against stub MCP server:

```bash
skill test [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-s, --skill` | Test specific skill (can be repeated) |
| `-t, --tool` | Test specific tool (`serverId:toolName`) |
| `-c, --case` | Test specific case ID |
| `--stub-url` | Stub server URL (default: `http://localhost:8765`) |
| `--coverage` | Show coverage report |
| `--format` | Output format: `text`, `json`, `junit` |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SKILLS_SRC_DIR` | Override default skills_src directory path |
| `GENERATED_DIR` | Override default generated output directory path |

### Examples

```bash
# Create a research skill with all defaults
skill init mycompany.research --template research --no-interactive

# Validate specific skills with JSON output
skill validate research.web plan.actions --format json

# Generate only manifests, cleaning first
skill generate --manifests-only --clean

# List skills filtered by tag
skill list --tags research --format table

# Run tests for a specific tool with coverage
skill test --tool search:search_query --coverage -v
```
