import os
import redis

def json_increment(
    key: str,
    path: str,
    delta: float,
    *,
    redis_url: str = ""
) -> dict:
    """
    Increment a numeric field by `delta`.

    Behavior:
      - Initializes a missing field to 0, then adds `delta`.
      - Errors if the existing value is not numeric.
      - Result is stored as int if it is exactly integral; otherwise float.
      - Incrementing at root "$" is not supported.

    Path rules:
      - "$.a.b" or "a.b" only (no bracket selectors, no indices).

    Args:
        key (str): Redis key of the JSON document.
        path (str): Path to a numeric field.
        delta (float): Amount to add (may be negative).
        redis_url (str): Optional Redis connection string.

    Returns:
        dict: { "success": bool, "error": str|None, "key": str, "doc_json": str|None }

    Examples:
        json_increment("k1", "counters.starts", 1.0)
    """
    rc = redis.Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    p = path.strip()
    if p == "$" or p == "":
        return {"success": False, "error": "Increment at `$` is not supported.", "key": key, "doc_json": None}
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
        cur[leaf] = 0
    val = cur[leaf]
    if not isinstance(val, (int, float)):
        return {"success": False, "error": "Target is not numeric.", "key": key, "doc_json": None}
    new_val = float(val) + float(delta)
    cur[leaf] = int(new_val) if float(new_val).is_integer() else float(new_val)

    rc.json().set(key, "$", doc)
    return {"success": True, "error": None, "key": key, "doc_json": json.dumps(doc)}
