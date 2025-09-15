# AI Agent RedisJSON Tools — End-to-End Conversation Test Plan

**Key under test:** `doc:onboarding:001`  
**Audit log path:** `$.logs`  
**Tools under test:** `json_set`, `json_ensure`, `json_append`, `json_increment`, `json_merge`, `json_move`, `json_copy`, `json_delete`, **`json_read`**

---

## How to use this plan

- Run this as a natural conversation with your agent. The agent should call the Python tools to satisfy each user turn.
- After *each* mutation, verify state using **`json_read`** with the provided paths.
- All schemas are JSON strings. Paths are object-style only (e.g., `$.a.b`, `$["a"]["b"]`).

> Tip: Keep Redis empty or delete the key before starting to ensure deterministic results.

---

## Turn 0 — Initialize document

**User → Agent**
> Start a fresh document for my onboarding workflow. Include a `status:"pending"`, empty `meta`, and `steps:{}`.

**Expected tool call**
```python
json_set(
  key="doc:onboarding:001",
  path="$",
  value_json='{"status":"pending","meta":{},"steps":{}}',
  validation_scope="document",
  global_schema_json='{"type":"object","required":["status","meta","steps"]}'
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$", pretty=True)
```
**Expected JSON (subset):**
```json
{
  "status": "pending",
  "meta": {},
  "steps": {}
}
```

---

## Turn 1 — Ensure `logs` and `events` arrays

**User → Agent**
> Make sure I have a `logs` array and an `events` array.

**Expected tool calls**
```python
json_ensure("doc:onboarding:001", "$.logs", "[]")
json_ensure("doc:onboarding:001", "$.events", "[]")
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.logs")
json_read("doc:onboarding:001", "$.events")
```
**Expected JSON (each):**
```json
[]
```

---

## Turn 2 — Append first event

**User → Agent**
> Record that onboarding started at `2025-09-04T09:00:00Z`.

**Expected tool call**
```python
json_append(
  key="doc:onboarding:001",
  path="$.events",
  value_json='{"ts":"2025-09-04T09:00:00Z","type":"start"}',
  validation_scope="subtree",
  subtree_schema_json='{"type":"array"}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.events", pretty=True)
json_read("doc:onboarding:001", "$.logs")  # should include an 'append' audit entry
```
**Expected `events`:**
```json
[
  {"ts":"2025-09-04T09:00:00Z","type":"start"}
]
```

---

## Turn 3 — Set `meta.started_at` with validation

**User → Agent**
> Set `meta.started_at` to the same ISO timestamp.

**Expected tool call**
```python
json_set(
  key="doc:onboarding:001",
  path="$.meta",
  value_json='{"started_at":"2025-09-04T09:00:00Z"}',
  validation_scope="subtree",
  subtree_schema_json='{"type":"object","properties":{"started_at":{"type":"string","format":"date-time"}},"required":["started_at"]}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.meta", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected `meta`:**
```json
{
  "started_at": "2025-09-04T09:00:00Z"
}
```

---

## Turn 4 — Increment counters

**User → Agent**
> Increment `counters.starts` by 1 (create it if missing).

**Expected tool call**
```python
json_increment(
  key="doc:onboarding:001",
  path="$.counters.starts",
  delta=1.0,
  initialize_missing_to_zero=True,
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.counters", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected `counters`:**
```json
{ "starts": 1 }
```

---

## Turn 5 — Merge step details (deep merge with deletion)

**User → Agent**
> Merge a new step `id="verify_identity"` with a status, add a nested `inputs` object, and delete any obsolete field.

**Expected tool call**
```python
json_merge(
  key="doc:onboarding:001",
  path="$.steps.verify_identity",
  patch_json='{"status":"in_progress","inputs":{"id_type":"passport","country":"GB"},"obsolete":null}',
  validation_scope="subtree",
  subtree_schema_json='{"type":"object","properties":{"status":{"type":"string"},"inputs":{"type":"object"}},"required":["status"]}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.steps.verify_identity", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected `steps.verify_identity`:**
```json
{
  "status": "in_progress",
  "inputs": { "id_type": "passport", "country": "GB" }
}
```

---

## Turn 6 — Ensure a result object for the step

**User → Agent**
> Ensure `steps.verify_identity.result` exists and defaults to `{ "approved": false }`.

**Expected tool call**
```python
json_ensure(
  key="doc:onboarding:001",
  path="$.steps.verify_identity.result",
  default_json='{"approved": false}',
  treat_null_as_missing=True,
  overwrite_if_type_mismatch=True,
  validation_scope="subtree",
  subtree_schema_json='{"type":"object","properties":{"approved":{"type":"boolean"}},"required":["approved"]}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.steps.verify_identity.result", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected `result`:**
```json
{ "approved": false }
```

---

## Turn 7 — Append another event

**User → Agent**
> Add an `event` that the ID scan finished at `2025-09-04T09:10:00Z`.

**Expected tool call**
```python
json_append(
  key="doc:onboarding:001",
  path="$.events",
  value_json='{"ts":"2025-09-04T09:10:00Z","type":"id_scan_complete"}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.events", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected `events`:**
```json
[
  {"ts":"2025-09-04T09:00:00Z","type":"start"},
  {"ts":"2025-09-04T09:10:00Z","type":"id_scan_complete"}
]
```

---

## Turn 8 — Move legacy info to canonical field

**User → Agent**
> Suppose a broker sent legacy data at `legacy.info`. Move it to `info` and overwrite anything there.

**Expected tool call**
```python
json_move(
  key="doc:onboarding:001",
  from_path="$.legacy.info",
  to_path="$.info",
  overwrite_if_exists=True,
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.info", pretty=True)
json_read("doc:onboarding:001", "$.legacy", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected:** If `legacy.info` existed, its contents appear under `info` and are removed from `legacy`.

---

## Turn 9 — Copy step snapshot

**User → Agent**
> Copy the current `steps.verify_identity` subtree to `snapshots.verify_identity_latest`.

**Expected tool call**
```python
json_copy(
  key="doc:onboarding:001",
  from_path="$.steps.verify_identity",
  to_path="$.snapshots.verify_identity_latest",
  overwrite_if_exists=True,
  validation_scope="subtree",
  subtree_schema_json='{"type":"object","properties":{"status":{"type":"string"}},"required":["status"]}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.snapshots.verify_identity_latest", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected snapshot:**
```json
{
  "status": "in_progress",
  "inputs": { "id_type": "passport", "country": "GB" },
  "result": { "approved": false }
}
```

---

## Turn 10 — Delete obsolete field

**User → Agent**
> Delete any `obsolete` field under `steps.verify_identity` if present.

**Expected tool call**
```python
json_delete(
  key="doc:onboarding:001",
  path="$.steps.verify_identity.obsolete",
  require_exists=False,
  validation_scope="subtree",
  subtree_schema_json='{"type":"object"}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.steps.verify_identity", pretty=True)
json_read("doc:onboarding:001", "$.logs")
```
**Expected:** The `obsolete` field should not exist.

---

## Turn 11 — Finalize: set status and whole-doc validation

**User → Agent**
> Mark the workflow `status:"completed"` and validate the whole document.

**Expected tool call**
```python
json_set(
  key="doc:onboarding:001",
  path="$.status",
  value_json='"completed"',
  validation_scope="document",
  global_schema_json='{"type":"object","properties":{"status":{"enum":["pending","in_progress","completed","failed","cancelled","skipped"]}},"required":["status"]}',
  audit_log_path="$.logs"
)
```

**Verify with reader**
```python
json_read("doc:onboarding:001", "$.status")
json_read("doc:onboarding:001", "$", pretty=True)
json_read("doc:onboarding:001", "$.logs", pretty=True)
```
**Expected final state (top-level excerpt):**
```json
{
  "status": "completed",
  "meta": { "started_at": "2025-09-04T09:00:00Z" },
  "events": [
    {"ts":"2025-09-04T09:00:00Z","type":"start"},
    {"ts":"2025-09-04T09:10:00Z","type":"id_scan_complete"}
  ],
  "steps": {
    "verify_identity": {
      "status": "in_progress",
      "inputs": { "id_type": "passport", "country": "GB" },
      "result": { "approved": false }
    }
  },
  "snapshots": {
    "verify_identity_latest": {
      "status": "in_progress",
      "inputs": { "id_type": "passport", "country": "GB" },
      "result": { "approved": false }
    }
  },
  "counters": { "starts": 1 },
  "logs": [
    {"ts":"<iso8601>", "op":"append",   "path":"$.events"},
    {"ts":"<iso8601>", "op":"set",      "path":"$.meta"},
    {"ts":"<iso8601>", "op":"increment","path":"$.counters.starts","delta":1.0},
    {"ts":"<iso8601>", "op":"merge",    "path":"$.steps.verify_identity"},
    {"ts":"<iso8601>", "op":"ensure",   "path":"$.steps.verify_identity.result"},
    {"ts":"<iso8601>", "op":"append",   "path":"$.events"},
    {"ts":"<iso8601>", "op":"move",     "from":"$.legacy.info","to":"$.info"},
    {"ts":"<iso8601>", "op":"copy",     "from":"$.steps.verify_identity","to":"$.snapshots.verify_identity_latest"},
    {"ts":"<iso8601>", "op":"delete",   "path":"$.steps.verify_identity.obsolete"},
    {"ts":"<iso8601>", "op":"set",      "path":"$.status"}
  ]
}
```

---

## Optional: Clean-up / Reset

To reset the test key to an empty object:
```python
json_set("doc:onboarding:001", "$", "{}")
```
