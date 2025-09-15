import os
import json
import redis
from datetime import datetime, timezone
from jsonschema import Draft202012Validator, ValidationError
from redis.exceptions import WatchError

def json_append(
    key: str,
    path: str,
    value_json: str,
    *,
    redis_url: str = "",
    create_if_missing: bool = True,
    require_exists: bool = False,
    validation_scope: str = "subtree",    # "none" | "subtree" | "document"
    subtree_schema_json: str = "",        # JSON string; empty = not provided
    global_schema_json: str = "",         # JSON string; empty = not provided
    audit_log_path: str = "$.logs",       # "" to disable auditing
    max_retries: int = 6,
    return_document: bool = True,
) -> dict:
    """
    Append a JSON value to an array at `path` inside a RedisJSON document, atomically.
    If the array does not exist and `require_exists` is False, it will be created as [].

    Supported paths: object-style keys only (e.g., $.a.b or $["a"]["b"]).
    Numeric array indices/selectors are NOT supported in this function.

    Args:
        key (str): Redis key where the JSON document is stored.
        path (str): JSONPath to the target array (e.g., $.items).
        value_json (str): Element to append, encoded as JSON (e.g., '"x"', '123', 'true', 'null', '{}', '[]').
        redis_url (str): Redis connection URL. If empty, uses REDIS_URL env var or 'redis://redis:6379/0'.
        create_if_missing (bool): If True and the key is missing, initializes it to {}. Default True.
        require_exists (bool): If True, error if `path` is missing. Default False.
        validation_scope (str): "none" | "subtree" | "document". Default "subtree".
        subtree_schema_json (str): JSON Schema (as JSON string) to validate the array after append when validation_scope="subtree".
        global_schema_json (str): JSON Schema (as JSON string) to validate the whole document when validation_scope="document".
        audit_log_path (str): If non-empty and the referenced path points to a list, append {"ts","op","path"}.
        max_retries (int): Max retries under optimistic concurrency.
        return_document (bool): If True, include final JSON document under "doc".

    Returns:
        dict: {"success": bool, "error": str|None, "doc": dict|None}
    """
    # Parse inputs
    try:
        value = json.loads(value_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"value_json is not valid JSON: {e}", "doc": None}

    subtree_schema = None
    if subtree_schema_json:
        try:
            subtree_schema = json.loads(subtree_schema_json)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"subtree_schema_json is not valid JSON: {e}", "doc": None}

    global_schema = None
    if global_schema_json:
        try:
            global_schema = json.loads(global_schema_json)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"global_schema_json is not valid JSON: {e}", "doc": None}

    rc = redis.Redis.from_url(
        redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True
    )

    if create_if_missing and not rc.exists(key):
        rc.json().set(key, "$", {})

    retries = 0
    while True:
        pipe = rc.pipeline()
        try:
            pipe.watch(key)

            # 1) Read full document snapshot
            doc = pipe.json().get(key, "$")
            if isinstance(doc, list) and doc:
                doc = doc[0]
            if doc is None:
                if not create_if_missing:
                    return {"success": False, "error": f"Key '{key}' not found.", "doc": None}
                doc = {}

            # 2) Parse object-style path to keys (supports $.a.b and $["a"]["b"])
            p = path.strip()
            if not p.startswith("$"):
                return {"success": False, "error": f"Path must start with $: {path}", "doc": None}
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
                            return {"success": False, "error": f"Bad path (unterminated quote): {path}", "doc": None}
                        keys.append(p[i:j])
                        i = j + 1
                        if i >= L or p[i] != "]":
                            return {"success": False, "error": f"Bad path (missing ]): {path}", "doc": None}
                        i += 1
                    else:
                        return {"success": False, "error": f"Array indices not supported in this function: {path}", "doc": None}
                else:
                    i += 1

            # 3) Navigate to array (create if allowed)
            if len(keys) == 0:
                # Root must be an array to append at `$`
                if not isinstance(doc, list):
                    if require_exists:
                        return {"success": False, "error": "Root is not an array.", "doc": None}
                    # Convert whole doc to array if allowed? Safer to forbid:
                    return {"success": False, "error": "Appending at `$` requires the document to be an array.", "doc": None}
                target_arr = doc
            else:
                cur = doc
                for k in keys[:-1]:
                    if not isinstance(cur, dict):
                        return {"success": False, "error": f"Cannot descend into non-object at key '{k}'", "doc": None}
                    if k not in cur or not isinstance(cur[k], (dict, list)):
                        cur[k] = {}
                    cur = cur[k]
                leaf = keys[-1]
                exists = isinstance(cur, dict) and leaf in cur
                if not exists:
                    if require_exists:
                        return {"success": False, "error": f"path not found: {path}", "doc": None}
                    cur[leaf] = []
                target_arr = cur[leaf]
                if not isinstance(target_arr, list):
                    return {"success": False, "error": f"append target at {path} is not an array", "doc": None}

            # 4) Append value
            target_arr.append(value)

            # 5) Validation
            if validation_scope == "subtree" and subtree_schema is not None:
                Draft202012Validator(subtree_schema).validate(target_arr)
            if validation_scope == "document" and global_schema is not None:
                Draft202012Validator(global_schema).validate(doc)

            # 6) Optional audit append
            if audit_log_path:
                ap = audit_log_path.strip()
                if ap.startswith("$"):
                    ak = []
                    i2 = 1
                    L2 = len(ap)
                    bad_audit = False
                    while i2 < L2:
                        ch2 = ap[i2]
                        if ch2 == ".":
                            i2 += 1
                            j2 = i2
                            while j2 < L2 and ap[j2] not in ".[":
                                j2 += 1
                            if j2 > i2: ak.append(ap[i2:j2])
                            i2 = j2
                        elif ch2 == "[":
                            i2 += 1
                            if i2 < L2 and ap[i2] in "\"'":
                                q = ap[i2]; i2 += 1
                                j2 = ap.find(q, i2)
                                if j2 == -1 or j2 + 1 >= L2 or ap[j2+1] != "]":
                                    bad_audit = True; break
                                ak.append(ap[i2:j2]); i2 = j2 + 2
                            else:
                                bad_audit = True; break
                        else:
                            i2 += 1
                    if not bad_audit:
                        cur2 = doc
                        ok = True
                        for k in ak:
                            if not isinstance(cur2, dict) or k not in cur2:
                                ok = False; break
                            cur2 = cur2[k]
                        if ok and isinstance(cur2, list):
                            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                            cur2.append({"ts": ts, "op": "append", "path": path})

            # 7) Commit
            pipe.multi()
            pipe.json().set(key, "$", doc)
            pipe.execute()

            return {"success": True, "error": None, "doc": doc if return_document else None}

        except WatchError:
            retries += 1
            if retries >= max_retries:
                return {"success": False, "error": "Write contention: too many concurrent updates.", "doc": None}
            continue
        except ValidationError as ve:
            return {"success": False, "error": f"Schema validation failed: {ve.message}", "doc": None}
        except Exception as e:
            return {"success": False, "error": f"{e.__class__.__name__}: {e}", "doc": None}
        finally:
            try:
                pipe.reset()
            except Exception:
                pass
