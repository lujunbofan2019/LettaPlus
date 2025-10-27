from typing import Any, Dict
import os
import json
import redis
import ast

def json_append(
    redis_key: str,
    path: str,
    value_json: str
) -> Dict[str, Any]:
    """
    Append a JSON value to an array at the given path.

    Creates the array if it does not exist. Errors if the target exists but is not an array.
    Appending at the root "$" is not supported.

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Path to the array. "$.a.b" or "a.b" only, no bracket selectors, no indices.
        value_json (str): Element to append, encoded as JSON (e.g., '"x"', '123', '{}').

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    # --- 1) Parse value_json robustly (JSON -> ast.literal_eval -> raw string) ---
    try:
        if isinstance(value_json, str):
            s = value_json.strip()
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
                    parsed_value = json.loads(s)
                except json.JSONDecodeError:
                    try:
                        parsed_value = ast.literal_eval(s)
                    except Exception:
                        parsed_value = s  # final fallback: treat token as raw string
        else:
            parsed_value = value_json
        parsed_value = json.loads(json.dumps(parsed_value))  # normalize to pure JSON types
    except Exception as e:
        return {"success": False, "error": f"value_json is not valid or JSON-serializable: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 2) Normalize path and build RedisJSON path ---
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        return {"success": False, "error": "Appending at `$` is not supported.", "redis_key": redis_key, "doc_json": None}
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

    # --- 3) Try server-side ARRAPPEND first ---
    items = parsed_value if isinstance(parsed_value, list) else [parsed_value]
    try:
        rc.json().arrappend(redis_key, redis_path, *items)
    except redis.exceptions.ResponseError:
        # Fallback: create parents + array client-side, then write once
        doc = rc.json().get(redis_key, "$")
        if isinstance(doc, list) and doc:
            doc = doc[0]
        if doc is None:
            doc = {}

        cur = doc
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
            cur[leaf] = []
        if not isinstance(cur[leaf], list):
            return {"success": False, "error": "Target is not an array.", "redis_key": redis_key, "doc_json": None}

        if isinstance(parsed_value, list):
            cur[leaf].extend(parsed_value)
        else:
            cur[leaf].append(parsed_value)

        rc.json().set(redis_key, "$", doc)

    # --- 4) Return final doc ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}
