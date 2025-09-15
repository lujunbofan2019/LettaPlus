# proxy.py
import os
import sys
import time
import json
import uuid
import logging
import asyncio
import re
from collections import defaultdict
from typing import Dict, Optional, List, Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx

# =========================
# Configuration (env vars)
# =========================
UPSTREAM = os.getenv("UPSTREAM_BASE", "http://letta:8283")

# Comma-separated list of allowed origins for CORS (no spaces, or we'll strip them)
ADE_ORIGINS = [o.strip() for o in os.getenv(
    "ADE_ORIGINS", "http://localhost,https://app.letta.com"
).split(",") if o.strip()]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Turn on to see request/response previews and wire summaries
WIRE_DEBUG = os.getenv("WIRE_DEBUG", "false").lower() == "true"

# Show body previews (respecting limits); usually you want this with WIRE_DEBUG
LOG_BODY_PREVIEW = os.getenv("LOG_BODY_PREVIEW", "true").lower() == "true"
BODY_PREVIEW_MAX = int(os.getenv("BODY_PREVIEW_MAX", "300"))

# Wire logging: keep only summary lines, not step-by-step traces
LOG_WIRE_SUMMARY_ONLY = os.getenv("LOG_WIRE_SUMMARY_ONLY", "true").lower() == "true"
# Suppress these httpx/httpcore event prefixes (comma-separated)
WIRE_SUPPRESS_PREFIXES = [p.strip() for p in os.getenv(
    "WIRE_SUPPRESS_PREFIXES",
    "connect_tcp.,send_request_headers.,send_request_body.,receive_response_headers.,"
    "receive_response_body.,response_closed.,close."
).split(",") if p.strip()]

# Quiet endpoints: demote spammy paths to DEBUG and/or sample 1-in-N at INFO
QUIET_ENDPOINT_REGEXES = [p.strip() for p in os.getenv(
    "QUIET_ENDPOINT_REGEXES",
    # Polling & high-chatter APIs
    r"^/v1/agents/[^/]+/messages/?$,"
    r"^/v1/agents/[^/]+/messages/stream/?$,"
    r"^/v1/agents/[^/]+/messages/async/?$,"
    r"^/v1/agents/[^/]+/archival-memory/?$,"
    r"^/v1/agents/[^/]+/core-memory/blocks(?:/.*)?$,"
    r"^/v1/runs(?:/.*)?$,"
    r"^/v1/steps(?:/.*)?$,"
    r"^/v1/runs/active$"
).split(",") if p.strip()]
QUIET_SAMPLE_EVERY = int(os.getenv("QUIET_SAMPLE_EVERY", "20"))  # 1-in-N INFO logs

# Stateless identity line injected into prompts
IDENTITY_TEMPLATE = os.getenv("IDENTITY_TEMPLATE", "Your Letta agent name is {name}. Your Letta agent id is {id}.")
ENABLE_RUNTIME_IDENTITY_INJECTION = os.getenv("ENABLE_RUNTIME_IDENTITY_INJECTION", "true").lower() == "true"
EXTRA_INJECT_PATTERNS = [p.strip() for p in os.getenv("EXTRA_INJECT_PATTERNS", "").split(",") if p.strip()]

TIMEOUT_SECS = float(os.getenv("PROXY_TIMEOUT_SECS", "30"))
RETRIES = int(os.getenv("UPSTREAM_RETRIES", "6"))
BACKOFF = float(os.getenv("UPSTREAM_BACKOFF_SECS", "0.25"))  # initial backoff seconds


# =========================
# Logging setup
# =========================
root_logger = logging.getLogger()
for _h in list(root_logger.handlers):
    root_logger.removeHandler(_h)

stream = logging.StreamHandler(sys.stdout)
stream.setFormatter(logging.Formatter("%(message)s"))
root_logger.addHandler(stream)
root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

log = logging.getLogger("letta-proxy")
log.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# ---- Wire log filtering for httpx/httpcore ----
class WireFilter(logging.Filter):
    def __init__(self, summary_only: bool, suppress_prefixes: List[str]):
        super().__init__()
        self.summary_only = summary_only
        self.suppress_prefixes = tuple(suppress_prefixes)

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(msg.startswith(p) for p in self.suppress_prefixes):
            return False
        if self.summary_only:
            # Allow only high-level summaries
            if ("HTTP Request:" in msg) or ("HTTP/" in msg):
                return True
            return False
        return True

def _setup_wire_loggers():
    # Demote unrelated libs
    for name in ["anyio", "h11", "h2", "uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Configure httpx/httpcore
    for name in ["httpx", "httpcore"]:
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.propagate = False
        if WIRE_DEBUG:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            handler.addFilter(WireFilter(LOG_WIRE_SUMMARY_ONLY, WIRE_SUPPRESS_PREFIXES))
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)

_setup_wire_loggers()


def _redact_headers(h: Dict[str, str]) -> Dict[str, str]:
    out = {}
    for k, v in h.items():
        out[k] = "Bearer ***" if k.lower() == "authorization" else v
    return out


def _preview(b: Optional[bytes]) -> str:
    if not LOG_BODY_PREVIEW or not b:
        return ""
    return b[:BODY_PREVIEW_MAX].decode(errors="ignore")


def jlog(event: str, level: str = "INFO", **kw):
    kw["event"] = event
    msg = json.dumps(kw, default=str)
    lvl = (level or "INFO").upper()
    if lvl == "DEBUG":
        log.debug(msg)
    elif lvl == "WARNING":
        log.warning(msg)
    elif lvl == "ERROR":
        log.error(msg)
    else:
        log.info(msg)


# Hop-by-hop headers we should not forward
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "accept-encoding",
}

def _passthrough_headers(h: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in h.items() if k.lower() not in HOP_BY_HOP}


# =========================
# FastAPI app & middleware
# =========================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ADE_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _startup():
    jlog(
        "shim.startup",
        upstream=UPSTREAM,
        origins=ADE_ORIGINS,
        log_level=LOG_LEVEL,
        wire_debug=WIRE_DEBUG,
        retries=RETRIES,
        backoff=BACKOFF,
        timeout_secs=TIMEOUT_SECS,
        enable_runtime_identity_injection=ENABLE_RUNTIME_IDENTITY_INJECTION,
        quiet_regexes=QUIET_ENDPOINT_REGEXES,
        quiet_sample_every=QUIET_SAMPLE_EVERY,
        log_wire_summary_only=LOG_WIRE_SUMMARY_ONLY,
        wire_suppress_prefixes=WIRE_SUPPRESS_PREFIXES,
    )

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.rid = request.headers.get("x-request-id", str(uuid.uuid4()))
    return await call_next(request)


# =========================
# HTTP helper with retries
# =========================
async def upstream_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    content: Optional[bytes] = None,
    params: Optional[Dict[str, str]] = None,
    json_body: Optional[dict] = None,
):
    attempt = 0
    delay = BACKOFF
    last_exc = None
    while attempt < RETRIES:
        try:
            return await client.request(
                method,
                url,
                headers=headers,
                content=content,
                params=params,
                json=json_body,
            )
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            last_exc = e
            jlog(
                "upstream.retry",
                level="WARNING",
                attempt=attempt + 1,
                retries=RETRIES,
                delay_s=round(delay, 3),
                method=method,
                url=url,
                error=str(e),
            )
            attempt += 1
            await asyncio.sleep(delay)
            delay *= 2
    jlog("upstream.failed", level="ERROR", method=method, url=url, error=str(last_exc))
    return None


# =========================
# Helpers: quiet sampling & identity injection
# =========================
QUIET_PATTERNS: List[re.Pattern] = []
for pat in QUIET_ENDPOINT_REGEXES:
    try:
        QUIET_PATTERNS.append(re.compile(pat))
    except re.error:
        jlog("quiet.pattern_invalid", level="WARNING", pattern=pat)

_QUIET_COUNTERS: defaultdict[str, int] = defaultdict(int)

def _is_quiet_endpoint(path: str) -> bool:
    return any(p.match(path) for p in QUIET_PATTERNS)

def _sample_quiet_log(path: str) -> bool:
    n = QUIET_SAMPLE_EVERY if QUIET_SAMPLE_EVERY > 0 else 1
    _QUIET_COUNTERS[path] += 1
    return (_QUIET_COUNTERS[path] % n) == 1

def _log_level_for_path(path: str, default: str = "INFO") -> str:
    if _is_quiet_endpoint(path):
        # 1-in-N at INFO, rest at DEBUG
        return "INFO" if _sample_quiet_log(path) else "DEBUG"
    return default

def _should_log_body(method: str, ctype: str) -> bool:
    # Only show body previews for JSON POST/PUT/PATCH (typical message sends)
    if not LOG_BODY_PREVIEW:
        return False
    if method.upper() not in ("POST", "PUT", "PATCH"):
        return False
    return (ctype or "").lower().startswith("application/json")

# ----- Identity injection -----
_AGENTS_PREFIX = r"/v1/agents/[^/]+"
_DEFAULT_INJECT_PATTERNS: List[re.Pattern] = [
    re.compile(rf"^{_AGENTS_PREFIX}/messages/?$"),
    re.compile(rf"^{_AGENTS_PREFIX}/messages/async/?$"),
    re.compile(rf"^{_AGENTS_PREFIX}/messages/stream/?$"),
    # alternates (safe if unused)
    re.compile(rf"^{_AGENTS_PREFIX}/respond/?$"),
    re.compile(rf"^{_AGENTS_PREFIX}/chat/?$"),
    re.compile(rf"^{_AGENTS_PREFIX}/run/?$"),
    # batch fanout
    re.compile(r"^/v1/batches/?$"),
]
for pat in EXTRA_INJECT_PATTERNS:
    try:
        _DEFAULT_INJECT_PATTERNS.append(re.compile(pat))
    except re.error:
        jlog("inject.pattern_invalid", level="WARNING", pattern=pat)

def _should_inject_identity(path: str, method: str, ctype: str) -> bool:
    if not ENABLE_RUNTIME_IDENTITY_INJECTION:
        return False
    if method.upper() != "POST":
        return False
    if not (ctype or "").lower().startswith("application/json"):
        return False
    return any(p.match(path) for p in _DEFAULT_INJECT_PATTERNS)

def _extract_agent_id_from_path(path: str) -> Optional[str]:
    m = re.match(r"^/v1/agents/([^/]+)/", path)
    return m.group(1) if m else None

def _extract_agent_id_from_body(body: dict) -> Optional[str]:
    for k in ("agent_id", "agentId", "agentID"):
        if isinstance(body.get(k), str):
            return body[k]
    return None

async def _resolve_agent_name(client: httpx.AsyncClient, headers: Dict[str, str], agent_id: str) -> str:
    url = f"{UPSTREAM}/v1/agents/{agent_id}"
    r = await upstream_request(client, "GET", url, headers=headers)
    if r and 200 <= r.status_code < 300:
        try:
            nm = (r.json().get("name") or "").strip()
            if nm:
                return nm
        except Exception:
            pass
    return "UnnamedAgent"

def _identity_text(name: str, agent_id: str) -> str:
    return (IDENTITY_TEMPLATE.format(name=name, id=agent_id)).strip()

def _content_parts_contain_identity(parts: Any, identity_text: str) -> bool:
    if isinstance(parts, str):
        return identity_text in parts
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, dict):
                txt = p.get("text")
                if isinstance(txt, str) and identity_text in txt:
                    return True
    return False

def _infer_messages_style(messages: List[dict]) -> str:
    if not messages:
        return "string"
    first = messages[0]
    content = first.get("content")
    if isinstance(content, str):
        return "string"
    if isinstance(content, list):
        if content and isinstance(content[0], dict) and "type" in content[0]:
            return "parts"
    return "string"

def _make_system_message(identity_text: str, style: str) -> dict:
    if style == "parts":
        return {"role": "system", "content": [{"type": "text", "text": identity_text}]}
    return {"role": "system", "content": identity_text}

def _inject_into_messages_array(messages: Any, identity_text: str) -> Any:
    if not isinstance(messages, list):
        return messages
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            if _content_parts_contain_identity(msg.get("content"), identity_text):
                return messages
    style = _infer_messages_style(messages)
    messages.insert(0, _make_system_message(identity_text, style))
    return messages

def _inject_identity_payload(payload: dict, agent_id: str, agent_name: str) -> dict:
    identity = _identity_text(agent_name, agent_id)
    if isinstance(payload.get("messages"), list):
        payload["messages"] = _inject_into_messages_array(payload["messages"], identity)
        return payload
    if isinstance(payload.get("system"), str):
        if not payload["system"].startswith(identity):
            payload["system"] = f"{identity}\n\n{payload['system']}"
        return payload
    if isinstance(payload.get("instructions"), str):
        if not payload["instructions"].startswith(identity):
            payload["instructions"] = f"{identity}\n\n{payload['instructions']}"
        return payload
    payload["messages"] = [_make_system_message(identity, "string")]
    return payload

async def _inject_identity_for_single_request(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    path: str,
    payload: dict,
    rid: str,
) -> dict:
    agent_id = _extract_agent_id_from_path(path) or _extract_agent_id_from_body(payload)
    if not agent_id:
        jlog("proxy.identity_skip_no_agent_id", level="DEBUG", rid=rid, path=path)
        return payload
    agent_name = await _resolve_agent_name(client, headers, agent_id)
    payload = _inject_identity_payload(payload, agent_id, agent_name)
    jlog("proxy.identity_injected", level="INFO", rid=rid, agent_id=agent_id, agent_name=agent_name, path=path)
    return payload

async def _inject_identity_for_batch_requests(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    payload: dict,
    rid: str,
) -> dict:
    reqs = payload.get("requests")
    if not isinstance(reqs, list):
        return payload
    name_cache: Dict[str, str] = {}
    for item in reqs:
        if not isinstance(item, dict):
            continue
        aid = _extract_agent_id_from_body(item)
        if not aid:
            continue
        if aid not in name_cache:
            name_cache[aid] = await _resolve_agent_name(client, headers, aid)
        identity = _identity_text(name_cache[aid], aid)
        if isinstance(item.get("messages"), list):
            item["messages"] = _inject_into_messages_array(item["messages"], identity)
        else:
            item["messages"] = [_make_system_message(identity, "string")]
        jlog("proxy.identity_injected_batch_item", level="DEBUG", rid=rid, agent_id=aid, agent_name=name_cache[aid])
    jlog("proxy.identity_injected_batch", level="INFO", rid=rid, count=len(reqs))
    return payload


# =========================================
# Intercept: POST /v1/agents (pass-through)
# =========================================
@app.api_route("/v1/agents", methods=["POST"])
@app.api_route("/v1/agents/", methods=["POST"])
async def intercept_create_agent(request: Request):
    rid = request.state.rid if hasattr(request.state, "rid") else str(uuid.uuid4())

    raw_body = await request.body()
    headers = _passthrough_headers(request.headers)
    ctype = request.headers.get("content-type", "")

    # Inbound request (only useful when WIRE_DEBUG and JSON)
    if WIRE_DEBUG and _should_log_body("POST", ctype):
        jlog(
            "inbound.request",
            level="INFO",
            rid=rid,
            method="POST",
            path="/v1/agents/",
            qs=dict(request.query_params),
            headers=_redact_headers(headers),
            body_preview=_preview(raw_body),
        )

    async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
        create_url = f"{UPSTREAM}/v1/agents/"
        # Upstream request (body is same as inbound here)
        if WIRE_DEBUG and _should_log_body("POST", ctype):
            jlog(
                "upstream.request",
                level="INFO",
                rid=rid,
                method="POST",
                url=create_url,
                path="/v1/agents/",
                headers=_redact_headers(headers),
                body_preview=_preview(raw_body),
            )
        r = await upstream_request(
            client,
            "POST",
            create_url,
            headers=headers,
            content=raw_body,
            params=dict(request.query_params),
        )
        if r is None:
            return Response(
                status_code=502,
                content=json.dumps({"error": "Upstream unavailable during agent creation"}),
                media_type="application/json",
            )

    # Upstream response
    jlog(
        "upstream.response",
        level=_log_level_for_path("/v1/agents/"),
        rid=rid,
        status=r.status_code,
        ctype=r.headers.get("content-type", ""),
        body_preview=_preview(r.content),
    )

    # Final answer to caller
    jlog("final.response", level=_log_level_for_path("/v1/agents/"), rid=rid, status=r.status_code)

    return Response(
        content=r.content,
        status_code=r.status_code,
        headers={"content-type": r.headers.get("content-type", "application/json")},
    )


# =========================
# Catch-all proxy handler
# =========================
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_all(path: str, request: Request):
    rid = request.state.rid if hasattr(request.state, "rid") else str(uuid.uuid4())
    t0 = time.time()
    headers = _passthrough_headers(request.headers)
    ctype = request.headers.get("content-type", "")
    raw_body = await request.body()
    body = raw_body
    full_path = "/" + path
    method = request.method.upper()

    # 1) Inbound request log (payload preview) when WIRE_DEBUG
    inbound_level = _log_level_for_path(full_path)
    inbound_preview = _preview(raw_body) if (WIRE_DEBUG and _should_log_body(method, ctype)) else ""
    jlog(
        "inbound.request",
        level=inbound_level,
        rid=rid,
        method=method,
        path=full_path,
        qs=dict(request.query_params),
        headers=_redact_headers(headers),
        body_preview=inbound_preview,
    )

    # ===== Identity injection (stateless) =====
    injected = False
    if _should_inject_identity(full_path, method, ctype):
        payload = None
        try:
            payload = json.loads(raw_body.decode() or "{}")
        except Exception:
            payload = None

        if isinstance(payload, dict):
            async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
                if full_path.startswith("/v1/batches"):
                    payload = await _inject_identity_for_batch_requests(client, headers, payload, rid)
                else:
                    payload = await _inject_identity_for_single_request(client, headers, full_path, payload, rid)
            body = json.dumps(payload).encode("utf-8")
            injected = True

    # 2) Upstream request log (payload preview AFTER injection)
    upstream_level = _log_level_for_path(full_path)
    upstream_preview = _preview(body) if (WIRE_DEBUG and _should_log_body(method, ctype)) else ""
    jlog(
        "upstream.request",
        level=upstream_level,
        rid=rid,
        method=method,
        url=f"{UPSTREAM}/{path}",
        path=full_path,
        injected=injected,
        headers=_redact_headers(headers) if WIRE_DEBUG else None,
        body_preview=upstream_preview,
    )

    # 3) Perform upstream request
    async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
        resp = await upstream_request(
            client,
            method,
            f"{UPSTREAM}/{path}",
            headers=headers,
            content=body,
            params=dict(request.query_params),
        )
        if resp is None:
            return Response(
                status_code=502,
                content=json.dumps({"error": "Upstream unavailable", "upstream": UPSTREAM, "path": path}),
                media_type="application/json",
            )

    # 4) Upstream response log (payload preview)
    rsp_level = _log_level_for_path(full_path)
    rsp_preview = _preview(resp.content) if (WIRE_DEBUG and LOG_BODY_PREVIEW) else ""
    jlog(
        "upstream.response",
        level=rsp_level,
        rid=rid,
        path=full_path,
        status=resp.status_code,
        ms=round((time.time() - t0) * 1000),
        ctype=resp.headers.get("content-type", ""),
        body_preview=rsp_preview,
    )

    # 5) Final response log (status only; body is same as upstream)
    jlog("final.response", level=rsp_level, rid=rid, path=full_path, status=resp.status_code)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={"content-type": resp.headers.get("content-type", "application/json")},
    )
