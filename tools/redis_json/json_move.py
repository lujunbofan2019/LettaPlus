import os
import json
import redis

def json_move(
    redis_key: str,
    from_path: str,
    to_path: str,
    overwrite: bool = True
) -> dict:
    """
    Move a subtree from `from_path` to `to_path`.

    Creates any missing destination parents. Overwrites destination by default (`overwrite=True`). Source is removed after the move.
    Moving the root "$" or moving into "$" is not supported. No cycle checks beyond simple path comparison (do not move into your own descendant).

    Args:
        redis_key (str): Redis key of the JSON document.
        from_path (str): Source subtree path. "$.a.b", or "a.b" only, no bracket selectors, no array indices.
        to_path (str): Destination subtree path. "$.a.b", or "a.b" only, no bracket selectors, no array indices.
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

    # Disallow moving into same path or into own descendant
    if tp == fp or tp.startswith(fp + "."):
        return {"success": False, "error": "Cannot move into the same path or into its own descendant.", "redis_key": redis_key, "doc_json": None}

    from_jsonpath = "$." + fp
    to_jsonpath   = "$." + tp

    # --- Fetch source subtree (no-op if absent) ---
    try:
        src_val = rc.json().get(redis_key, from_jsonpath)
    except redis.exceptions.ResponseError:
        src_val = None
    if isinstance(src_val, list):
        src_val = src_val[0] if src_val else None
    if src_val is None:
        # Nothing to move
        final_doc = rc.json().get(redis_key, "$")
        if isinstance(final_doc, list) and final_doc:
            final_doc = final_doc[0]
        if final_doc is None:
            final_doc = {}
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}

    # --- Honor overwrite=False if destination exists ---
    try:
        dest_probe = rc.json().get(redis_key, to_jsonpath)
    except redis.exceptions.ResponseError:
        dest_probe = None
    if isinstance(dest_probe, list):
        dest_probe = dest_probe[0] if dest_probe else None
    if (dest_probe is not None) and not overwrite:
        return {"success": False, "error": "Destination exists and overwrite=False.", "redis_key": redis_key, "doc_json": None}

    # Prepare payload (deep copy via JSON round-trip to ensure pure JSON types)
    payload = json.loads(json.dumps(src_val))

    # --- Try server-side SET at destination ---
    try:
        rc.json().set(redis_key, to_jsonpath, payload)
        set_done = True
    except redis.exceptions.ResponseError:
        set_done = False

    if not set_done:
        # Fallback: create destination parents client-side and write once
        root = rc.json().get(redis_key, "$")
        if isinstance(root, list) and root:
            root = root[0]
        if root is None:
            root = {}

        # Build destination parents as objects
        cur = root
        tparts = tp.split(".")
        for seg in tparts[:-1]:
            if not isinstance(cur, dict):
                return {"success": False, "error": f"Destination parent segment '{seg}' is not an object.", "redis_key": redis_key, "doc_json": None}
            if seg not in cur:
                cur[seg] = {}
            elif not isinstance(cur[seg], dict):
                return {"success": False, "error": f"Destination parent segment '{seg}' exists but is not an object.", "redis_key": redis_key, "doc_json": None}
            cur = cur[seg]
        dest_leaf = tparts[-1]
        if (dest_leaf in cur) and not overwrite:
            return {"success": False, "error": "Destination exists and overwrite=False.", "redis_key": redis_key, "doc_json": None}
        cur[dest_leaf] = payload

        # Remove source in the same client-side doc
        cur = root
        fparts = fp.split(".")
        for seg in fparts[:-1]:
            if not isinstance(cur, dict) or seg not in cur:
                # Source vanished; just persist destination
                rc.json().set(redis_key, "$", root)
                final_doc = rc.json().get(redis_key, "$")
                if isinstance(final_doc, list) and final_doc:
                    final_doc = final_doc[0]
                return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}
            cur = cur[seg]
        if isinstance(cur, dict) and fparts[-1] in cur:
            del cur[fparts[-1]]

        # Persist whole doc once
        rc.json().set(redis_key, "$", root)

    else:
        # Server-side delete source
        try:
            rc.json().delete(redis_key, from_jsonpath)
        except redis.exceptions.ResponseError as e:
            return {"success": False, "error": f"Delete failed after set: {e}", "redis_key": redis_key, "doc_json": None}

    # --- Return final document ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    if final_doc is None:
        final_doc = {}
        rc.json().set(redis_key, "$", final_doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}