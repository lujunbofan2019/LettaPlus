from typing import Any, Dict
import os
import json
import redis
import ast

def json_ensure(
    redis_key: str,
    path: str,
    default_json: str
) -> Dict[str, Any]:
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
    # --- 1) Parse default_json robustly (JSON -> ast.literal_eval -> raw string) ---
    try:
        if isinstance(default_json, str):
            s = default_json.strip()
            if s.startswith("```"):
                newline = s.find("\n")
                if newline != -1:
                    s = s[newline + 1 :]
                if s.endswith("```"):
                    s = s[:-3]
                s = s.strip()
            if s == "":
                parsed_default = None
            else:
                try:
                    parsed_default = json.loads(s)
                except json.JSONDecodeError:
                    try:
                        parsed_default = ast.literal_eval(s)
                    except Exception:
                        parsed_default = s  # final fallback: raw string
        else:
            parsed_default = default_json
        parsed_default = json.loads(json.dumps(parsed_default))  # normalize to pure JSON types
    except Exception as e:
        return {"success": False, "error": f"default_json is not valid or JSON-serializable: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 2) Normalize and validate path ---
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
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

    # --- 3) Fast path: JSON.SET ... NX (sets only if missing and parents exist) ---
    try:
        rc.json().set(redis_key, redis_path, parsed_default, nx=True)
    except redis.exceptions.ResponseError:
        pass
    except Exception as e:
        return {"success": False, "error": f"Ensure error: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 4) Distinguish null vs absent with JSON.TYPE ---
    try:
        leaf_type = rc.json().type(redis_key, redis_path)
    except redis.exceptions.ResponseError:
        leaf_type = None
    if isinstance(leaf_type, list):
        leaf_type = leaf_type[0] if leaf_type else None

    if leaf_type == "null":
        # Exists but null → overwrite server-side
        try:
            rc.json().set(redis_key, redis_path, parsed_default)
        except Exception as e:
            return {"success": False, "error": f"Failed to overwrite null: {e}", "redis_key": redis_key, "doc_json": None}
    elif leaf_type is None:
        # Absent → create parents client-side, set once
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

    # --- 5) Return final doc ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    if final_doc is None:
        final_doc = {}
        rc.json().set(redis_key, "$", final_doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}
