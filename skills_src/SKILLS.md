# DCF Skills Authoring & Simulation Guide

This document explains the skill simulation and authoring infrastructure for the Dynamic Capabilities Framework (DCF). It covers both simulated skills for testing and real skills for production use.

## Overview

The DCF skill system enables agents to dynamically load and unload capabilities at runtime. Skills are defined as declarative manifests that specify:

- **Directives**: Behavioral instructions for the agent
- **Tools**: MCP tools the skill requires
- **Data Sources**: Context injected into agent memory
- **Permissions**: Network access and secret requirements

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

Maps logical server IDs to actual endpoints.

```yaml
apiVersion: registry/v1
kind: ServerRegistry

env: test   # test | staging | production

servers:
  search:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

  llm:
    transport: streamable_http
    endpoint: http://stub-mcp:8765
    path: /mcp

# Production overrides (commented example)
# overrides:
#   production:
#     search:
#       endpoint: https://api.bing.microsoft.com
#       headers:
#         Ocp-Apim-Subscription-Key: ${BING_API_KEY}
```

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

## Generation Commands

### Unified Generator (Recommended)

```python
from dcf_mcp.tools.dcf.generate import generate_all

# Generate everything
result = generate_all()

# Custom paths
result = generate_all(
    skills_src_dir="/path/to/skills_src",
    generated_dir="/path/to/generated"
)
```

### Individual Generators

```python
from dcf_mcp.tools.dcf.yaml_to_manifests import yaml_to_manifests
from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config

yaml_to_manifests()
yaml_to_stub_config()
```

---

## Directory Structure

```
skills_src/
├── SKILLS.md                   # This documentation
├── tools.yaml                  # Tool specifications + test cases
├── registry.yaml               # Server endpoint mappings
├── skills/                     # Individual skill definitions
│   ├── research.web.skill.yaml
│   ├── research.news.skill.yaml
│   ├── write.summary.skill.yaml
│   └── ...
└── schemas/                    # YAML schema documentation
    ├── skill.schema.yaml
    ├── tools.schema.yaml
    └── registry.schema.yaml
```

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
- Verify the tool exists in `tools.yaml`
- Check the `ref` format: `serverId:toolName`
- Regenerate artifacts after adding tools

**"No case matched"**
- Check match strategy and path
- Verify input arguments match expected values
- Add an `always` fallback case

**"Manifest validation failed"**
- Ensure `manifestId` matches pattern: `skill.<domain>.<name>@<version>`
- Verify all required fields are present
- Check permissions have valid egress values

### Debug Commands

```bash
# Verify stub config
cat generated/stub/stub_config.json | jq '.servers | keys'

# Check skill manifest
cat generated/manifests/skill.research.web-0.1.0.json | jq '.requiredTools'

# Test stub server
curl -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

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
