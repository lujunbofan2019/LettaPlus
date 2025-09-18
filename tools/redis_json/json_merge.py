import os
import json
import redis

def json_merge(
    redis_key: str,
    path: str,
    patch_json: str
) -> dict:
    """
    Deep-merge an object into a path using RFC-7386 semantics.

    If both target and patch values at a Redis key are objects, they merge recursively. If a patch value is `null`,
    that key is **deleted** from the target. Otherwise, the patch value **overwrites** the target. Creates the target
    object if it is missing.

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Path to the object to merge into. "$", "$.a.b", or "a.b" only, no bracket selectors, no array indices.
        patch_json (str): JSON object to merge.

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    try:
        patch = json.loads(patch_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"patch_json invalid: {e}", "redis_key": redis_key, "doc_json": None}
    if not isinstance(patch, dict):
        return {"success": False, "error": "patch_json must be an object.", "redis_key": redis_key, "doc_json": None}

    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(redis_key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        doc = {}

    p = path.strip()
    if p == "$" or p == "":
        if not isinstance(doc, dict):
            return {"success": False, "error": "Root is not an object.", "redis_key": redis_key, "doc_json": None}
        target = doc
    else:
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
        leaf = parts[-1]
        if leaf not in cur or not isinstance(cur[leaf], dict):
            cur[leaf] = {}
        target = cur[leaf]

    stack = [(target, patch)]
    while stack:
        dst, src = stack.pop()
        for k, v in src.items():
            if v is None:
                if k in dst:
                    del dst[k]
            elif isinstance(v, dict) and isinstance(dst.get(k), dict):
                stack.append((dst[k], v))
            else:
                dst[k] = v

    rc.json().set(redis_key, "$", doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(doc)}
