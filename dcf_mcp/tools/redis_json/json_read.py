from typing import Any, Dict
import os
import json
import redis

def json_read(
    redis_key: str,
    path: str = "$",
    pretty: bool = False
) -> Dict[str, Any]:
    """
    Read a JSON value from a RedisJSON document.

    Returns the value at `path` as a JSON string in `value_json`. If the document exists but the dot-path does not,
    returns `"null"` (success=True). If the Redis key does not exist, returns success=False with an error. Pretty
    printing is opt-in via `pretty=True`.

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Target path to read. "$", "$.a.b", or "a.b" only, no bracket selectors, no array indices. Defaults to "$".
        pretty (bool): If True, return indented JSON in `value_json`. Defaults to False.

    Returns:
        dict: A dictionary with the following keys:
            - success (bool): False only if the Redis key is missing or parameters are invalid.
            - error (str): Error message when success=False.
            - redis_key (str | None): The Redis key used.
            - value_json (str | None): JSON string of the value, or "null" if the path is absent.
        }
    """
    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # Normalize and validate path
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        # Root read
        doc = rc.json().get(redis_key, "$")
        if isinstance(doc, list) and doc:
            doc = doc[0]
        if doc is None:
            # Distinguish missing key vs. empty doc
            if not rc.exists(redis_key):
                return {"success": False, "error": f"Key not found: {redis_key}", "redis_key": redis_key, "value_json": None}
            # If key exists but root is somehow nil, normalize to {}
            doc = {}
        return {
            "success": True,
            "error": None,
            "redis_key": redis_key,
            "value_json": json.dumps(doc, indent=2 if pretty else None),
        }

    if p_raw.startswith("$."):
        p = p_raw[2:]
    elif p_raw.startswith("$"):
        p = p_raw[1:]
    else:
        p = p_raw

    # Simple dot-path validation (no brackets/indices/wildcards)
    if "[" in p or "]" in p or p == "" or p.startswith(".") or p.endswith(".") or ".." in p:
        return {"success": False, "error": "Invalid path; use '$' or dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "value_json": None}

    redis_path = "$." + p

    # Server-side subpath read
    try:
        res = rc.json().get(redis_key, redis_path)
    except redis.exceptions.ResponseError:
        # Invalid/absent path or missing key; disambiguate
        if not rc.exists(redis_key):
            return {"success": False, "error": f"Key not found: {redis_key}", "redis_key": redis_key, "value_json": None}
        # Treat as missing path
        return {"success": True, "error": None, "redis_key": redis_key, "value_json": "null"}
    except Exception as e:
        return {"success": False, "error": f"Read error: {e}", "redis_key": redis_key, "value_json": None}

    # RedisJSON returns a list for JSONPath; unwrap single match
    if isinstance(res, list):
        res = res[0] if res else None

    if res is None:
        # Path absent — success with "null" if key exists, else error
        if not rc.exists(redis_key):
            return {"success": False, "error": f"Key not found: {redis_key}", "redis_key": redis_key, "value_json": None}
        return {"success": True, "error": None, "redis_key": redis_key, "value_json": "null"}

    return {
        "success": True,
        "error": None,
        "redis_key": redis_key,
        "value_json": json.dumps(res, indent=2 if pretty else None),
    }
