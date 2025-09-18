import os
import json
import redis

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
    try:
        value = json.loads(value_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"value_json invalid: {e}", "redis_key": redis_key, "doc_json": None}

    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(redis_key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    p = path.strip()
    if p == "$" or p == "":
        if not isinstance(value, dict):
            return {"success": False, "error": "Root `$` must be an object.", "redis_key": redis_key, "doc_json": None}
        rc.json().set(redis_key, "$", value)
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(value)}

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
    cur[parts[-1]] = value

    rc.json().set(redis_key, "$", doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}
