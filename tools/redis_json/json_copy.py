import os
import json
import redis
from datetime import datetime, timezone
from jsonschema import Draft202012Validator, ValidationError
from redis.exceptions import WatchError

def json_copy(
    key: str,
    from_path: str,
    to_path: str,
    *,
    redis_url: str = "",
    create_if_missing: bool = True,
    require_src_exists: bool = True,
    require_dest_parent_exists: bool = False,
    overwrite_if_exists: bool = False,
    validation_scope: str = "subtree",    # "none" | "subtree" | "document"
    subtree_schema_json: str = "",        # JSON string; empty = not provided
    global_schema_json: str = "",         # JSON string; empty = not provided
    audit_log_path: str = "$.logs",       # "" to disable auditing
    max_retries: int = 6,
    return_document: bool = True,
) -> dict:
    """
    Copy a JSON subtree from `from_path` to `to_path` inside a RedisJSON document, atomically.
    (Unlike move, the source remains intact.)

    Constraints:
      - Only object-style paths supported (e.g., $.a.b or $["a"]["b"]).
      - Copying the root `$` or copying into `$` is not supported (to avoid replacing the whole doc).

    Args:
        key (str): Redis key where the JSON document is stored.
        from_path (str): Source JSONPath to copy from (e.g., $.a.b).
        to_path (str): Destination JSONPath to copy to (e.g., $.x.y).
        redis_url (str): Redis connection URL. If empty, uses REDIS_URL env var or 'redis://redis:6379/0'.
        create_if_missing (bool): If True and the key is missing, initializes it to {}. Default True.
        require_src_exists (bool): If True, error if `from_path` does not exist. Default True.
        require_dest_parent_exists (bool): If True, error if destination parent chain is missing.
            If False, parent objects will be created as needed. Default False.
        overwrite_if_exists (bool): If False and `to_path` already exists, error. If True, overwrite. Default False.
        validation_scope (str): "none" | "subtree" | "document". Default "subtree".
            - For "subtree", validates the copied subtree at its new location against `subtree_schema_json` (if provided).
        subtree_schema_json (str): JSON Schema (as JSON string) for the copied subtree at `to_path`.
        global_schema_json (str): JSON Schema (as JSON string) to validate the whole document.
        audit_log_path (str): If non-empty and the referenced path points to a list, append {"ts","op","from","to"}.
        max_retries (int): Max retries under optimistic concurrency.
        return_document (bool): If True, include final JSON document under "doc".

    Returns:
        dict: {"success": bool, "error": str|None, "doc": dict|None}
    """
    # Parse schemas (if provided)
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

    # Basic path checks
    fp = from_path.strip()
    tp = to_path.strip()
    if not fp.startswith("$") or not tp.startswith("$"):
        return {"success": False, "error": "Both from_path and to_path must start with '$'.", "doc": None}
    if fp == "$" or tp == "$":
        return {"success": False, "error": "Copying the root or into the root '$' is not supported.", "doc": None}

    # Inline parse of object-style paths (supports $.a.b and $["a"]["b"])
    from_keys = []
    i = 1
    L = len(fp)
    while i < L:
        ch = fp[i]
        if ch == ".":
            i += 1
            j = i
            while j < L and fp[j] not in ".[":
                j += 1
            if j > i:
                from_keys.append(fp[i:j])
            i = j
        elif ch == "[":
            i += 1
            if i < L and fp[i] in "\"'":
                quote = fp[i]; i += 1
                j = fp.find(quote, i)
                if j == -1:
                    return {"success": False, "error": f"Bad path (unterminated quote): {from_path}", "doc": None}
                from_keys.append(fp[i:j])
                i = j + 1
                if i >= L or fp[i] != "]":
                    return {"success": False, "error": f"Bad path (missing ]): {from_path}", "doc": None}
                i += 1
            else:
                return {"success": False, "error": f"Array indices not supported in this function: {from_path}", "doc": None}
        else:
            i += 1

    to_keys = []
    i2 = 1
    L2 = len(tp)
    while i2 < L2:
        ch2 = tp[i2]
        if ch2 == ".":
            i2 += 1
            j2 = i2
            while j2 < L2 and tp[j2] not in ".[":
                j2 += 1
            if j2 > i2:
                to_keys.append(tp[i2:j2])
            i2 = j2
        elif ch2 == "[":
            i2 += 1
            if i2 < L2 and tp[i2] in "\"'":
                quote2 = tp[i2]; i2 += 1
                j2 = tp.find(quote2, i2)
                if j2 == -1:
                    return {"success": False, "error": f"Bad path (unterminated quote): {to_path}", "doc": None}
                to_keys.append(tp[i2:j2])
                i2 = j2 + 1
                if i2 >= L2 or tp[i2] != "]":
                    return {"success": False, "error": f"Bad path (missing ]): {to_path}", "doc": None}
                i2 += 1
            else:
                return {"success": False, "error": f"Array indices not supported in this function: {to_path}", "doc": None}
        else:
            i2 += 1

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

            # 1) Snapshot
            doc = pipe.json().get(key, "$")
            if isinstance(doc, list) and doc:
                doc = doc[0]
            if doc is None:
                if not create_if_missing:
                    return {"success": False, "error": f"Key '{key}' not found.", "doc": None}
                doc = {}

            # 2) Locate source value
            cur_src = doc
            for k in from_keys[:-1]:
                if not isinstance(cur_src, dict) or k not in cur_src:
                    if require_src_exists:
                        return {"success": False, "error": f"from_path not found: {from_path}", "doc": None}
                    # No-op if source missing
                    return {"success": True, "error": None, "doc": doc if return_document else None}
                cur_src = cur_src[k]
            if not isinstance(cur_src, dict):
                return {"success": False, "error": f"Source parent is not an object at {from_path}", "doc": None}
            src_leaf = from_keys[-1] if len(from_keys) > 0 else None
            if src_leaf is None or src_leaf not in cur_src:
                if require_src_exists:
                    return {"success": False, "error": f"from_path not found: {from_path}", "doc": None}
                # No-op
                return {"success": True, "error": None, "doc": doc if return_document else None}
            copied_value = cur_src[src_leaf]

            # 3) Locate/create destination parent
            cur_dst = doc
            for k in to_keys[:-1]:
                if not isinstance(cur_dst, dict):
                    return {"success": False, "error": f"Destination parent is not an object at {to_path}", "doc": None}
                if k not in cur_dst or not isinstance(cur_dst[k], (dict, list)):
                    if require_dest_parent_exists:
                        return {"success": False, "error": f"Destination parent path not found: {to_path}", "doc": None}
                    cur_dst[k] = {}
                cur_dst = cur_dst[k]
            if not isinstance(cur_dst, dict):
                return {"success": False, "error": f"Destination parent is not an object at {to_path}", "doc": None}
            dest_leaf = to_keys[-1] if len(to_keys) > 0 else None
            if dest_leaf is None:
                return {"success": False, "error": "Destination path must point to a field, not `$`.", "doc": None}

            # 4) Overwrite protection
            if dest_leaf in cur_dst and not overwrite_if_exists:
                return {"success": False, "error": f"Destination already exists at {to_path}", "doc": None}

            # 5) Perform copy (shallow copy is fine for JSON because we'll write whole doc)
            # If deep copy is desired to avoid aliasing in RAM, json round-trip is safe:
            try:
                copied_json = json.loads(json.dumps(copied_value))
            except Exception:
                # Fallback (shouldn't happen for JSON-serializable values)
                copied_json = copied_value
            cur_dst[dest_leaf] = copied_json

            # 6) Validation
            if validation_scope == "subtree" and subtree_schema is not None:
                Draft202012Validator(subtree_schema).validate(cur_dst[dest_leaf])
            if validation_scope == "document" and global_schema is not None:
                Draft202012Validator(global_schema).validate(doc)

            # 7) Optional audit append
            if audit_log_path:
                ap = audit_log_path.strip()
                if ap.startswith("$"):
                    ak = []
                    i3 = 1
                    L3 = len(ap)
                    bad_audit = False
                    while i3 < L3:
                        ch3 = ap[i3]
                        if ch3 == ".":
                            i3 += 1
                            j3 = i3
                            while j3 < L3 and ap[j3] not in ".[":
                                j3 += 1
                            if j3 > i3:
                                ak.append(ap[i3:j3])
                            i3 = j3
                        elif ch3 == "[":
                            i3 += 1
                            if i3 < L3 and ap[i3] in "\"'":
                                q3 = ap[i3]; i3 += 1
                                j3 = ap.find(q3, i3)
                                if j3 == -1 or j3 + 1 >= L3 or ap[j3+1] != "]":
                                    bad_audit = True; break
                                ak.append(ap[i3:j3]); i3 = j3 + 2
                            else:
                                bad_audit = True; break
                        else:
                            i3 += 1
                    if not bad_audit:
                        cur_a = doc
                        ok = True
                        for k in ak:
                            if not isinstance(cur_a, dict) or k not in cur_a:
                                ok = False; break
                            cur_a = cur_a[k]
                        if ok and isinstance(cur_a, list):
                            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                            cur_a.append({"ts": ts, "op": "copy", "from": from_path, "to": to_path})

            # 8) Commit
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
