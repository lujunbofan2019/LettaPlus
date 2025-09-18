import os
import redis

def json_delete(
    redis_key: str,
    path: str
) -> dict:
    """
    Delete a value at the given path (or reset root to `{}`).

    If `path` is "$" or empty, the document is reset to an empty object `{}`. If the target path does not exist,
    the operation is a no-op (success=True). Only object fields can be deleted (no array index deletion).

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Path to delete. "$", "$.a.b", or "a.b" only, no bracket selectors, no indices.

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(redis_key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    p = path.strip()
    if p == "$" or p == "":
        if isinstance(doc, dict):
            doc.clear()
        rc.json().set(redis_key, "$", doc)
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": "{}"}

    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    if "[" in p or "]" in p:
        return {"success": False, "error": "Bracketed selectors are not supported.", "redis_key": redis_key, "doc_json": None}

    cur = doc
    parts = p.split(".") if p else []
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            rc.json().set(redis_key, "$", doc)
            return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)

    rc.json().set(redis_key, "$", doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}
