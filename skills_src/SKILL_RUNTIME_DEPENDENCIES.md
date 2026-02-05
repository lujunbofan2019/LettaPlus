# Skill Runtime Dependencies

This document captures the critical findings from an investigation into agent-skill dependencies, conducted before the planned DCF skill authoring refactoring.

## Purpose

Before reorganizing the skill authoring layer, we needed to understand what parts of the skill system are **immutable runtime contracts** versus **flexible authoring concerns**. This ensures refactoring doesn't break agent functionality.

## Key Finding: Two-Layer Architecture

The DCF skill system operates as a **two-layer architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│  AUTHORING LAYER (Human-Editable)                               │
│  ────────────────────────────────                               │
│  • skills_src/skills/*.skill.yaml                               │
│  • skills_src/tools.yaml                                        │
│  • skills_src/registry.yaml                                     │
│  • skills_src/schemas/*.schema.yaml                             │
│                                                                 │
│  ✓ CAN CHANGE: file layout, directory structure, YAML format    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                     [ GENERATORS ]
                     yaml_to_manifests()
                     yaml_to_stub_config()
                     yaml_to_registry()
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  RUNTIME LAYER (Machine-Readable)                               │
│  ────────────────────────────────                               │
│  • generated/manifests/skill.*.json                             │
│  • generated/catalogs/skills_catalog.json                       │
│  • generated/stub/stub_config.json                              │
│  • generated/registry.json                                      │
│                                                                 │
│  ✗ MUST NOT CHANGE: JSON schema, field names, data structure    │
└─────────────────────────────────────────────────────────────────┘
```

## Protected Runtime Fields (CRITICAL)

These fields in the JSON manifest schema are consumed by agents at runtime. Changing them would break agent functionality:

| Field | Consumer | Purpose |
|-------|----------|---------|
| `manifestId` | `load_skill`, `unload_skill` | Unique skill identifier |
| `skillName` | Agents, validation | Human-readable name |
| `skillVersion` | Version resolution | Semantic version string |
| `skillDirectives` | Agent prompts | Instructions for skill use |
| `requiredTools` | Tool loading | List of MCP tools to attach |
| `requiredDataSources` | Memory blocks | Data sources to create |
| `permissions.egress` | Security checks | Network access requirements |
| `permissions.secrets` | Secret injection | Required secrets list |
| `complexityProfile` | AMSP selection | Task complexity metrics |

## Runtime Consumers (9+ Components)

The following components depend on the JSON manifest format:

### Phase 1 (DCF) Tools
1. **`validate_skill_manifest.py`** - Schema validation
2. **`load_skill.py`** - Attaches skill to agent
3. **`unload_skill.py`** - Detaches skill from agent
4. **`get_skillset.py`** - Lists available skills
5. **`get_skillset_from_catalog.py`** - Fast skill discovery

### Phase 2 (DCF+) Tools
6. **`delegate_task.py`** - Reads complexityProfile for AMSP
7. **`create_companion.py`** - May use skill metadata

### Agent Prompts
8. **Planner/Conductor** - Use skill discovery output
9. **Worker/Companion** - Load skills via tool calls

## Safe vs Unsafe Changes

### Safe Changes (Authoring Layer)
- Reorganize YAML file directory structure
- Rename YAML files
- Change YAML internal structure
- Add new YAML-only fields (ignored by generators)
- Modify generator logic

### Unsafe Changes (Runtime Layer)
- Rename JSON manifest fields
- Change JSON schema structure
- Alter the manifest ID format
- Modify tool reference format (`server:tool_name`)
- Change complexityProfile field names

## Fallback Safety

The AMSP `complexityProfile` field has built-in fallback behavior:

```python
# From compute_task_complexity.py
def compute_task_complexity(skill_manifests: list[dict]) -> dict:
    if not skill_manifests:
        return {
            "fcs": 6.0,  # Default moderate complexity
            "tier": 0,
            "method": "fallback_no_skills"
        }

    # Skills without complexityProfile get defaults
    base_wcs = profile.get("baseWCS", 6)
    dimension_scores = profile.get("dimensionScores", {})
```

This means:
- Missing `complexityProfile` → uses sensible defaults
- Invalid dimension scores → uses zeros
- System degrades gracefully, not catastrophically

## Refactoring Guidelines

When proceeding with Phase 1 (DCF Cleanup) and Phase 2 (Electron App):

1. **Freely modify** the `skills_src/` YAML structure
2. **Update generators** to produce the same JSON output format
3. **Never change** the JSON manifest schema without updating all consumers
4. **Test generators** to ensure JSON output remains identical
5. **Add new fields** to YAML that don't map to JSON (authoring metadata)

## Verification Strategy

Before merging any refactoring:

```bash
# 1. Generate manifests with new structure
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; generate_all()'

# 2. Compare JSON output with baseline
diff -r generated/manifests/ baseline/manifests/

# 3. Run all skill-related tests
docker exec lettaplus-dcf-mcp-1 python -m pytest tests/ -k skill

# 4. Verify agents can still load skills
# (integration test with Letta API)
```

## Related Documentation

- `SKILLS.md` - Skill authoring guide (will need updates after refactoring)
- `skill_cli/README.md` - CLI tool documentation
- `CLAUDE.md` - Project overview with skill pipeline section
- `generated/schemas/skill.schema.json` - JSON Schema for validation

---

*Document created: 2026-02-05*
*Context: Pre-refactoring investigation for AMSP-DCF integration project*
