import os
import json
import redis

def json_read(
    key: str,
    path: str,
    *,
    redis_url: str = "",
    require_exists: bool = True,
    pretty: bool = False
) -> dict:
    """
    Read a JSON value from a RedisJSON document at the given path.

    Supported paths: object-style keys only (e.g., $.a.b or $["a"]["b"]).
    Numeric array indices/selectors are NOT supported in this function.

    Args:
        key (str): Redis key where the JSON document is stored.
        path (str): JSONPath to read. `$` returns the whole document.
        redis_url (str): Redis connection URL. If empty, uses REDIS_URL env var or 'redis://redis:6379/0'.
        require_exists (bool): If True, error when the key or the path does not exist. If False, returns exists=False and value_json="null".
        pretty (bool): If True, pretty-print returned JSON string.

    Returns:
        dict: {
          "success": bool,
          "error": str | None,
          "exists": bool,           # whether the requested path existed
          "value_json": str | None  # JSON-encoded string of the value (or "null" when missing and require_exists=False)
        }
    """
    rc = redis.Redis.from_url(
        redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True
    )

    # 1) Read full document
    doc = rc.json().get(key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]

    if doc is None:
        if require_exists:
            return {"success": False, "error": f"Key '{key}' not found.", "exists": False, "value_json": None}
        # Treat as empty document
        if pretty:
            return {"success": True, "error": None, "exists": False, "value_json": "null"}
        else:
            return {"success": True, "error": None, "exists": False, "value_json": "null"}

    # 2) Parse object-style path into keys (supports $.a.b and $["a"]["b"])
    p = path.strip()
    if not p.startswith("$"):
        return {"success": False, "error": f"Path must start with $: {path}", "exists": False, "value_json": None}

    # Root path: return whole doc
    if p == "$":
        try:
            s = json.dumps(doc, indent=2 if pretty else None)
        except Exception as e:
            return {"success": False, "error": f"JSON encode error: {e}", "exists": True, "value_json": None}
        return {"success": True, "error": None, "exists": True, "value_json": s}

    keys = []
    i = 1
    L = len(p)
    while i < L:
        ch = p[i]
        if ch == ".":
            i += 1
            j = i
            while j < L and p[j] not in ".[":
                j += 1
            if j > i:
                keys.append(p[i:j])
            i = j
        elif ch == "[":
            i += 1
            if i < L and p[i] in "\"'":
                quote = p[i]; i += 1
                j = p.find(quote, i)
                if j == -1:
                    return {"success": False, "error": f"Bad path (unterminated quote): {path}", "exists": False, "value_json": None}
                keys.append(p[i:j])
                i = j + 1
                if i >= L or p[i] != "]":
                    return {"success": False, "error": f"Bad path (missing ]): {path}", "exists": False, "value_json": None}
                i += 1
            else:
                return {"success": False, "error": f"Array indices not supported in this function: {path}", "exists": False, "value_json": None}
        else:
            i += 1

    # 3) Traverse
    cur = doc
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            if require_exists:
                return {"success": False, "error": f"path not found: {path}", "exists": False, "value_json": None}
            return {"success": True, "error": None, "exists": False, "value_json": "null"}
        cur = cur[k]

    # 4) Return value as JSON string
    try:
        s = json.dumps(cur, indent=2 if pretty else None)
    except Exception as e:
        return {"success": False, "error": f"JSON encode error: {e}", "exists": True, "value_json": None}

    return {"success": True, "error": None, "exists": True, "value_json": s}
