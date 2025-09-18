# AI Agent RedisJSON Tools — Simple Suite Conversation Test Plan (v2)

**Key under test (explicit):** `doc:onboarding:001`  
**Alternative:** Use auto-generated keys via `json_create("", "{}")` (see Turn 0 note).  
**Tools under test:** `json_create`, `json_set`, `json_ensure`, `json_append`, `json_increment`, `json_merge`, `json_move`, `json_copy`, `json_delete`, `json_read`

**Path rules:** dot paths only — `"$"`, `"$.a.b"`, or `"a.b"`. **No** bracket selectors and **no** array indices.

---

## How to run this plan

- Speak each **User → Agent** instruction to your agent.
- After every mutation, verify with **`json_read`**.
- This plan assumes you are using the *simplified* function signatures (no schemas, no audit logs).
- If you prefer an auto-generated key, replace `doc:onboarding:001` with the key returned by `json_create("", initial_json)`.

> Tip: To ensure deterministic results, start by resetting the key (Turn 0 uses `overwrite=True`).

---

## Turn 0 — Initialize document (use `json_create`)

**User → Agent**
> Create a fresh json document with `status:"pending"`, empty `meta`, and `steps:{}`. Use the key `doc:onboarding:001` and overwrite anything that exists.

**Expected tool call**
```python
json_create(
  key="doc:onboarding:001",
  initial_json='{"status":"pending","meta":{},"steps":{}}',
  overwrite=True
)
```

**Verify**
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

**Auto-key variant (optional):**
```python
res = json_create("", '{"status":"pending","meta":{},"steps":{}}')
# Use res["key"] for all subsequent calls in place of "doc:onboarding:001"
```

---

## Turn 1 — Ensure `logs` and `events` arrays

**User → Agent**
> Make sure I have both a `logs` array and an `events` array.

**Expected tool calls**
```python
json_ensure("doc:onboarding:001", "logs", "[]")
json_ensure("doc:onboarding:001", "events", "[]")
```

**Verify**
```python
json_read("doc:onboarding:001", "logs")
json_read("doc:onboarding:001", "events")
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
  path="events",
  value_json='{"ts":"2025-09-04T09:00:00Z","type":"start"}'
)
```

**Verify**
```python
json_read("doc:onboarding:001", "events", pretty=True)
```
**Expected `events`:**
```json
[
  {"ts":"2025-09-04T09:00:00Z","type":"start"}
]
```

---

## Turn 3 — Set `meta.started_at`

**User → Agent**
> Set `meta.started_at` to the same ISO timestamp.

**Expected tool call**
```python
json_set(
  key="doc:onboarding:001",
  path="meta",
  value_json='{"started_at":"2025-09-04T09:00:00Z"}'
)
```

**Verify**
```python
json_read("doc:onboarding:001", "meta", pretty=True)
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
  path="counters.starts",
  delta=1.0
)
```

**Verify**
```python
json_read("doc:onboarding:001", "counters", pretty=True)
```
**Expected `counters`:**
```json
{ "starts": 1 }
```

---

## Turn 5 — Merge step details (deep merge with deletion via null)

**User → Agent**
> Merge a new step `id="verify_identity"` with a status, add a nested `inputs` object, and delete any obsolete field.

**Expected tool call**
```python
json_merge(
  key="doc:onboarding:001",
  path="steps.verify_identity",
  patch_json='{"status":"in_progress","inputs":{"id_type":"passport","country":"GB"},"obsolete":null}'
)
```

**Verify**
```python
json_read("doc:onboarding:001", "steps.verify_identity", pretty=True)
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
  path="steps.verify_identity.result",
  default_json='{"approved": false}'
)
```

**Verify**
```python
json_read("doc:onboarding:001", "steps.verify_identity.result", pretty=True)
```
**Expected `result`:**
```json
{ "approved": false }
```

---

## Turn 7 — Append another event

**User → Agent**
> Add an event that the ID scan finished at `2025-09-04T09:10:00Z`.

**Expected tool call**
```python
json_append(
  key="doc:onboarding:001",
  path="events",
  value_json='{"ts":"2025-09-04T09:10:00Z","type":"id_scan_complete"}'
)
```

**Verify**
```python
json_read("doc:onboarding:001", "events", pretty=True)
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
> If there is legacy data at `legacy.info`, move it to `info` and overwrite anything there.

**Expected tool call**
```python
json_move(
  key="doc:onboarding:001",
  from_path="legacy.info",
  to_path="info",
  overwrite=True
)
```

**Verify**
```python
json_read("doc:onboarding:001", "info", pretty=True)
json_read("doc:onboarding:001", "legacy", pretty=True)
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
  from_path="steps.verify_identity",
  to_path="snapshots.verify_identity_latest",
  overwrite=True
)
```

**Verify**
```python
json_read("doc:onboarding:001", "snapshots.verify_identity_latest", pretty=True)
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
  path="steps.verify_identity.obsolete"
)
```

**Verify**
```python
json_read("doc:onboarding:001", "steps.verify_identity", pretty=True)
```
**Expected:** The `obsolete` field should not exist.

---

## Turn 11 — Finalize: set status

**User → Agent**
> Mark the workflow `status:"completed"`.

**Expected tool call**
```python
json_set(
  key="doc:onboarding:001",
  path="status",
  value_json='"completed"'
)
```

**Verify (final)**
```python
json_read("doc:onboarding:001", "$", pretty=True)
```
**Expected top-level excerpt:**
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
  "counters": { "starts": 1 }
}
```

---

## Optional: Clean-up / Reset

Reset the test key to an empty object:
```python
json_delete("doc:onboarding:001", "$")
```
