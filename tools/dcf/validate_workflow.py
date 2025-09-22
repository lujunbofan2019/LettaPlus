import json
import os
from urllib.parse import urlparse
from jsonschema import Draft202012Validator

def validate_workflow(workflow_json, schema_path, imports_base_dir=None, skills_base_dir=None):
    """Validate a Letta–ASL workflow (v2.2.0) and resolve .af and skill references.

      1) Validates the workflow instance against the v2.2.0 workflow JSON Schema.
      2) Loads .af v2 bundles from `af_imports[*].uri` and builds an agent index (by id and by name).
      3) Loads skill manifests from `skill_imports[*].uri` (single or {"skills": [...]}) and indexes them by:
         - manifestId
         - skillPackageId
         - skillName@skillVersion (case-insensitive)
         - skill://skillPackageId@skillVersion
         - skill://skillName@skillVersion (case-insensitive)
      4) Resolves each Task state's AgentBinding:
         - requires either agent_template_ref or agent_ref
         - resolves agent refs against .af imports
         - resolves `skills` array to imported manifests
      5) Performs ASL graph checks (StartAt present, valid transitions, terminal sanity).

    Args:
      workflow_json: String containing the workflow JSON instance to validate.
      schema_path: Filesystem path to the v2.2.0 workflow JSON Schema file.
      imports_base_dir: Optional base dir for resolving relative .af import URIs (defaults to schema dir).
      skills_base_dir: Optional base dir for resolving skill manifest URIs (defaults to imports_base_dir).

    Returns:
      Dict shaped for agent consumption:
        {
          "ok": bool,
          "exit_code": int,  # 0 OK, 1 schema validation errors, 2 imports/refs validation errors, 3 graph validation errors, 4 other errors
          "schema_errors": [str],
          "resolution": {
            "af_imports_loaded": [{"uri": str, "status": "ok|error", "error": str|None, "agents": int, "tools": int}],
            "skill_imports_loaded": [{"uri": str, "status": "ok|error", "error": str|None, "skills": int}],
            "agents_index_size": int,
            "skills_index_size": int,
            "unresolved_agent_refs": [{"where": str, "ref": {"id": str|None, "name": str|None}}],
            "unresolved_skill_ids": [str],
            "state_skill_map": { "StateName": [{"skill": str, "manifestId": str}] }
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
    out = {
        "ok": False,
        "exit_code": 4,
        "schema_errors": [],
        "resolution": {
            "af_imports_loaded": [],
            "skill_imports_loaded": [],
            "agents_index_size": 0,
            "skills_index_size": 0,
            "unresolved_agent_refs": [],
            "unresolved_skill_ids": [],
            "state_skill_map": {}
        },
        "graph": {},
        "warnings": []
    }

    # ---------- Parse workflow + load schema ----------
    try:
        inst = json.loads(workflow_json)
    except Exception as ex:
        out["warnings"].append("JSONDecodeError: %s" % ex)
        out["exit_code"] = 4
        return out

    try:
        schema_abs = os.path.abspath(schema_path)
        with open(schema_abs, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as ex:
        out["warnings"].append("SchemaLoadError: %s" % ex)
        out["exit_code"] = 4
        return out

    if imports_base_dir is None:
        imports_base_dir = os.path.dirname(schema_abs)
    if skills_base_dir is None:
        skills_base_dir = imports_base_dir

    # ---------- 1) JSON Schema validation ----------
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(inst), key=lambda e: list(e.path))
        if errors:
            for e in errors:
                path = "/".join(map(str, e.path)) or "<root>"
                out["schema_errors"].append("%s: %s" % (path, e.message))
            out["exit_code"] = 1
            return out
    except Exception as ex:
        out["warnings"].append("SchemaValidationError: %s" % ex)
        out["exit_code"] = 4
        return out

    # ---------- 2) Option B enforcement ----------
    if "af_v2_entities" in inst:
        out["warnings"].append("Embedded 'af_v2_entities' is not supported in Option B.")
        out["exit_code"] = 2
        return out

    # ---------- 3) Load .af v2 imports ----------
    af_tools_index = {}   # by tool name
    af_agents_index = {}  # by id and by name

    for imp in (inst.get("af_imports") or []):
        uri = (imp or {}).get("uri")
        rec = {"uri": uri, "status": "ok", "error": None, "agents": 0, "tools": 0}
        try:
            if not uri:
                raise ValueError("Missing af_imports[*].uri")
            parsed = urlparse(uri)
            scheme = parsed.scheme
            if scheme in ("", "file"):
                path = parsed.path if scheme == "file" else uri
                if not os.path.isabs(path):
                    path = os.path.normpath(os.path.join(imports_base_dir, path))
                with open(path, "r", encoding="utf-8") as f:
                    bundle = json.load(f)
            else:
                raise ValueError("Only file paths/file:// URIs are allowed for af_imports: %s" % uri)

            agents = (bundle.get("agents") or [])
            tools = (bundle.get("tools") or [])
            for a in agents:
                aid = a.get("id")
                aname = a.get("name")
                if aid:   af_agents_index[aid] = a
                if aname: af_agents_index[aname] = a
            for t in tools:
                tname = t.get("name")
                if tname: af_tools_index[tname] = t

            rec["agents"] = len(agents)
            rec["tools"]  = len(tools)
        except Exception as ex:
            rec["status"] = "error"
            rec["error"] = "%s: %s" % (type(ex).__name__, ex)
        out["resolution"]["af_imports_loaded"].append(rec)

    out["resolution"]["agents_index_size"] = len(af_agents_index)

    # ---------- 4) Load skill manifests ----------
    # An import may be a single manifest or { "skills": [ ... ] }
    skills_index = {}   # key -> manifest object
    # also track canonical id by manifestId for reporting
    for simp in (inst.get("skill_imports") or []):
        uri = (simp or {}).get("uri")
        rec = {"uri": uri, "status": "ok", "error": None, "skills": 0}
        try:
            if not uri:
                raise ValueError("Missing skill_imports[*].uri")
            parsed = urlparse(uri)
            scheme = parsed.scheme
            if scheme in ("", "file"):
                path = parsed.path if scheme == "file" else uri
                if not os.path.isabs(path):
                    path = os.path.normpath(os.path.join(skills_base_dir, path))
                with open(path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
            else:
                raise ValueError("Only file paths/file:// URIs are allowed for skill_imports: %s" % uri)

            def _index_one(m):
                if not isinstance(m, dict):
                    return
                manifestId = m.get("manifestId")
                pkgId = m.get("skillPackageId")
                name = (m.get("skillName") or "").strip()
                ver = (m.get("skillVersion") or "").strip()
                if manifestId:
                    skills_index.setdefault(manifestId, m)
                if pkgId:
                    skills_index.setdefault(pkgId, m)
                    if ver:
                        skills_index.setdefault("skill://%s@%s" % (pkgId, ver), m)
                if name and ver:
                    skills_index.setdefault("%s@%s" % (name.lower(), ver), m)
                    skills_index.setdefault("skill://%s@%s" % (name.lower(), ver), m)

            if isinstance(doc, dict) and isinstance(doc.get("skills"), list):
                for m in (doc.get("skills") or []):
                    _index_one(m)
                rec["skills"] = len(doc.get("skills") or [])
            else:
                _index_one(doc)
                rec["skills"] = 1
        except Exception as ex:
            rec["status"] = "error"
            rec["error"] = "%s: %s" % (type(ex).__name__, ex)
        out["resolution"]["skill_imports_loaded"].append(rec)

    out["resolution"]["skills_index_size"] = len(skills_index)

    # ---------- 5) Resolve AgentBinding + skills in ASL ----------
    unresolved_agent_refs = []
    unresolved_skill_ids = []
    state_skill_map = {}

    asl = inst.get("asl") or {}
    states = asl.get("States") or {}
    for sname, sdef in states.items():
        if not isinstance(sdef, dict):
            continue
        if sdef.get("Type") != "Task":
            continue
        ab = sdef.get("AgentBinding")
        if not isinstance(ab, dict):
            unresolved_agent_refs.append({
                "where": "asl.States['%s']" % sname,
                "ref": {"id": None, "name": None}
            })
            continue

        # require either agent_template_ref or agent_ref
        has_any = False
        for key in ("agent_template_ref", "agent_ref"):
            ref = ab.get(key)
            if isinstance(ref, dict) and (ref.get("id") or ref.get("name")):
                has_any = True
                rid = ref.get("id")
                rname = ref.get("name")
                ok = False
                if rid and rid in af_agents_index:
                    ok = True
                if (not ok) and rname and rname in af_agents_index:
                    ok = True
                if not ok:
                    unresolved_agent_refs.append({
                        "where": "asl.States['%s'].AgentBinding.%s" % (sname, key),
                        "ref": {"id": rid, "name": rname}
                    })
        if not has_any:
            unresolved_agent_refs.append({
                "where": "asl.States['%s'].AgentBinding (missing agent_template_ref/agent_ref)" % sname,
                "ref": {"id": None, "name": None}
            })

        # skills resolution
        resolved_list = []
        for sid in (ab.get("skills") or []):
            key = sid
            # normalize possible name@ver to lowercase for name part
            if isinstance(key, str) and "@" in key and not key.lower().startswith("skill://"):
                name, ver = key.split("@", 1)
                key_try = "%s@%s" % (name.lower(), ver)
                m = skills_index.get(key) or skills_index.get(key_try)
            else:
                m = skills_index.get(key) or skills_index.get(key.lower()) if isinstance(key, str) else None
            if not m:
                unresolved_skill_ids.append(sid)
            else:
                resolved_list.append({"skill": sid, "manifestId": m.get("manifestId")})
        if resolved_list:
            state_skill_map[sname] = resolved_list

    out["resolution"]["unresolved_agent_refs"] = unresolved_agent_refs
    out["resolution"]["unresolved_skill_ids"] = unresolved_skill_ids
    out["resolution"]["state_skill_map"] = state_skill_map

    if (any(r.get("status") == "error" for r in out["resolution"]["af_imports_loaded"]) or
        any(r.get("status") == "error" for r in out["resolution"]["skill_imports_loaded"]) or
        unresolved_agent_refs or unresolved_skill_ids):
        out["exit_code"] = 2
        return out

    # ---------- 6) ASL graph checks ----------
    graph = {
        "start_exists": False,
        "missing_states": [],
        "unreachable_states": [],
        "invalid_transitions": [],
        "terminal_states_ok": True
    }

    states = asl.get("States") or {}
    start = asl.get("StartAt")
    if not start or start not in states:
        graph["start_exists"] = False
        graph["missing_states"] = [start] if start else ["<missing StartAt>"]
        out["graph"] = graph
        out["exit_code"] = 3
        return out
    graph["start_exists"] = True

    referenced = set()
    for name, sd in states.items():
        if not isinstance(sd, dict):
            continue

        # Next
        if "Next" in sd:
            nxt = sd["Next"]
            if nxt not in states:
                graph["invalid_transitions"].append({"state": name, "to": nxt})
            else:
                referenced.add(nxt)

        # Choice
        if sd.get("Type") == "Choice":
            for ch in (sd.get("Choices") or []):
                nxt = ch.get("Next")
                if nxt:
                    if nxt not in states:
                        graph["invalid_transitions"].append({"state": name, "to": nxt})
                    else:
                        referenced.add(nxt)
            default = sd.get("Default")
            if default:
                if default not in states:
                    graph["invalid_transitions"].append({"state": name, "to": default})
                else:
                    referenced.add(default)

        # Parallel
        if sd.get("Type") == "Parallel":
            for i, br in enumerate(sd.get("Branches") or []):
                bst = (br.get("States") or {})
                if br.get("StartAt") not in bst:
                    graph["invalid_transitions"].append({"state": name, "to": "branch[%d].StartAt" % i})

        # Map
        if sd.get("Type") == "Map":
            it = sd.get("Iterator") or {}
            ist = (it.get("States") or {})
            if it.get("StartAt") not in ist:
                graph["invalid_transitions"].append({"state": name, "to": "Iterator.StartAt"})

        # Terminal sanity
        if sd.get("End") is True and "Next" in sd:
            graph["terminal_states_ok"] = False

    graph["unreachable_states"] = [s for s in states.keys() if s != start and s not in referenced]
    out["graph"] = graph
    if (not graph["start_exists"]) or graph["invalid_transitions"] or (not graph["terminal_states_ok"]):
        out["exit_code"] = 3
        return out

    # ---------- Success ----------
    out["ok"] = True
    out["exit_code"] = 0
    return out
