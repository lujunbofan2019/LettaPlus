import os
import json
import redis
import uuid

def json_create(
    key: str = "",
    initial_json: str = "{}",
    key_prefix: str = "doc:",
    overwrite: bool = False,
    redis_url: str = ""
) -> dict:
    """
    Create or reset a JSON document in Redis and return its key.

    Behavior:
      - If `key` is empty, a new key is generated as `key_prefix + uuid4().hex` (e.g., "doc:7fd2a0...").
      - Writes `initial_json` to the key as the root document.
      - If the key already exists and `overwrite=False`, returns an error without modifying the document.
      - The root document should be a JSON **object** for best compatibility with other tools.

    Args:
        key (str): Redis key for the JSON document. Use "" to auto-generate a key.
        initial_json (str): Root document to write, as a JSON string (e.g., "{}", '{"status":"pending"}'). Default "{}".
        key_prefix (str): Prefix used when auto-generating a key. Default "doc:".
        overwrite (bool): If True, replace an existing document at `key`. If False and the key exists, return an error.
        redis_url (str): Optional Redis connection URL. If empty, uses the REDIS_URL env var or "redis://redis:6379/0".

    Returns:
        dict: {
            "success": bool,          # True when the document is created/replaced
            "error": str | None,      # Error message when success=False
            "key": str,               # The actual Redis key used (auto-generated when input key="")
            "doc_json": str | None    # JSON string of the root document after creation
        }

    Examples:
        # Create with auto-generated key and empty object
        res = json_create("", "{}")
        # Use res["key"] for subsequent operations

        # Create with explicit key and initial payload
        json_create("doc:onboarding:001", '{"status":"pending","meta":{}}')

        # Reset an existing key
        json_create("doc:onboarding:001", "{}", overwrite=True)
    """
    try:
        doc = json.loads(initial_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"initial_json is not valid JSON: {e}", "key": key, "doc_json": None}

    actual_key = key if key else f"{key_prefix}{uuid.uuid4().hex}"
    rc = redis.Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    if rc.exists(actual_key) and not overwrite:
        return {"success": False, "error": f"Key already exists: {actual_key}", "key": actual_key, "doc_json": None}

    rc.json().set(actual_key, "$", doc)
    return {"success": True, "error": None, "key": actual_key, "doc_json": json.dumps(doc)}
