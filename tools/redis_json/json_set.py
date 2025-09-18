import os
import json
import redis
import ast

def json_set(
    redis_key: str,
    path: str,
    value_json: str
) -> dict:
    """
    Set a JSON value at a path inside a RedisJSON document.

    Creates missing parent objects automatically. Root `$` (or empty path) replaces the whole document, but the root must be an object.

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Target path. "$", "$.a.b", or "a.b" only, no bracket selectors, no array indices.
        value_json (str): The value to write, encoded as JSON.

    Returns:
        dict: {
            "success": bool,            # True on write success
            "error": str | None,        # Error message when success=False
            "redis_key": str,           # The Redis key used
            "doc_json": str | None      # JSON string of the entire document after the write
        }
    """
    # --- 1) Parse value_json robustly ---
    try:
        if isinstance(value_json, str):
            s = value_json.strip()
            # Strip accidental code fences like ```json ... ```
            if s.startswith("```"):
                newline = s.find("\n")
                if newline != -1:
                    s = s[newline + 1 :]
                if s.endswith("```"):
                    s = s[:-3]
                s = s.strip()
            if s == "":
                parsed_value = None
            else:
                try:
                    parsed_value = json.loads(s)  # proper JSON
                except json.JSONDecodeError:
                    parsed_value = ast.literal_eval(s)  # Python-literal fallback
        else:
            parsed_value = value_json  # some runners pass an object directly
        # Normalize to pure JSON types
        parsed_value = json.loads(json.dumps(parsed_value))
    except Exception as e:
        return {"success": False, "error": f"value_json is not valid or JSON-serializable: {e}", "redis_key": redis_key, "doc_json": None}

    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # --- 2) Normalize and validate path ---
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        # Root replace: require object at root for compatibility with other tools
        if not isinstance(parsed_value, dict):
            return {"success": False, "error": "Root `$` must be an object.", "redis_key": redis_key, "doc_json": None}
        try:
            rc.json().set(redis_key, "$", parsed_value)
        except Exception as e:
            return {"success": False, "error": f"Root set failed: {e}", "redis_key": redis_key, "doc_json": None}
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(parsed_value)}

    if p_raw.startswith("$."):
        p = p_raw[2:]
    elif p_raw.startswith("$"):
        p = p_raw[1:]
    else:
        p = p_raw

    # Validate simple dot-path syntax
    if "[" in p or "]" in p or p == "" or p.startswith(".") or p.endswith(".") or ".." in p:
        return {"success": False, "error": "Invalid path; use dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}

    redis_path = "$." + p

    # --- 3) Try server-side JSON.SET at subpath first ---
    try:
        rc.json().set(redis_key, redis_path, parsed_value)
        set_done = True
    except redis.exceptions.ResponseError:
        # Usually means parent path doesn't exist
        set_done = False
    except Exception as e:
        return {"success": False, "error": f"Set error: {e}", "redis_key": redis_key, "doc_json": None}

    if not set_done:
        # --- 4) Minimal client-side fallback: create parents, set once ---
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
        if not isinstance(cur, dict):
            return {"success": False, "error": "Leaf parent is not an object.", "redis_key": redis_key, "doc_json": None}
        cur[leaf] = parsed_value

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