# Phase 1 E2E Testing Summary

This document summarizes the learnings, fixes, and current state after completing Phase 1 (Workflow Execution) end-to-end testing.

## Testing Scope

Phase 1 testing covered the Dynamic Capabilities Framework (DCF) workflow execution pattern:
- **Planner Agent**: Workflow creation and orchestration
- **Worker Agents**: Ephemeral task executors
- **Reflector Agent**: Post-workflow analysis (not tested in this round)

## Key Issues Identified and Fixed

### 1. Worker Agent Naming Bug
**Issue**: Worker agents were created with double prefix: `wf-wf-order-proc-001-ValidateOrder`
**Root Cause**: `create_worker_agents.py` line 450 recalculated prefix instead of using pre-computed `base_prefix`
**Fix**: Changed to use `base_prefix` variable computed at line 312-319

### 2. YAML Source vs JSON Generated Design Violation
**Issue**: JSON files were created directly in `skills_src/` which should only contain YAML sources
**Principle**: `skills_src/` = human-editable YAML sources; `generated/` = machine-readable JSON outputs
**Fix**: Created generators for all artifact types:
- `yaml_to_manifests.py` → `generated/manifests/*.json`
- `yaml_to_stub_config.py` → `generated/stub/stub_config.json`
- `yaml_to_registry.py` → `generated/registry.json`
- `yaml_to_schemas.py` → `generated/schemas/*.json`

### 3. Schema Files Conflict
**Issue**: `skill.schema.json` and `skill.schema.yaml` coexisted in `skills_src/schemas/`
**Resolution**:
- Created `skill.authoring.schema.yaml` (proper JSON Schema in YAML format)
- Renamed documentation file to `skill.reference.yaml`
- Removed JSON files from `skills_src/schemas/`
- Generator produces `generated/schemas/skill.authoring.schema.json`

### 4. Missing Volume Mounts
**Issue**: `generated/schemas/` and `generated/registry.json` weren't mounted in Docker
**Fix**: Added volume mounts in `docker-compose.yml`:
```yaml
- ./generated/schemas:/app/generated/schemas
- ./generated/registry.json:/app/generated/registry.json
```

### 5. skill_cli Test Command Failures
**Issue**: HTTP 406 "Not Acceptable" errors when running tests
**Root Cause**: MCP Streamable HTTP requires `Accept: application/json, text/event-stream`
**Fixes**:
- Added correct Accept header
- Changed session header from `mcp-session` to `mcp-session-id`
- Added SSE (Server-Sent Events) response parser
- Updated protocol version to `2024-11-05`

### 6. agents_map Persistence
**Issue**: Worker agent IDs weren't persisted to Redis control plane
**Fix**: Added Redis persistence in `create_worker_agents.py` (lines 497-528)

## Current System State

### Services (Docker Compose)
| Service | Port | Status |
|---------|------|--------|
| Letta API | 8283 | Healthy |
| DCF MCP | 8337 | Running |
| Stub MCP | 8765 | Healthy |
| Graphiti MCP | 8000 | Running |
| Redis | 6379 | Healthy |
| FalkorDB | 8379 | Healthy |

### Generated Artifacts
```
generated/
├── manifests/           # 15 skill manifest JSON files
├── catalogs/
│   └── skills_catalog.json
├── stub/
│   └── stub_config.json  # 24 tools, 54 test cases
├── schemas/
│   └── skill.authoring.schema.json
└── registry.json         # 9 MCP servers
```

### skill_cli Commands (All Working)
| Command | Function | Result |
|---------|----------|--------|
| `list` | List available skills | 15 skills |
| `tool list` | List MCP tools | 24 tools |
| `server list` | List MCP servers | 9 servers |
| `validate` | Validate skill YAML files | All valid |
| `generate` | Generate all artifacts | All generated |
| `test` | Run test cases against stub | 54/54 passed |

### Schema Validation
All 15 skills pass JSON Schema validation:
- analyze.synthesis, calculate.pricing, compose.response
- diagnose.issue, generate.invoice, lookup.customer
- plan.actions, plan.research_scope, qa.review
- research.company, research.news, research.web
- validate.order, write.briefing, write.summary

## Architecture Principles Reinforced

### 1. YAML → JSON Pipeline
```
skills_src/           →  generated/
├── skills/*.yaml     →  ├── manifests/*.json
├── tools.yaml        →  ├── stub/stub_config.json
├── registry.yaml     →  ├── registry.json
└── schemas/*.yaml    →  └── schemas/*.json
```

### 2. MCP Streamable HTTP Protocol
- Requires dual Accept header: `application/json, text/event-stream`
- Session ID returned as `mcp-session-id` header
- Responses may be SSE format requiring parsing

### 3. Control Plane (Redis)
- Meta document: `cp:wf:{workflow_id}:meta`
- State documents: `cp:wf:{workflow_id}:state:{state_name}`
- Data plane outputs: `dp:wf:{workflow_id}:output:{state_name}`

## Files Modified

### Core DCF Tools
- `dcf_mcp/tools/dcf/create_worker_agents.py` - Worker naming fix, agents_map persistence
- `dcf_mcp/tools/dcf/generate.py` - Added registry and schema generation
- `dcf_mcp/tools/dcf/load_skill.py` - Updated registry path
- `dcf_mcp/tools/dcf/yaml_to_registry.py` - NEW: Registry generator
- `dcf_mcp/tools/dcf/yaml_to_schemas.py` - NEW: Schema generator

### skill_cli
- `skill_cli/commands/generate.py` - Added registry/schema generation
- `skill_cli/commands/test.py` - Fixed MCP communication (headers, SSE parsing)
- `skill_cli/commands/validate.py` - Updated schema path resolution

### Configuration
- `docker-compose.yml` - Added volume mounts
- `dcf_mcp/requirements.txt` - Added pyyaml>=6.0

### Documentation
- `CLAUDE.md` - Updated generated directory description
- `skills_src/SKILLS.md` - Updated generation pipeline documentation

## Recommendations for Phase 2

1. **Verify DCF+ tools exist**: Check `dcf_mcp/tools/dcf_plus/` for Companion, Conductor, Strategist tools
2. **Check agent templates**: Verify `.af` templates exist for Phase 2 agents
3. **Review session management**: Phase 2 uses shared memory blocks, not Redis control plane
4. **Test async messaging**: Phase 2 uses `send_message_to_agent_async` for task delegation

## Test Commands Reference

```bash
# Health checks
curl -sf http://localhost:8283/v1/health/  # Letta
curl -sf http://localhost:8765/healthz     # Stub MCP

# Generate all artifacts
docker exec lettaplus-dcf-mcp-1 python -c \
  "from tools.dcf.generate import generate_all; print(generate_all()['summary'])"

# Run skill_cli
python -m skill_cli --skills-dir skills_src list
python -m skill_cli --skills-dir skills_src generate
python -m skill_cli --skills-dir skills_src test --coverage

# Redis inspection
docker exec lettaplus-redis-1 redis-cli KEYS "cp:wf:*"
docker exec lettaplus-redis-1 redis-cli JSON.GET "cp:wf:{id}:meta" $
```
