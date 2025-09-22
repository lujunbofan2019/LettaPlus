import json
import os
from urllib.parse import urlparse
from jsonschema import Draft202012Validator


def validate_workflow(workflow_json, schema_path, imports_base_dir=None) -> dict:
    """Validate a Letta–ASL workflow JSON and resolve its .af v2 references.

      1) Validation of the workflow instance against JSON schema file.
      2) Checking imported .af v2 entity references.
      3) Basic ASL graph validation (StartAt exists, transitions valid, terminal sanity).

    Args:
      workflow_json: String containing the workflow JSON instance to validate.
      schema_path: Filesystem path to the workflow JSON Schema (e.g., "schemas/letta-asl-workflow-option-b-2.1.0.json").
      imports_base_dir: Optional base directory for resolving relative import URIs.

    Returns:
      Dict with the following structure:
        {
          "ok": bool,
          "exit_code": int,  # 0 OK, 1 schema validation errors, 2 imports/refs errors, 3 graph validation errors, 4 other errors
          "schema_errors": [str],
          "resolution": {
            "imports_loaded": [
              {"uri": str, "status": "ok"|"error", "error": str|None, "agents": int, "tools": int}
            ],
            "agents_index_size": int,
            "unresolved_agent_refs": [
              {"where": str, "ref": {"id": str|None, "name": str|None}}
            ]
          },
          "graph": {
            "start_exists": bool,
            "missing_states": [str],
            "unreachable_states": [str],
            "invalid_transitions": [{"state": str, "to": str}],
            "terminal_states_ok": bool
          },
          "warnings": [str]
        }
    """
    result = {
        "ok": False,
        "exit_code": 4,
        "schema_errors": [],
        "resolution": {
            "imports_loaded": [],
            "agents_index_size": 0,
            "unresolved_agent_refs": []
        },
        "graph": {},
        "warnings": []
    }

    # ---------- Parse workflow + load schema ----------
    try:
        workflow = json.loads(workflow_json)
    except Exception as ex:
        result["warnings"].append("JSONDecodeError: %s" % ex)
        result["exit_code"] = 4
        return result

    try:
        schema_abs = os.path.abspath(schema_path)
        with open(schema_abs, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as ex:
        result["warnings"].append("SchemaLoadError: %s" % ex)
        result["exit_code"] = 4
        return result

    if imports_base_dir is None:
        imports_base_dir = os.path.dirname(schema_abs)

    # ---------- 1) JSON Schema validation ----------
    try:
        validator = Draft202012Validator(schema)
        schema_errors = sorted(validator.iter_errors(workflow), key=lambda e: list(e.path))
        if schema_errors:
            for e in schema_errors:
                path = "/".join(map(str, e.path))
                result["schema_errors"].append("%s: %s" % (path or "<root>", e.message))
            result["exit_code"] = 1
            return result
    except Exception as ex:
        result["warnings"].append("SchemaValidationError: %s" % ex)
        result["exit_code"] = 4
        return result

    # ---------- 2) Option B enforcement ----------
    if "af_v2_entities" in (workflow or {}):
        result["warnings"].append("Embedded 'af_v2_entities' is not supported in Option B.")
        result["exit_code"] = 2
        return result

    # ---------- 3) Imports load + agent_ref resolution ----------
    bundles = []
    imports = workflow.get("imports") or []
    for imp in imports:
        uri = (imp or {}).get("uri")
        rec = {"uri": uri, "status": "ok", "error": None, "agents": 0, "tools": 0}
        try:
            if not uri:
                raise ValueError("Missing import.uri")

            parsed = urlparse(uri)
            scheme = parsed.scheme

            if scheme in ("", "file"):
                path = parsed.path if scheme == "file" else uri
                if not os.path.isabs(path):
                    path = os.path.normpath(os.path.join(imports_base_dir, path))
                with open(path, "r", encoding="utf-8") as f:
                    bundle = json.load(f)
            elif scheme in ("http", "https"):
                # HTTP(S) is not allowed by design.
                raise ValueError("HTTP imports are not allowed in Option B: %s" % uri)
            else:
                raise ValueError("Unsupported URI scheme for imports: %s" % (scheme or "(none)"))

            bundles.append(bundle)
            rec["agents"] = len(bundle.get("agents") or [])
            rec["tools"] = len(bundle.get("tools") or [])
        except Exception as ex:
            rec["status"] = "error"
            rec["error"] = "%s: %s" % (type(ex).__name__, ex)
        result["resolution"]["imports_loaded"].append(rec)

    # Build index of agents by id and by name (later bundles win)
    idx = {}
    for b in bundles:
        for agent in (b.get("agents") or []):
            aid = agent.get("id")
            aname = agent.get("name")
            if aid:
                idx[aid] = agent
            if aname:
                idx[aname] = agent
    result["resolution"]["agents_index_size"] = len(idx)

    # Collect all agent_ref occurrences
    unresolved = []

    # Top-level agents[*].agent_ref
    for i, a in enumerate(workflow.get("agents") or []):
        if isinstance(a, dict) and isinstance(a.get("agent_ref"), dict):
            ref = a["agent_ref"]
            rid = ref.get("id")
            rname = ref.get("name")
            ok = (rid in idx) if rid else False
            if not ok:
                ok = (rname in idx) if rname else False
            if not ok:
                unresolved.append({"where": "agents[%d].agent_ref" % i, "ref": {"id": rid, "name": rname}})

    # ASL bindings: asl.States.*.AgentBinding.agent_ref
    asl = workflow.get("asl") or {}
    states = asl.get("States") or {}
    for sname, sdef in states.items():
        if not isinstance(sdef, dict):
            continue
        binding = sdef.get("AgentBinding")
        if isinstance(binding, dict) and isinstance(binding.get("agent_ref"), dict):
            ref = binding["agent_ref"]
            rid = ref.get("id")
            rname = ref.get("name")
            ok = (rid in idx) if rid else False
            if not ok:
                ok = (rname in idx) if rname else False
            if not ok:
                unresolved.append({
                    "where": "asl.States['%s'].AgentBinding.agent_ref" % sname,
                    "ref": {"id": rid, "name": rname}
                })

    result["resolution"]["unresolved_agent_refs"] = unresolved
    if any(r.get("status") == "error" for r in result["resolution"]["imports_loaded"]) or unresolved:
        result["exit_code"] = 2
        return result

    # ---------- 4) ASL graph checks ----------
    graph = {
        "start_exists": False,
        "missing_states": [],
        "unreachable_states": [],
        "invalid_transitions": [],
        "terminal_states_ok": True
    }
    if isinstance(asl, dict):
        states = asl.get("States") or {}
        start = asl.get("StartAt")

        if not start or start not in states:
            graph["start_exists"] = False
            graph["missing_states"] = [start] if start else ["<missing StartAt>"]
            result["graph"] = graph
            result["exit_code"] = 3
            return result

        graph["start_exists"] = True
        referenced = set()

        for name, sdef in states.items():
            if not isinstance(sdef, dict):
                continue

            # Next
            if "Next" in sdef:
                nxt = sdef["Next"]
                if nxt not in states:
                    graph["invalid_transitions"].append({"state": name, "to": nxt})
                else:
                    referenced.add(nxt)

            # Choice
            if sdef.get("Type") == "Choice":
                for ch in (sdef.get("Choices") or []):
                    nxt = ch.get("Next")
                    if nxt:
                        if nxt not in states:
                            graph["invalid_transitions"].append({"state": name, "to": nxt})
                        else:
                            referenced.add(nxt)
                default = sdef.get("Default")
                if default:
                    if default not in states:
                        graph["invalid_transitions"].append({"state": name, "to": default})
                    else:
                        referenced.add(default)

            # Parallel branches
            if sdef.get("Type") == "Parallel":
                for i, br in enumerate(sdef.get("Branches") or []):
                    bst = (br.get("States") or {})
                    if br.get("StartAt") not in bst:
                        graph["invalid_transitions"].append({"state": name, "to": "branch[%d].StartAt" % i})

            # Map iterator
            if sdef.get("Type") == "Map":
                it = sdef.get("Iterator") or {}
                ist = (it.get("States") or {})
                if it.get("StartAt") not in ist:
                    graph["invalid_transitions"].append({"state": name, "to": "Iterator.StartAt"})

            # Terminal sanity: 'End': true should not coexist with 'Next'
            if sdef.get("End") is True and "Next" in sdef:
                graph["terminal_states_ok"] = False

        graph["unreachable_states"] = [s for s in states.keys() if s != start and s not in referenced]
        result["graph"] = graph

        if (not graph["start_exists"]) or graph["invalid_transitions"] or (not graph["terminal_states_ok"]):
            result["exit_code"] = 3
            return result

    # ---------- Success ----------
    result["ok"] = True
    result["exit_code"] = 0
    return result
