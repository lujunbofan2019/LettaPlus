import os
import json
import redis
import uuid

def json_create(
    redis_key: str = "",
    initial_json: str = "{}",
    key_prefix: str = "doc:",
    overwrite: bool = False
) -> dict:
    """
    Create or reset a JSON document in Redis and return its key.

    If `redis_key` is empty, a new key is generated at random. Writes `initial_json` to the key as the root document.
    If the redis_key already exists and `overwrite=False`, returns an error without modifying the document.

    Args:
        redis_key (str): Redis key for the JSON document. Defaults to "".
        initial_json (str): Root document to write, as a JSON string. Defaults to "{}".
        key_prefix (str): Prefix used when auto-generating a key. Defaults to "doc:"
        overwrite (bool): If True, replace an existing document at redis_key. Defaults to False.

    Returns:
        dict: A dictionary with the following keys:
            - success (bool): Whether the document is created/replaced successfully.
            - error (str): Error message when success=False.
            - redis_key (str): The actual Redis key used.
            - doc_json (str): JSON string of the root document after creation.
        }
    """
    try:
        doc = json.loads(initial_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"initial_json is not valid JSON: {e}", "redis_key": redis_key, "doc_json": None}

    actual_key = redis_key if redis_key else f"{key_prefix}{uuid.uuid4().hex}"
    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    if rc.exists(actual_key) and not overwrite:
        return {"success": False, "error": f"Key already exists: {actual_key}", "redis_key": actual_key, "doc_json": None}

    rc.json().set(actual_key, "$", doc)
    return {"success": True, "error": None, "redis_key": actual_key, "doc_json": json.dumps(doc)}
