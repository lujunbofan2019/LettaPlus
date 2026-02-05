# Documentation Audit - Pre-Refactoring Review

This document identifies all documentation updates needed before and after the planned DCF skill authoring refactoring (Phase 1: DCF Cleanup, Phase 2: Electron App).

## Audit Summary

| Document | Priority | Status | Update Type |
|----------|----------|--------|-------------|
| `README.md` | HIGH | OUTDATED | Major rewrite - CSV references |
| `stub_mcp/README.md` | HIGH | OUTDATED | Minor updates - CSV references |
| `skills_src/SKILLS.md` | HIGH | CURRENT | Post-refactoring updates |
| `skill_cli/README.md` | MEDIUM | CURRENT | Post-refactoring updates |
| `dcf_mcp/tools/TOOLS.md` | LOW | MOSTLY CURRENT | Minor fix |
| `CLAUDE.md` | LOW | CURRENT | Minor updates after refactoring |

---

## 1. `README.md` (Main Project README)

**Priority**: HIGH
**Current Status**: OUTDATED
**Lines affected**: 395-542 ("Update Oct-2025" section)

### Issues Found

The "CSV-first rapid skill prototyping" section (lines 395-542) is entirely outdated:

1. **References CSV files that no longer exist**:
   - `skills.csv` → replaced by `skills_src/skills/*.skill.yaml`
   - `skill_tool_refs.csv` → embedded in YAML files
   - `mcp_tools.csv` → replaced by `skills_src/tools.yaml`
   - `mcp_cases.csv` → replaced by `skills_src/tools.yaml`

2. **References old generator commands**:
   - `csv_to_manifests.py` → replaced by `yaml_to_manifests()`
   - `csv_to_stub_config.py` → replaced by `yaml_to_stub_config()`

3. **Outdated mental model section** (lines 489-495):
   - Still describes CSV-based workflow

4. **Outdated example commands** (lines 529-533):
   - References `python skills_src/csv_to_manifests.py`

### Recommended Action

**BEFORE refactoring**: Rewrite lines 395-542 to reflect current YAML-based approach:
- Document the YAML skill authoring pipeline
- Reference correct source files and generators
- Update the mental model section
- Update example commands

---

## 2. `stub_mcp/README.md`

**Priority**: HIGH
**Current Status**: OUTDATED
**Lines affected**: 6, 34-36

### Issues Found

1. **Line 6**: References `csv_to_stub_config`:
   ```
   configuration from `generated/stub/stub_config.json`, the file produced by
   `dcf_mcp.tools.dcf.csv_to_stub_config`.
   ```
   Should reference `yaml_to_stub_config`

2. **Lines 34-36**: Outdated generator command:
   ```bash
   python -m dcf_mcp.tools.dcf.csv_to_stub_config
   ```
   Should reference the YAML-based generator

### Recommended Action

**BEFORE refactoring**: Update to reference YAML-based generation:
```python
python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
```

---

## 3. `skills_src/SKILLS.md`

**Priority**: HIGH (Post-refactoring)
**Current Status**: CURRENT (for now)
**Lines affected**: TBD after refactoring

### Current Structure (1,550 lines)

The document currently covers:
- YAML Skill Authoring (lines 1-150)
- Skill File Structure (lines 150-300)
- Tools.yaml Format (lines 300-500)
- Registry.yaml Format (lines 500-600)
- Generation Pipeline (lines 600-800)
- Real vs Simulated Skills (lines 800-1000)
- BDD Test Cases (lines 1000-1200)
- Examples (lines 1200-1550)

### Expected Changes After Refactoring

If Phase 1 reorganizes the authoring layer:
1. Directory structure section will need updates
2. File naming conventions may change
3. Generation commands may change
4. Package-based organization (if implemented)

### Recommended Action

**AFTER refactoring**: Update to reflect:
- New directory structure
- New file organization
- Any new authoring patterns
- Updated generation commands

---

## 4. `skill_cli/README.md`

**Priority**: MEDIUM (Post-refactoring)
**Current Status**: CURRENT (for now)
**Lines**: 425 lines

### Current Content

Documents the CLI tool for skill authoring:
- Commands: `create`, `validate`, `generate`, `list`
- Real vs Simulated skill modes
- BDD test case creation

### Expected Changes After Refactoring

Depends on whether `skill_cli` is:
1. **Kept**: May need updates to reflect new directory structure
2. **Deprecated**: Document should be archived or removed
3. **Replaced by Electron app**: Document should redirect to new tool

### Recommended Action

**AFTER Phase 2 (Electron App)**: Determine fate of CLI tool and update accordingly.

---

## 5. `dcf_mcp/tools/TOOLS.md`

**Priority**: LOW
**Current Status**: MOSTLY CURRENT
**Lines affected**: 54

### Issues Found

1. **Line 54**: Lists CSV-based tools in response format section:
   ```
   **Tools using this pattern**: `validate_workflow`, `validate_skill_manifest`,
   `load_skill`, `csv_to_manifests`, `csv_to_stub_config`
   ```
   Should reference `yaml_to_manifests`, `yaml_to_stub_config`

### Recommended Action

**BEFORE refactoring**: Minor fix to line 54 - update tool names.

---

## 6. `CLAUDE.md`

**Priority**: LOW
**Current Status**: CURRENT
**Lines affected**: TBD after refactoring

### Current Status

The "YAML Skill Pipeline" section (lines ~240-300) is accurate and documents:
- Source files (YAML)
- Generated files (JSON)
- Generation pipeline
- Important note about not editing generated files

### Expected Changes After Refactoring

If Phase 1 changes directory structure:
- Update source file paths
- Update generated file paths
- Update generation commands

### Recommended Action

**AFTER refactoring**: Review and update if directory structure changes.

---

## 7. Other Documents (No Changes Needed)

The following documents are either background/research docs or already up-to-date:

| Document | Reason |
|----------|--------|
| `docs/Architectural_Evolution_Opus.md` | Architectural overview, not affected |
| `docs/research/AMSP-DCF-Integration-Progress.md` | Already updated with latest |
| `docs/background/*.md` | Historical/design documents |
| `docs/testing/*.md` | Testing guides, may need minor updates |
| `prompts/dcf_plus/*.md` | Agent prompts, already updated with AMSP |
| `graphiti/ENTITY_TYPES.md` | Knowledge graph types, not affected |
| `AGENTS.md` | Agent definitions, not affected |

---

## Action Plan

### Immediate (Before Refactoring)

1. **Fix `README.md`** (HIGH priority)
   - Rewrite "Update Oct-2025" section for YAML-based approach
   - Update all CSV references to YAML
   - Update example commands

2. **Fix `stub_mcp/README.md`** (HIGH priority)
   - Update generator reference on line 6
   - Update command example on lines 34-36

3. **Fix `dcf_mcp/tools/TOOLS.md`** (LOW priority)
   - Update tool names on line 54

### After Phase 1 Refactoring

4. **Update `skills_src/SKILLS.md`**
   - Reflect new directory structure
   - Update file organization documentation

5. **Review `CLAUDE.md`**
   - Update paths if changed
   - Update generation commands if changed

### After Phase 2 (Electron App)

6. **Decide fate of `skill_cli/README.md`**
   - Keep and update, OR
   - Archive/deprecate, OR
   - Redirect to Electron app documentation

7. **Create Electron app documentation**
   - New user guide for GUI-based authoring
   - Installation instructions
   - Feature documentation

---

## Cross-Reference: Related Documentation

For context, also review:
- `skills_src/SKILL_RUNTIME_DEPENDENCIES.md` - NEW: Documents safe vs unsafe changes
- `docs/research/TODO-AMSP-DCF-Integration.md` - AMSP integration TODO
- `docs/research/AMSP-DCF-Integration-Progress.md` - AMSP integration progress

---

*Audit performed: 2026-02-05*
*Context: Pre-refactoring documentation review*
