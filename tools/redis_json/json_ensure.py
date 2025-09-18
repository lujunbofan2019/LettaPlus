import os
import json
import redis
import ast

def json_ensure(
    redis_key: str,
    path: str,
    default_json: str
) -> dict:
    """
    Ensure a value exists at a path; if missing or null, set it to the default.

    Creates any missing parent objects. If the leaf is missing or is `null`, writes `default_json`.
    Does not modify the root "$" (use json_set for replacing the whole doc).

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Path to ensure (not "$"). "$.a.b" or "a.b" only, no bracket selectors, no indices.
        default_json (str): Default value to write, as a JSON string (e.g., "[]", "{}", '"x"').

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    # --- 1) Parse default_json robustly ---
    try:
        if isinstance(default_json, str):
            s = default_json.strip()
            if s.startswith("```"):
                nl = s.find("\n")
                if nl != -1:
                    s = s[nl+1:]
                if s.endswith("```"):
                    s = s[:-3]
                s = s.strip()
            if s == "":
                parsed_default = None
            else:
                try:
                    parsed_default = json.loads(s)
                except json.JSONDecodeError:
                    parsed_default = ast.literal_eval(s)
        else:
            parsed_default = default_json
        parsed_default = json.loads(json.dumps(parsed_default))  # normalize to pure JSON types
    except Exception as e:
        return {"success": False, "error": f"default_json is not valid or JSON-serializable: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 2) Normalize and validate path ---
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        # Contract: don't modify root here; just return current doc
        rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
        doc = rc.json().get(redis_key, "$")
        if isinstance(doc, list) and doc:
            doc = doc[0]
        if doc is None:
            doc = {}
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}

    if p_raw.startswith("$."):
        p = p_raw[2:]
    elif p_raw.startswith("$"):
        p = p_raw[1:]
    else:
        p = p_raw

    if "[" in p or "]" in p or p == "" or p.startswith(".") or p.endswith(".") or ".." in p:
        return {"success": False, "error": "Invalid path; use dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}

    redis_path = "$." + p
    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # --- 3) Fast path: server-side JSON.SET ... NX (sets only if leaf missing and parents exist) ---
    try:
        rc.json().set(redis_key, redis_path, parsed_default, nx=True)
    except redis.exceptions.ResponseError:
        # Parent path likely missing; we'll handle below.
        pass
    except Exception as e:
        return {"success": False, "error": f"Ensure error: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 4) Distinguish null vs. absent using JSON.TYPE ---
    try:
        leaf_type = rc.json().type(redis_key, redis_path)
    except redis.exceptions.ResponseError:
        leaf_type = None
    if isinstance(leaf_type, list):
        leaf_type = leaf_type[0] if leaf_type else None

    if leaf_type == "null":
        # Exists but is null → overwrite server-side (no whole-doc write)
        try:
            rc.json().set(redis_key, redis_path, parsed_default)
        except Exception as e:
            return {"success": False, "error": f"Failed to overwrite null: {e}", "redis_key": redis_key, "doc_json": None}

    elif leaf_type is None:
        # Path still absent → parents missing or NX couldn't apply → minimal client-side parent creation
        root = rc.json().get(redis_key, "$")
        if isinstance(root, list) and root:
            root = root[0]
        if root is None:
            root = {}

        cur = root
        parts = p.split(".")
        for seg in parts[:-1]:
            if not isinstance(cur, dict):
                return {"success": False, "error": f"Cannot descend into non-object at '{seg}'", "redis_key": redis_key, "doc_json": None}
            nxt = cur.get(seg)
            if not isinstance(nxt, dict):
                cur[seg] = {}
                nxt = cur[seg]
            cur = nxt

        leaf = parts[-1]
        if leaf not in cur or cur[leaf] is None:
            cur[leaf] = parsed_default
            try:
                rc.json().set(redis_key, "$", root)
            except Exception as e:
                return {"success": False, "error": f"Persist failed: {e}", "redis_key": redis_key, "doc_json": None}
        # else: leaf exists and is non-null → nothing to do

    # else: leaf exists and is non-null → nothing to do

    # --- 5) Return final document ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    if final_doc is None:
        final_doc = {}
        rc.json().set(redis_key, "$", final_doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}