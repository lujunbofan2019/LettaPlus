import os
import json
import redis

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
    try:
        default_val = json.loads(default_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"default_json invalid: {e}", "redis_key": redis_key, "doc_json": None}

    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(redis_key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    p = path.strip()
    if p == "$" or p == "":
        # do nothing at root (use set for that)
        rc.json().set(redis_key, "$", doc)
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}
    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    if "[" in p or "]" in p:
        return {"success": False, "error": "Bracketed selectors are not supported.", "redis_key": redis_key, "doc_json": None}

    cur = doc
    parts = p.split(".") if p else []
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            return {"success": False, "error": f"Cannot descend into non-object at '{part}'", "redis_key": redis_key, "doc_json": None}
        if part not in cur or not isinstance(cur[part], (dict, list)):
            cur[part] = {}
        cur = cur[part]
    if not isinstance(cur, dict):
        return {"success": False, "error": "Leaf parent is not an object.", "redis_key": redis_key, "doc_json": None}
    leaf = parts[-1]
    if leaf not in cur or cur[leaf] is None:
        cur[leaf] = default_val

    rc.json().set(redis_key, "$", doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}
