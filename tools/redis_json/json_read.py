import os
import json
import redis

def json_read(
    key: str,
    path: str = "$",
    *,
    pretty: bool = False,
    redis_url: str = ""
) -> dict:
    """
    Read a JSON value from a RedisJSON document.

    Behavior:
      - Returns the value at `path` as a JSON string in `value_json`.
      - If the document exists but the dot-path does not, returns `"null"` (success=True).
      - If the Redis key does not exist, returns success=False with an error.
      - Pretty printing is opt-in via `pretty=True`.

    Path rules:
      - Accepts "$" (root), "$.a.b", or "a.b".
      - Dot-paths only; **no** bracket selectors (`$["a"]`) and **no** array indices.

    Args:
        key (str): Redis key of the JSON document.
        path (str): Target path to read. Use "$" for the whole document. Default "$".
        pretty (bool): If True, return indented JSON in `value_json`. Default False.
        redis_url (str): Optional Redis connection URL. If empty, uses the REDIS_URL env var or "redis://redis:6379/0".

    Returns:
        dict: {
            "success": bool,           # False only if the key is missing or parameters are invalid
            "error": str | None,       # Error message when success=False
            "key": str,                # The Redis key used
            "value_json": str | None   # JSON string of the value, or "null" if the path is absent
        }

    Examples:
        # Read the entire document
        json_read("doc:123", "$", pretty=True)

        # Read a nested field (returns "null" if absent)
        json_read("doc:123", "profile.name")

        # Dollar-prefixed dot-path also works
        json_read("doc:123", "$.steps.verify_identity.status")
    """
    rc = redis.Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    doc = rc.json().get(key, "$")
    if isinstance(doc, list) and doc:
        doc = doc[0]
    if doc is None:
        return {"success": False, "error": f"Key not found: {key}", "key": key, "value_json": None}

    p = path.strip()
    if p == "$" or p == "":
        return {"success": True, "error": None, "key": key, "value_json": json.dumps(doc, indent=2 if pretty else None)}
    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    if "[" in p or "]" in p:
        return {"success": False, "error": "Bracketed selectors are not supported in simple tools.", "key": key, "value_json": None}

    cur = doc
    if p != "":
        parts = p.split(".")
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                return {"success": True, "error": None, "key": key, "value_json": "null"}
            cur = cur[part]

    return {"success": True, "error": None, "key": key, "value_json": json.dumps(cur, indent=2 if pretty else None)}
