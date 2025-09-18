import os
import redis

def json_increment(
    redis_key: str,
    path: str,
    delta: float
) -> dict:
    """
    Increment a numeric field by `delta`.

    Initializes a missing field to 0, then adds `delta`. Errors if the existing value is not numeric.
    Result is stored as int if it is exactly integral; otherwise float. Incrementing at root "$" is not supported.

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Path to a numeric field. "$.a.b" or "a.b" only, no bracket selectors, no indices.
        delta (float): Amount to add, may be negative.

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    # --- 1) Normalize and validate path ---
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        return {"success": False, "error": "Increment at `$` is not supported.", "redis_key": redis_key, "doc_json": None}

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

    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # --- 2) Try server-side NUMINCRBY first ---
    try:
        rc.json().numincrby(redis_key, redis_path, float(delta))
    except redis.exceptions.ResponseError:
        # --- 3) Fallback: fix structure or initialize when missing ---
        # Load or initialize the root document
        doc = rc.json().get(redis_key, "$")
        if isinstance(doc, list) and doc:
            doc = doc[0]
        if doc is None:
            doc = {}

        # Build parent chain as objects; coerce missing/non-object parents to {}
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
            # Initialize to 0 then persist, so NUMINCRBY can run atomically afterwards
            cur[leaf] = 0
            try:
                rc.json().set(redis_key, "$", doc)
            except Exception as e:
                return {"success": False, "error": f"Failed to initialize numeric field: {e}", "redis_key": redis_key, "doc_json": None}
        else:
            # If leaf exists, it must be numeric
            if not isinstance(cur[leaf], (int, float)):
                return {"success": False, "error": "Target is not numeric.", "redis_key": redis_key, "doc_json": None}
            # No need to persist; try NUMINCRBY again

        # Re-attempt server-side atomic increment
        try:
            rc.json().numincrby(redis_key, redis_path, float(delta))
        except redis.exceptions.ResponseError as e:
            return {"success": False, "error": f"Increment failed: {e}", "redis_key": redis_key, "doc_json": None}
        except Exception as e:
            return {"success": False, "error": f"Increment error: {e}", "redis_key": redis_key, "doc_json": None}
    except Exception as e:
        return {"success": False, "error": f"Increment error: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 4) Return final doc ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    # RedisJSON stores numbers as float or int; no need to coerce here.
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}