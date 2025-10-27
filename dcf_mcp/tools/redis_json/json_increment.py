from typing import Any, Dict
import os
import json
import redis
import ast
import math

def json_increment(
    redis_key: str,
    path: str,
    delta: str
) -> Dict[str, Any]:
    """
    Increment a numeric field by `delta`.

    `delta` is accepted as a string and parsed into a number. Non-numeric or non-finite values (NaN/Infinity) are rejected.
    Initializes a missing field to 0, then adds `delta`. Errors if the existing value is not numeric. Incrementing at root
    "$" is not supported.

    Args:
        redis_key (str): Redis key of the JSON document.
        path (str): Path to a numeric field. "$.a.b" or "a.b" only, no bracket selectors, no indices.
        delta (str): Amount to add (string), may be negative.

    Returns:
        dict: { "success": bool, "error": str|None, "redis_key": str, "doc_json": str|None }
    """
    # --- 0) Parse delta (string -> float) robustly ---
    try:
        if isinstance(delta, str):
            s = delta.strip()
            # Strip accidental code fences like ```json ... ```
            if s.startswith("```"):
                nl = s.find("\n")
                if nl != -1:
                    s = s[nl + 1 :]
                if s.endswith("```"):
                    s = s[:-3]
                s = s.strip()
            # First try JSON numeric
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                # Fallback: Python-literal (supports 1_000, etc.)
                parsed = ast.literal_eval(s)
        else:
            # If a runner passes a number directly despite the str signature, accept it
            parsed = delta

        if isinstance(parsed, (int, float)):
            inc = float(parsed)
        elif isinstance(parsed, str):
            # e.g., delta='"5.0"' turned into "5.0"
            inc = float(parsed)
        else:
            return {"success": False, "error": "delta must be a numeric value (string).", "redis_key": redis_key, "doc_json": None}

        if not math.isfinite(inc):
            return {"success": False, "error": "delta must be a finite number (no NaN/Infinity).", "redis_key": redis_key, "doc_json": None}
    except Exception as e:
        return {"success": False, "error": f"Invalid delta: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 1) Normalize and validate path ---
    p_raw = (path or "").strip()
    if p_raw in ("", "$"):
        return {"success": False, "error": "Increment at `$` is not supported.", "redis_key": redis_key, "doc_json": None}

    if p_raw.startswith("$."):
        p = p_raw[2:]
    elif p_raw.startswith("$"):
        p = p_raw[1:]
    else:
        p = p_raw

    if "[" in p or "]" in p or p == "" or p.startswith(".") or p.endswith(".") or ".." in p:
        return {"success": False, "error": "Invalid path; use dot paths like 'a.b' (no brackets/indices).", "redis_key": redis_key, "doc_json": None}

    redis_path = "$." + p
    rc = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # --- 2) Try server-side NUMINCRBY first (atomic) ---
    try:
        rc.json().numincrby(redis_key, redis_path, inc)
    except redis.exceptions.ResponseError:
        # --- 3) Fallback: initialize missing chain/leaf to 0, then re-run NUMINCRBY ---
        doc = rc.json().get(redis_key, "$")
        if isinstance(doc, list) and doc:
            doc = doc[0]
        if doc is None:
            doc = {}

        cur = doc
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
        if leaf not in cur or cur[leaf] is None:
            cur[leaf] = 0
            try:
                rc.json().set(redis_key, "$", doc)
            except Exception as e:
                return {"success": False, "error": f"Failed to initialize numeric field: {e}", "redis_key": redis_key, "doc_json": None}
        else:
            if not isinstance(cur[leaf], (int, float)):
                return {"success": False, "error": "Target is not numeric.", "redis_key": redis_key, "doc_json": None}

        # Re-attempt atomic increment
        try:
            rc.json().numincrby(redis_key, redis_path, inc)
        except redis.exceptions.ResponseError as e:
            return {"success": False, "error": f"Increment failed: {e}", "redis_key": redis_key, "doc_json": None}
        except Exception as e:
            return {"success": False, "error": f"Increment error: {e}", "redis_key": redis_key, "doc_json": None}
    except Exception as e:
        return {"success": False, "error": f"Increment error: {e}", "redis_key": redis_key, "doc_json": None}

    # --- 4) Return final doc ---
    final_doc = rc.json().get(redis_key, "$")
    if isinstance(final_doc, list) and final_doc:
        final_doc = final_doc[0]
    if final_doc is None:
        final_doc = {}
        rc.json().set(redis_key, "$", final_doc)
    return {"success": True, "error": None, "redis_key": redis_key, "doc_json": json.dumps(final_doc)}
