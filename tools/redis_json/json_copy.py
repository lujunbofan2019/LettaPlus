import os
import json
import redis

def json_copy(
    key: str,
    from_path: str,
    to_path: str,
    overwrite: bool = True,
    redis_url: str = ""
) -> dict:
    """
    Copy a subtree from `from_path` to `to_path`.

    Behavior:
      - Creates any missing destination parents.
      - Overwrites destination by default (`overwrite=True`).
      - Source remains unchanged.
      - Copying the root "$" or copying *into* "$" is not supported.

    Path rules:
      - "$.a.b" or "a.b" only for both `from_path` and `to_path`.

    Args:
        key (str): Redis key of the JSON document.
        from_path (str): Source subtree path (not "$").
        to_path (str): Destination subtree path (not "$").
        overwrite (bool): Overwrite destination if it already exists. Default True.
        redis_url (str): Optional Redis connection string.

    Returns:
        dict: { "success": bool, "error": str|None, "key": str, "doc_json": str|None }

    Examples:
        json_copy("k1", "steps.verify_identity", "snapshots.verify_identity_latest", overwrite=True)
    """
    rc = redis.Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    fp = from_path.strip(); tp = to_path.strip()
    if fp == "$" or tp == "$":
        return {"success": False, "error": "Copying root is not supported.", "key": key, "doc_json": None}

    if fp.startswith("$."): fp = fp[2:]
    elif fp.startswith("$"): fp = fp[1:]
    if tp.startswith("$."): tp = tp[2:]
    elif tp.startswith("$"): tp = tp[1:]
    if any(c in fp+tp for c in "[]"):
        return {"success": False, "error": "Bracketed selectors are not supported.", "key": key, "doc_json": None}

    # get source
    cur = doc
    fparts = fp.split(".") if fp else []
    for part in fparts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return {"success": False, "error": "from_path not found.", "key": key, "doc_json": None}
        cur = cur[part]
    if not isinstance(cur, dict) or fparts[-1] not in cur:
        return {"success": False, "error": "from_path not found.", "key": key, "doc_json": None}
    copied_value = cur[fparts[-1]]

    # set destination
    cur = doc
    tparts = tp.split(".") if tp else []
    for part in tparts[:-1]:
        if not isinstance(cur, dict):
            return {"success": False, "error": "Destination parent is not an object.", "key": key, "doc_json": None}
        if part not in cur or not isinstance(cur[part], (dict, list)):
            cur[part] = {}
        cur = cur[part]
    if not isinstance(cur, dict):
        return {"success": False, "error": "Destination parent is not an object.", "key": key, "doc_json": None}
    dest_leaf = tparts[-1]
    if (dest_leaf in cur) and not overwrite:
        return {"success": False, "error": "Destination exists and overwrite=False.", "key": key, "doc_json": None}
    cur[dest_leaf] = json.loads(json.dumps(copied_value))  # deep copy

    rc.json().set(key, "$", doc)
    return {"success": True, "error": None, "key": key, "doc_json": json.dumps(doc)}
