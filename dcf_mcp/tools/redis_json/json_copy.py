from typing import Any, Dict
import os
import json
import redis

def json_copy(
    redis_key: str,
    from_path: str,
    to_path: str,
    overwrite: bool = True
) -> Dict[str, Any]:
    """
    Copy a subtree from `from_path` to `to_path`.

    Creates any missing destination parents. Overwrites destination by default (`overwrite=True`). Source remains unchanged.
    Copying the root "$" or copying *into* "$" is not supported.

    Args:
        redis_key (str): Redis key of the JSON document.
        from_path (str): Source subtree path (not "$"). "$.a.b" or "a.b" only, no bracket selectors, no indices.
        to_path (str): Destination subtree path (not "$"). "$.a.b" or "a.b" only, no bracket selectors, no indices.
        overwrite (bool): Overwrite destination if it already exists. Defaults to True.

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # --- Normalize & validate from_path ---
    fp_raw = (from_path or "").strip()
    if fp_raw in ("", "$"):
        return {"success": False, "error": "from_path cannot be '$' or empty.", "redis_key": redis_key, "doc_json": None}
    if fp_raw.startswith("$."):
        fp = fp_raw[2:]
    elif fp_raw.startswith("$"):
        fp = fp_raw[1:]
    else:
        fp = fp_raw
    if "[" in fp or "]" in fp or fp == "" or fp.startswith(".") or fp.endswith(".") or ".." in fp:
        return {"success": False, "error": "Invalid from_path; use dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}

    # --- Normalize & validate to_path ---
    tp_raw = (to_path or "").strip()
    if tp_raw in ("", "$"):
        return {"success": False, "error": "to_path cannot be '$' or empty.", "redis_key": redis_key, "doc_json": None}
    if tp_raw.startswith("$."):
        tp = tp_raw[2:]
    elif tp_raw.startswith("$"):
        tp = tp_raw[1:]
    else:
        tp = tp_raw
    if "[" in tp or "]" in tp or tp == "" or tp.startswith(".") or tp.endswith(".") or ".." in tp:
        return {"success": False, "error": "Invalid to_path; use dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}

    # Early no-op if identical normalized paths
    if fp == tp:
        final_doc = rc.json().get(redis_key, "$")
        if isinstance(final_doc, list) and final_doc:
            final_doc = final_doc[0]
        if final_doc is None:
            final_doc = {}
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}

    from_jsonpath = "$." + fp
    to_jsonpath   = "$." + tp

    # --- Fetch source subtree ---
    try:
        src = rc.json().get(redis_key, from_jsonpath)
    except redis.exceptions.ResponseError:
        src = None
    if isinstance(src, list):
        src = src[0] if src else None
    if src is None:
        return {"success": False, "error": "from_path not found.", "redis_key": redis_key, "doc_json": None}

    # --- Honor overwrite=False if destination exists ---
    try:
        dest_probe = rc.json().get(redis_key, to_jsonpath)
    except redis.exceptions.ResponseError:
        dest_probe = None
    if isinstance(dest_probe, list):
        dest_probe = dest_probe[0] if dest_probe else None
    if (dest_probe is not None) and not overwrite:
        return {"success": False, "error": "Destination exists and overwrite=False.", "redis_key": redis_key, "doc_json": None}

    # Prepare payload as pure JSON
    payload = json.loads(json.dumps(src))

    # --- Try server-side subpath set first ---
    try:
        rc.json().set(redis_key, to_jsonpath, payload)
        set_done = True
    except redis.exceptions.ResponseError:
        set_done = False

    if not set_done:
        # Minimal client-side fallback: create destination parents, then persist once
        root = rc.json().get(redis_key, "$")
        if isinstance(root, list) and root:
            root = root[0]
        if root is None:
            root = {}

        cur = root
        parts = tp.split(".")
        for seg in parts[:-1]:
            if not isinstance(cur, dict):
                return {"success": False, "error": f"Destination parent segment '{seg}' is not an object.", "redis_key": redis_key, "doc_json": None}
            if seg not in cur:
                cur[seg] = {}
            elif not isinstance(cur[seg], dict):
                return {"success": False, "error": f"Destination parent segment '{seg}' exists but is not an object.", "redis_key": redis_key, "doc_json": None}
            cur = cur[seg]
        dest_leaf = parts[-1]
        if (dest_leaf in cur) and not overwrite:
            return {"success": False, "error": "Destination exists and overwrite=False.", "redis_key": redis_key, "doc_json": None}
        cur[dest_leaf] = payload

        rc.json().set(redis_key, "$", root)

    # --- Return final doc ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    if final_doc is None:
        final_doc = {}
        rc.json().set(redis_key, "$", final_doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}
