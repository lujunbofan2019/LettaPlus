# DCF Skill Studio

A cross-platform Electron application for authoring, editing, validating, and generating DCF skill manifests.

## Overview

**DCF Skill Studio** provides a visual interface for working with Dynamic Capabilities Framework (DCF) skills. Skills are the fundamental unit of capability in DCF—self-contained, version-controlled packages that define what an agent can do, which tools it needs, and how it should behave.

### Why a GUI Tool?

While YAML files are excellent for version control and CI/CD pipelines, skill authoring benefits from:

- **Immediate Validation Feedback**: See errors as you type, not after running a command
- **Tool Discovery**: Browse available tools grouped by server instead of remembering names
- **Form-Based Editing**: Structured input with dropdowns, checkboxes, and type validation
- **Cross-Reference Visualization**: See which tools exist, which are used, which are missing

The Studio complements (not replaces) the command-line workflow—use whichever fits your task.

---

## Relationship with skill_cli

DCF provides **two authoring tools** that work with the same YAML source files:

| Tool | Best For | Strengths |
|------|----------|-----------|
| **DCF Skill Studio** (GUI) | Interactive authoring, exploration, learning | Visual feedback, tool discovery, form validation |
| **skill_cli** (CLI) | Automation, CI/CD, scripting, batch operations | Scriptable, no GUI dependencies, pipeline integration |

### Complementary Workflows

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AUTHORING LAYER                              │
│                                                                     │
│    ┌───────────────────┐              ┌───────────────────┐         │
│    │  DCF Skill Studio │              │    skill_cli      │         │
│    │     (Electron)    │              │    (Python)       │         │
│    │                   │              │                   │         │
│    │  • Visual editing │              │  • skill init     │         │
│    │  • Tool picker    │              │  • skill validate │         │
│    │  • Live validation│              │  • skill generate │         │
│    │  • Export to zip  │              │  • skill test     │         │
│    └────────┬──────────┘              └────────┬──────────┘         │
│             │                                   │                   │
│             └──────────────┬───────────────────┘                    │
│                            │                                        │
│                            ▼                                        │
│              ┌─────────────────────────┐                            │
│              │   skills_src/*.yaml     │  ◄── Single source of truth│
│              │   (YAML source files)   │                            │
│              └─────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       GENERATION LAYER                              │
│                                                                     │
│              dcf_mcp/tools/dcf/generate.py                          │
│              (Same generators used by both tools)                   │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        RUNTIME LAYER                                │
│                                                                     │
│              generated/manifests/*.json                             │
│              (Machine-readable skill manifests)                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Principle**: Both tools produce identical outputs. Choose based on context:

- **New to DCF?** Start with the Studio to explore and learn
- **Quick edit?** Use the Studio for visual feedback
- **CI/CD pipeline?** Use skill_cli for automation
- **Batch validation?** Use `skill validate` in CI
- **Creating from template?** Either works; CLI has `skill init` wizard

---

## DCF Skill Lifecycle

A skill moves through distinct phases from creation to runtime execution:

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐    ┌─────────┐
│ AUTHOR  │───▶│ VALIDATE │───▶│ GENERATE │───▶│  LOAD   │───▶│ EXECUTE │
└─────────┘    └──────────┘    └──────────┘    └─────────┘    └─────────┘
     │              │               │               │              │
     ▼              ▼               ▼               ▼              ▼
  .skill.yaml   Schema check   manifest.json   Agent gains    Tools are
  created/      + static       + catalog       tools &        called per
  edited        analysis       updated         directives     directives
```

### Phase 1: Author

Create or edit a `.skill.yaml` file defining:
- **Metadata**: Name, version, description, tags
- **Permissions**: Network egress, secret access, risk level
- **Directives**: Natural language instructions for the agent
- **Tools**: References to MCP tools the skill requires
- **Data Sources**: Files, URLs, or memory blocks to inject

### Phase 2: Validate

Validation happens at two levels:

| Level | What's Checked | When |
|-------|----------------|------|
| **Schema Validation** | YAML structure matches authoring schema | Real-time in Studio, `skill validate` |
| **Static Analysis** | manifestId format, tool reference format, required fields | Real-time in Studio |
| **Cross-Reference** | Tools exist in catalog, servers are defined | When tools catalog is loaded |

### Phase 3: Generate

The generator transforms human-friendly YAML into machine-readable JSON:

```yaml
# YAML Authoring (human-friendly)          # JSON Runtime (machine-ready)
tools:                                      "tools": [
  - ref: search:search_query        ───▶      {
    required: true                              "name": "search_query",
                                                "server": "search",
                                                "inputSchema": { ... },
                                                "required": true
                                              }
                                            ]
```

**What the generator does:**
1. Resolves tool references (`search:search_query`) to full definitions
2. Inlines file-based data sources
3. Validates against runtime schema
4. Updates skills catalog for discovery

### Phase 4: Load

When a Planner or Conductor assigns a skill to an agent:

```python
load_skill(
    skill_manifest="generated/manifests/skill.research.web-0.1.0.json",
    agent_id="worker-agent-123"
)
```

**What happens:**
1. Manifest is validated against runtime schema
2. Tools are attached to the agent via MCP
3. Directives are injected into agent's system prompt
4. Data sources are loaded into agent's memory blocks

### Phase 5: Execute

The agent uses the skill's tools following its directives until:
- Task is complete → `unload_skill()` restores clean baseline
- Error occurs → Skill remains loaded for debugging
- Session ends → All skills unloaded automatically

---

## Skill Package Resource Types

A skill package consists of several resource types, each serving a specific purpose:

### 1. Metadata

Identifies and categorizes the skill:

```yaml
metadata:
  manifestId: skill.research.web@0.1.0   # Unique identifier
  name: research.web                      # Dot-notation name (category.skill)
  version: 0.1.0                          # Semantic version
  description: Lightweight web research   # Human-readable purpose
  tags: [research, web, search]           # Discovery tags
```

**Naming Convention**: `<category>.<skill-name>`
- Categories: `research`, `analyze`, `plan`, `write`, `qa`, `order-processing`, etc.
- Names: lowercase, hyphen-separated words

**Version Format**: Semantic versioning (`MAJOR.MINOR.PATCH`)
- MAJOR: Breaking changes to directives or tool requirements
- MINOR: New capabilities, backward compatible
- PATCH: Bug fixes, documentation updates

### 2. Permissions

Declares security requirements for governance:

```yaml
permissions:
  egress: true          # Can make outbound network requests
  secrets: true         # Can access API keys, tokens
  riskLevel: medium     # low | medium | high
```

| Permission | Purpose | Governance Impact |
|------------|---------|-------------------|
| `egress` | Network access (HTTP, WebSocket) | Logged, rate-limited in production |
| `secrets` | Credential access | Audited, requires approval |
| `riskLevel` | Overall risk assessment | Affects approval workflow |

**Risk Level Guidelines:**
- **low**: Read-only, no external access, no PII
- **medium**: External API calls, data transformation
- **high**: Writes to external systems, handles PII, financial operations

### 3. Directives

Natural language instructions that guide agent behavior:

```yaml
directives: |
  # Web Research Skill

  You are conducting web research. Follow these guidelines:

  ## Process
  1. Formulate precise search queries based on user intent
  2. Execute searches using the search_query tool
  3. Analyze results for relevance and credibility
  4. Synthesize findings into a coherent summary

  ## Output Format
  - Lead with key findings
  - Include source citations with URLs
  - Note any limitations or gaps in available information

  ## Constraints
  - Maximum 3 search queries per request
  - Prefer recent sources (< 1 year old)
  - Flag contradictory information explicitly
```

**Best Practices:**
- Use Markdown for structure (headers, lists, code blocks)
- Be specific about process steps
- Define output format expectations
- State constraints and limitations
- Include examples for complex behaviors

### 4. Tools

References to MCP tools the skill requires:

```yaml
tools:
  - ref: search:search_query      # server:tool_name format
    required: true                 # Skill won't work without this
    description: Primary search    # Why this tool is needed

  - ref: web:fetch_page
    required: false                # Optional enhancement
    description: Deep-dive into specific pages
```

**Tool Reference Format**: `<server>:<tool_name>`
- `server`: Logical server ID (defined in registry.yaml)
- `tool_name`: Tool name as registered on that server

**Required vs Optional:**
- `required: true` — Skill fails to load if tool unavailable
- `required: false` — Skill works with degraded functionality

### 5. Data Sources

External data injected into agent context:

```yaml
dataSources:
  # File-based (resolved at generation time)
  - type: file
    path: ./data/research-guidelines.md

  # URL-based (fetched at load time)
  - type: url
    url: https://api.example.com/guidelines

  # Memory block (shared across agents)
  - type: memory_block
    blockLabel: session_context
```

| Type | When Resolved | Use Case |
|------|---------------|----------|
| `file` | Generation time | Static guidelines, templates, examples |
| `url` | Load time | Dynamic configuration, live data |
| `memory_block` | Runtime | Shared state, session context |

---

## Composing Skills Effectively

### Skill Design Principles

#### 1. Single Responsibility

Each skill should do **one thing well**:

```yaml
# GOOD: Focused skill
name: research.web
description: Search the web and summarize findings
tools:
  - ref: search:search_query
  - ref: web:fetch_page

# BAD: Kitchen sink skill
name: research.everything
description: Research, analyze, write reports, send emails...
tools:
  - ref: search:search_query
  - ref: web:fetch_page
  - ref: analyze:sentiment
  - ref: write:format_report
  - ref: email:send
```

**Why?** Focused skills are:
- Easier to test
- Reusable across workflows
- Simpler to version
- Clearer in their permissions

#### 2. Explicit Dependencies

Declare all tools explicitly—never assume availability:

```yaml
# GOOD: All dependencies declared
tools:
  - ref: search:search_query
    required: true
  - ref: llm:summarize
    required: true

# BAD: Implicit dependency on LLM
tools:
  - ref: search:search_query
    required: true
# (Agent might not have summarize capability!)
```

#### 3. Defensive Directives

Write directives that handle edge cases:

```yaml
directives: |
  ## Error Handling
  - If search returns no results, report "No results found" rather than hallucinating
  - If a URL is inaccessible, note it and continue with available data
  - If results are contradictory, present both viewpoints with sources

  ## Boundaries
  - Do NOT make up information not found in search results
  - Do NOT access URLs not returned by search results
  - STOP and ask for clarification if the query is ambiguous
```

#### 4. Appropriate Permissions

Request minimum necessary permissions:

```yaml
# GOOD: Minimal permissions
permissions:
  egress: true      # Needed for web search
  secrets: false    # No API keys needed (uses stub)
  riskLevel: low    # Read-only research

# BAD: Over-permissioned
permissions:
  egress: true
  secrets: true     # Why? Not using any secrets
  riskLevel: high   # Why? Just doing research
```

### Skill Composition Patterns

#### Pattern 1: Research → Analyze → Write

```yaml
# skills/research/web.skill.yaml
name: research.web
tools: [search:search_query, web:fetch_page]

# skills/analyze/sentiment.skill.yaml
name: analyze.sentiment
tools: [llm:analyze_sentiment]

# skills/write/report.skill.yaml
name: write.report
tools: [llm:format_markdown]
```

**Workflow orchestrates these independently:**
```
Task1: research.web → "Raw findings"
Task2: analyze.sentiment → "Sentiment scores"
Task3: write.report → "Final report"
```

#### Pattern 2: Skill with Optional Enhancement

```yaml
name: research.comprehensive
tools:
  - ref: search:search_query
    required: true
  - ref: search:search_news     # Optional: adds news results
    required: false
  - ref: web:fetch_page         # Optional: deep-dive capability
    required: false

directives: |
  If search_news is available, also check recent news.
  If fetch_page is available, retrieve full content for top 3 results.
```

#### Pattern 3: Data-Driven Skill

```yaml
name: qa.compliance-check
dataSources:
  - type: file
    path: ./data/compliance-rules.yaml

directives: |
  You have access to compliance rules in your context.
  For each item, check against these rules and report violations.
```

---

## Features

- **Skill List View**: Browse skills from project folder with search and filter
- **Skill Editor**: Form-based editing with tabs for Metadata, Permissions, Tools, and Data Sources
- **Tool Picker**: Visual tool selection from the catalog grouped by server
- **Real-time Validation**: Immediate feedback on skill validity
- **Generation**: One-click generation of skill manifests via Python bridge
- **Export**: Package skills as zip archives with documentation

## Prerequisites

- Node.js 18+
- Python 3.9+ (for generation features)
- `dcf_mcp` package installed (`pip install -e ../dcf_mcp`)

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Type checking
npm run typecheck

# Linting
npm run lint
```

## Build

```bash
# Package for current platform
npm run package

# Create distributables
npm run make
```

## Project Structure

```
dcf-skill-studio/
├── src/
│   ├── main/                 # Electron Main Process
│   │   ├── index.ts          # Entry point, window creation
│   │   ├── preload.ts        # Context bridge for IPC
│   │   ├── ipc/              # IPC handlers
│   │   │   ├── skills.ts     # Skill CRUD operations
│   │   │   ├── tools.ts      # Tools catalog loading
│   │   │   ├── validation.ts # Schema validation
│   │   │   ├── generation.ts # Python generator bridge
│   │   │   └── export.ts     # Zip packaging
│   │   └── services/
│   │       ├── FileService.ts      # File system operations
│   │       ├── YamlService.ts      # YAML parsing/serialization
│   │       ├── ValidationService.ts # Ajv schema validation
│   │       ├── GeneratorBridge.ts  # Python subprocess bridge
│   │       └── WatcherService.ts   # File change detection
│   ├── renderer/             # React Renderer Process
│   │   ├── App.tsx           # Main React app
│   │   ├── components/
│   │   │   ├── layout/       # Header, Sidebar, StatusBar
│   │   │   ├── skills/       # SkillList, SkillEditor, SkillCard
│   │   │   ├── editor/       # Form components per tab
│   │   │   ├── tools/        # ToolPicker, ToolCatalog
│   │   │   └── validation/   # ValidationPanel
│   │   ├── hooks/            # Custom React hooks
│   │   └── store/            # Zustand state management
│   └── shared/               # Shared types and IPC channels
├── resources/
│   └── templates/            # Skill templates for "New Skill"
├── forge.config.ts           # Electron Forge configuration
└── package.json
```

## Usage

1. Click "Open Project" to select your LettaPlus project directory
2. Browse and select skills from the sidebar (grouped by category)
3. Edit skill properties using the form interface
4. See validation errors in real-time in the right panel
5. Click "Save" to write changes to disk
6. Click "Generate All" to run the Python generators

## Architecture Decisions

### Why Electron?

- **Cross-platform**: Single codebase for Windows, macOS, Linux
- **Full Node.js access**: File system, child processes, native modules
- **Web technologies**: React ecosystem, rapid UI development
- **Offline-first**: No server dependency, works without network

### Why React + Zustand?

- **React**: Component-based UI, large ecosystem, TypeScript support
- **Zustand**: Minimal boilerplate, no providers needed, good DevTools

### Why Python Bridge (not Pure Node.js)?

The generators live in `dcf_mcp` (Python) and are also used by:
- The CLI (`skill_cli`)
- Docker containers
- CI/CD pipelines

**Duplicating in Node.js would mean:**
- Two implementations to maintain
- Potential drift between outputs
- More testing burden

**The bridge approach:**
- Single source of truth for generation logic
- Studio always produces identical output to CLI
- Python requirement is acceptable (users already have it for DCF)

### Why File-Based (not Database)?

Skills are:
- Version controlled (Git)
- Edited by multiple tools (Studio, CLI, text editors)
- Part of a monorepo structure

A database would add:
- Sync complexity with Git
- Migration overhead
- Dependency on running service

File-based + file watching gives:
- Instant sync with external edits
- No additional infrastructure
- Natural Git workflow

## Technology Stack

- **Electron 31** - Cross-platform desktop framework
- **React 18** - UI library with hooks
- **TypeScript** - Type safety across main/renderer
- **Tailwind CSS** - Utility-first styling
- **Radix UI** - Accessible, unstyled components
- **Zustand** - Lightweight state management
- **Monaco Editor** - VS Code's editor for directives
- **Ajv** - JSON Schema validation
- **js-yaml** - YAML parsing and serialization
- **chokidar** - Cross-platform file watching

## License

MIT
