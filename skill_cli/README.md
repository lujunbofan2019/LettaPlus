# DCF Skill CLI

Command-line interface for authoring, validating, and managing DCF skills.

## Overview

A **skill** is a meaningful capability that a Planner agent can understand and assign to a Worker agent. Skills differ in how they are **fulfilled**:

| Type | Fulfillment | User Provides | Use Case |
|------|-------------|---------------|----------|
| **Real** | Actual MCP servers & APIs | Integration details (endpoints, auth) | Production |
| **Simulated** | stub_mcp server | BDD test cases (input → output) | Testing workflows |

The key insight: A simulated skill doesn't need integration details because stub_mcp handles everything. Instead, it needs **test cases** that define what inputs trigger what outputs—enabling deterministic, reproducible testing of workflows.

## Installation

```bash
pip install -e .

# Optional: Enhanced validation
pip install jsonschema
```

## Quick Start

```bash
# Create a skill (choose Real or Simulated)
skill init

# Validate
skill validate

# Generate manifests and stub config
skill generate

# Test simulated skills
skill test
```

---

## Tutorials

### Tutorial 1: Creating a Simulated Skill for Testing

Simulated skills are fulfilled by stub_mcp. You define **BDD-style test cases** that specify what the stub returns for different inputs.

```bash
skill init
```

**Step 1: Choose skill type**
```
Skill type:
  1. Real
  2. Simulated (Recommended)
Select: 2
```

**Step 2: Define the skill**
```
Skill name: research.competitor_analysis
Description: Analyze competitors in a market segment
Tags: research, analysis
```

**Step 3: Define tools with test cases**
```
Tool name: find_competitors
What does this tool do?: Search for competitors in a given market

Parameter name: market
Type: string
Description: Market segment to analyze
Required? [Y/n]: y

Parameter name: (Enter to finish)

Default JSON: {"competitors": []}
```

**Step 4: Add BDD test cases**
```
Scenario name: robotics market search
Match strategy: contains
Which parameter to match: market
Value that input should contain: robotics
Response JSON: {"competitors": ["Acme Robotics", "SwiftLift", "AutoBot Inc"]}
Add another test case? [Y/n]: y

Scenario name: unknown market
Match strategy: contains
Which parameter to match: market
Value that input should contain: unknown_xyz
Response JSON: {"competitors": [], "message": "No data available"}
Add another test case? [y/N]: n
```

**Step 5: Directives**
```
Use default directives? [Y/n]: n

You are analyzing competitive landscapes.
When using find_competitors:
- Focus on direct competitors in the specified market
- Include both established players and emerging startups
- Note market positioning and key differentiators
```

**Result:**
- Skill YAML created in `skills_src/skills/`
- Tools with test cases added to `tools.yaml`

**Step 6: Test it**
```bash
skill generate
skill test --tool research_competitor_analysis:find_competitors
```

---

### Tutorial 2: Creating a Real Skill for Production

Real skills connect to actual APIs. You don't define test cases (the real API provides real responses).

**Prerequisites:** First, set up your tools with real endpoints:

```bash
# Add a server with real endpoint
skill server add
```
```
Server ID: bing_search
Description: Bing Search API
Transport type: streamable_http
Endpoint URL: https://api.bing.microsoft.com
Path: /v7.0/search
```

```bash
# Add a tool to that server
skill tool add --server bing_search
```

**Then create the skill:**

```bash
skill init
```

```
Skill type: Real
Skill name: research.web_search
Description: Search the web for information
Tags: research, search, web

Egress: internet
Required API keys: BING_API_KEY

Select tools: 1  (bing_search:search)

Use default directives? [Y/n]: y
```

---

### Tutorial 3: Understanding Test Cases

Test cases are the heart of simulated skills. They define **deterministic behavior** for testing.

**Match Strategies:**

| Strategy | Description | Example |
|----------|-------------|---------|
| `exact` | Input must match exactly | `market = "robotics"` |
| `contains` | Input contains substring | `market` contains `"robot"` |
| `regex` | Input matches regex pattern | `market` matches `".*robot.*"` |
| `always` | Always matches (fallback) | Default response |

**Example test cases for a competitor analysis tool:**

```yaml
cases:
  # Specific scenario
  - id: case_robotics_market
    match:
      strategy: contains
      path: market
      value: robotics
    response:
      competitors:
        - name: Acme Robotics
          strength: Market leader
        - name: SwiftLift
          strength: Fast-growing challenger

  # Edge case: empty results
  - id: case_unknown_market
    match:
      strategy: regex
      path: market
      value: "^unknown_.*"
    response:
      competitors: []
      message: No competitors found

  # Fallback for any other input
  - id: case_default
    match:
      strategy: always
    response:
      competitors:
        - name: Generic Competitor
      generated_at: "{{ now_iso }}"
```

**Why this matters:**
- The Planner assigns skills to Workers based on capability descriptions
- Workers execute skills using the tools
- Test cases ensure **predictable outputs** for testing workflows
- Without test cases, simulated skills return empty defaults

---

## Command Reference

### `skill init`

Create a new skill interactively:

```bash
skill init           # Choose Real or Simulated
skill init --force   # Overwrite existing skill
```

### `skill tool`

Manage MCP tools:

```bash
skill tool list                      # List all tools
skill tool list --server search      # Filter by server
skill tool show search:search_query  # Show tool details
skill tool add                       # Add tool interactively
skill tool add --server myserver     # Add to specific server
```

### `skill server`

Manage MCP servers:

```bash
skill server list           # List all servers
skill server show search    # Show server details
skill server add            # Add server interactively
skill server validate       # Validate all server connections
```

**Connection Validation:**
When adding a server, the CLI automatically validates the connection:
- **HTTP/SSE**: Sends MCP initialize request to verify endpoint responds
- **stdio**: Checks that the command/executable exists and is runnable

**Resource Memory:**
The CLI remembers previously configured servers, endpoints, and commands. When you add a new server or tool, it offers these as quick-select options—no need to retype the same endpoints repeatedly.

Known servers are stored in `.skill_cli_cache.yaml` and marked with ✓ if successfully validated.

### `skill validate`

Validate skill YAML files:

```bash
skill validate                 # All skills
skill validate research.web    # Specific skill
skill validate --strict        # Warnings as errors
skill validate --integrations  # Also validate server connections
skill validate --format json   # JSON output
```

**Integration validation** (`--integrations`) checks that:
- MCP servers referenced by skills are reachable
- File paths referenced by data sources exist
- Stdio commands are executable

### `skill generate`

Generate manifests and stub configuration:

```bash
skill generate                 # Generate everything
skill generate --manifests-only
skill generate --stub-only
skill generate --clean         # Clean first
```

### `skill list`

List available skills:

```bash
skill list                 # Table format
skill list --tags research # Filter by tags
skill list --tools         # Show tools
skill list --format json
```

### `skill test`

Run test cases against stub_mcp:

```bash
skill test                              # All tests
skill test --tool server:tool_name      # Specific tool
skill test --case case_robotics_market  # Specific case
skill test --coverage                   # Show coverage
skill test --format junit               # JUnit output
```

---

## Integration Validation

The CLI validates MCP server connections before saving configurations:

| Transport | Validation Method |
|-----------|-------------------|
| `streamable_http` | Sends MCP `initialize` JSON-RPC request |
| `sse` | HTTP HEAD/GET request to verify endpoint exists |
| `stdio` | Checks executable exists in PATH or at absolute path |

**Validate all servers:**
```bash
skill server validate
```

**Example output:**
```
Validating 3 servers

✓ search: MCP server responding
✓ llm: MCP server responding
✗ datasets: Connection failed: Connection refused
```

---

## Workflow Summary

### For Testing (Simulated Skills)

```
┌─────────────────────────────────────────────────────────┐
│  skill init (Simulated)                                 │
│    └─ Define skill purpose                              │
│    └─ Define tools with parameters                      │
│    └─ Define BDD test cases (input → output)            │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  skill generate                                         │
│    └─ Creates skill manifest JSON                       │
│    └─ Creates stub_config.json with test cases          │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  skill test                                             │
│    └─ Calls stub_mcp with test inputs                   │
│    └─ Verifies deterministic responses                  │
└─────────────────────────────────────────────────────────┘
```

### For Production (Real Skills)

```
┌─────────────────────────────────────────────────────────┐
│  skill server add                                       │
│    └─ Configure real API endpoint                       │
│  skill tool add                                         │
│    └─ Define tool schema (no test cases needed)         │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  skill init (Real)                                      │
│    └─ Define skill purpose                              │
│    └─ Select existing tools                             │
│    └─ Set permissions (egress, secrets)                 │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  skill generate                                         │
│    └─ Creates skill manifest JSON                       │
│    └─ (Real APIs called at runtime, no stub needed)     │
└─────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
skills_src/
├── skills/                    # Skill YAML files
│   ├── research.web.skill.yaml
│   └── ...
├── tools.yaml                 # Tool definitions + test cases
├── registry.yaml              # Server endpoints
├── .skill_cli_cache.yaml      # Remembered servers and endpoints
└── schemas/
    └── skill.schema.json      # Validation schema

generated/
├── manifests/                 # Skill manifest JSONs
├── catalogs/                  # Skills catalog
└── stub/
    └── stub_config.json       # Test cases for stub_mcp
```

**Note:** `.skill_cli_cache.yaml` stores known servers, recent endpoints, and recent stdio commands for quick reuse. This file is auto-managed by the CLI.
