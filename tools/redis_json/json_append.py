import os
import json
import redis

def json_append(
    key: str,
    path: str,
    value_json: str,
    *,
    redis_url: str = ""
) -> dict:
    """
    Append a JSON value to an array at the given path.

    Behavior:
      - Creates the array if it does not exist.
      - Errors if the target exists but is not an array.
      - Appending at the root "$" is not supported.

    Path rules:
      - "$.a.b" or "a.b" only (no bracket selectors, no indices).

    Args:
        key (str): Redis key of the JSON document.
        path (str): Path to the array (e.g., "events").
        value_json (str): Element to append, encoded as JSON (e.g., '"x"', '123', '{}').
        redis_url (str): Optional Redis connection string.

    Returns:
        dict: { "success": bool, "error": str|None, "key": str, "doc_json": str|None }

    Examples:
        json_append("k1", "events", '{"ts":"2025-09-04T09:00:00Z","type":"start"}')
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
        return {"success": False, "error": "Appending at `$` is not supported.", "key": key, "doc_json": None}
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
    leaf = parts[-1]
    if leaf not in cur:
        cur[leaf] = []
    if not isinstance(cur[leaf], list):
        return {"success": False, "error": "Target is not an array.", "key": key, "doc_json": None}
    cur[leaf].append(value)

    rc.json().set(key, "$", doc)
    return {"success": True, "error": None, "key": key, "doc_json": json.dumps(doc)}
