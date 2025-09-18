import os
import json
import redis
import ast

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
    # --- 1) Parse patch_json robustly (JSON -> Python; fallback to Python-literal) ---
    try:
        if isinstance(patch_json, str):
            s = patch_json.strip()
            # Strip accidental code fences like ```json ... ```
            if s.startswith("```"):
                newline = s.find("\n")
                if newline != -1:
                    s = s[newline + 1 :]
                if s.endswith("```"):
                    s = s[:-3]
                s = s.strip()
            if s == "":
                patch = {}
            else:
                try:
                    patch = json.loads(s)
                except json.JSONDecodeError:
                    patch = ast.literal_eval(s)
        else:
            patch = patch_json  # already a dict-like
        # Normalize to pure JSON types
        patch = json.loads(json.dumps(patch))
    except Exception as e:
        return {"success": False, "error": f"patch_json is not valid or JSON-serializable: {e}", "redis_key": redis_key, "doc_json": None}

    if not isinstance(patch, dict):
        return {"success": False, "error": "patch_json must be an object.", "redis_key": redis_key, "doc_json": None}

    # --- 2) Normalize and validate path ---
    p_raw = (path or "").strip()
    is_root = False
    if p_raw in ("", "$"):
        is_root = True
        redis_path = "$"
        p = ""
    else:
        if p_raw.startswith("$."):
            p = p_raw[2:]
        elif p_raw.startswith("$"):
            p = p_raw[1:]
        else:
            p = p_raw
        if "[" in p or "]" in p or p == "" or p.startswith(".") or p.endswith(".") or ".." in p:
            return {"success": False, "error": "Invalid path; use '$' or dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}
        redis_path = "$." + p

    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    try:
        if is_root:
            # --- 3A) Root merge: get whole doc, ensure object, merge, set root ---
            doc = rc.json().get(redis_key, "$")
            if isinstance(doc, list) and doc:
                doc = doc[0]
            if doc is None:
                doc = {}
            if not isinstance(doc, dict):
                return {"success": False, "error": "Root is not an object.", "redis_key": redis_key, "doc_json": None}

            # Merge at root
            stack = [(doc, patch)]
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
            final_doc = rc.json().get(redis_key, "$")
            if isinstance(final_doc, list) and final_doc:
                final_doc = final_doc[0]
            return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}

        # --- 3B) Subpath merge ---
        # Try to fetch current subtree directly
        current = rc.json().get(redis_key, redis_path)
        if isinstance(current, list):
            current = current[0] if current else None

        if current is None:
            # Missing leaf or missing parents.
            # First attempt: create leaf as {} with JSON.SET NX (works only if parents exist).
            created_leaf = False
            try:
                rc.json().set(redis_key, redis_path, {}, nx=True)
                created_leaf = True
                current = {}
            except redis.exceptions.ResponseError:
                created_leaf = False  # parents likely missing

            if not created_leaf:
                # Minimal client-side parent creation
                root = rc.json().get(redis_key, "$")
                if isinstance(root, list) and root:
                    root = root[0]
                if root is None:
                    root = {}

                cur = root
                parts = p.split(".")
                for seg in parts[:-1]:
                    if not isinstance(cur, dict):
                        return {"success": False, "error": f"Cannot descend into non-object at '{seg}'", "redis_key": redis_key, "doc_json": None}
                    nxt = cur.get(seg)
                    if not isinstance(nxt, dict):
                        cur[seg] = {}
                        nxt = cur[seg]
                    cur = nxt
                leaf = parts[-1]
                if leaf not in cur or cur[leaf] is None or not isinstance(cur[leaf], dict):
                    cur[leaf] = {}
                current = cur[leaf]

                # Merge onto the new/empty target
                stack = [(current, patch)]
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

                # Persist whole doc once
                rc.json().set(redis_key, "$", root)

            else:
                # We created {} at the subpath; merge and set back at the subpath
                base = {}
                stack = [(base, patch)]
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
                rc.json().set(redis_key, redis_path, base)

        else:
            # Leaf exists. If it's not an object, treat as empty object (overwrite-by-merge semantics).
            if not isinstance(current, dict):
                base = {}
            else:
                base = current

            # Apply RFC-7386 merge onto 'base'
            stack = [(base, patch)]
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

            # Persist modified subtree directly at subpath
            rc.json().set(redis_key, redis_path, base)

        # --- 4) Return final full document ---
        final_doc = rc.json().get(redis_key, "$")
        if isinstance(final_doc, list) and final_doc:
            final_doc = final_doc[0]
        return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}

    except Exception as e:
        return {"success": False, "error": f"Merge error: {e}", "redis_key": redis_key, "doc_json": None}