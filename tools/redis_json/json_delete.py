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

    # Root reset
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        rc.json().set(redis_key, "$", {})  # write empty object
        final_doc = rc.json().get(redis_key, "$")
        if isinstance(final_doc, list) and final_doc:
            final_doc = final_doc[0]
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}

    # Normalize path
    if p_raw.startswith("$."):
        p = p_raw[2:]
    elif p_raw.startswith("$"):
        p = p_raw[1:]
    else:
        p = p_raw

    # Validate path syntax
    if "[" in p or "]" in p or p == "" or p.startswith(".") or p.endswith(".") or ".." in p:
        return {"success": False, "error": "Invalid path; use dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}

    redis_path = "$." + p

    # Server-side delete; JSON.DEL returns count (0 if nothing deleted)
    try:
        rc.json().delete(redis_key, redis_path)
    except redis.exceptions.ResponseError as e:
        # Treat structural issues as no-op for simplicity/compatibility
        return {"success": False, "error": f"Delete failed: {e}", "redis_key": redis_key, "doc_json": None}

    # Return final doc
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    if final_doc is None:
        # If key did not exist previously, make it consistent with "{}"
        final_doc = {}
        rc.json().set(redis_key, "$", final_doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}