import os
import json
import redis

def json_set(
    key: str,
    path: str,
    value_json: str,
    *,
    redis_url: str = ""
) -> dict:
    """
    Set a JSON value at a path inside a RedisJSON document.

    Simple rules:
      - Creates missing parent objects automatically.
      - Root `$` (or empty path) replaces the whole document, but the root must be an **object**.
      - Only dot paths are supported: "$", "$.a.b", or "a.b". No bracket selectors or array indices.

    Args:
        key (str): Redis key of the JSON document.
        path (str): Target path. "$" or dot path like "$.a.b" / "a.b".
        value_json (str): The value to write, encoded as JSON (e.g., '"x"', '123', 'true', '{}', '[]').
        redis_url (str): Optional Redis connection string. Defaults to REDIS_URL env var or "redis://redis:6379/0".

    Returns:
        dict: {
            "success": bool,            # True on write success
            "error": str | None,        # Error message when success=False
            "key": str,                 # The Redis key used
            "doc_json": str | None      # JSON string of the entire document after the write
        }

    Examples:
        json_set("k1", "$", '{"status":"pending","meta":{}}')
        json_set("k1", "meta.started_at", '"2025-09-04T09:00:00Z"')
    """
    try:
        value = json.loads(value_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"value_json invalid: {e}", "key": key, "doc_json": None}

    rc = redis.Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    p = path.strip()
    if p == "$" or p == "":
        if not isinstance(value, dict):
            return {"success": False, "error": "Root `$` must be an object.", "key": key, "doc_json": None}
        rc.json().set(key, "$", value)
        return {"success": True, "error": None, "key": key, "doc_json": json.dumps(value)}

    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    if "[" in p or "]" in p:
        return {"success": False, "error": "Bracketed selectors are not supported.", "key": key, "doc_json": None}

    cur = doc
    parts = p.split(".") if p else []
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            return {"success": False, "error": f"Cannot descend into non-object at '{part}'", "key": key, "doc_json": None}
        if part not in cur or not isinstance(cur[part], (dict, list)):
            cur[part] = {}
        cur = cur[part]
    if not isinstance(cur, dict):
        return {"success": False, "error": "Leaf parent is not an object.", "key": key, "doc_json": None}
    cur[parts[-1]] = value

    rc.json().set(key, "$", doc)
    return {"success": True, "error": None, "key": key, "doc_json": json.dumps(doc)}
