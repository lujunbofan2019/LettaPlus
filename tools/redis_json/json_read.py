import os
import json
import redis

def json_read(
    redis_key: str,
    path: str = "$",
    pretty: bool = False
) -> dict:
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
    doc = rc.json().get(redis_key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        return {"success": False, "error": f"Key not found: {redis_key}", "redis_key": redis_key, "value_json": None}

    p = path.strip()
    if p == "$" or p == "":
        return {"success": True, "error": None, "redis_key": redis_key, "value_json": json.dumps(doc, indent=2 if pretty else None)}
    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    if "[" in p or "]" in p:
        return {"success": False, "error": "Bracketed selectors are not supported in simple tools.", "redis_key": redis_key, "value_json": None}

    cur = doc
    if p != "":
        parts = p.split(".")
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                return {"success": True, "error": None, "redis_key": redis_key, "value_json": "null"}
            cur = cur[part]

    return {"success": True, "error": None, "redis_key": redis_key, "value_json": json.dumps(cur, indent=2 if pretty else None)}
