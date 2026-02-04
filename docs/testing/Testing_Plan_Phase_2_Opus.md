# Testing Plan: Phase 2 — Delegated Execution

**Version**: 1.1.0
**Last Updated**: 2026-02-04
**Author**: Claude Opus 4.5

This document provides a comprehensive end-to-end testing playbook for Phase 2 of the Dynamic Capabilities Framework (DCF+). It validates the delegated execution pattern involving **Conductor**, **Companion**, and **Strategist** agents.

> **E2E Testing Completed**: All 12 DCF+ tools have been validated. See [E2E Testing Results](#e2e-testing-results) section for findings and fixes.

---

## Table of Contents

1. [Overview](#overview)
2. [Test Scenario: Customer Support Session](#test-scenario-customer-support-session)
3. [Setup: Skill Definitions](#setup-skill-definitions)
4. [Setup: Stub MCP Configuration](#setup-stub-mcp-configuration)
5. [Test Execution: Session Initialization](#test-execution-session-initialization)
6. [Test Execution: Task Delegation](#test-execution-task-delegation)
7. [Test Execution: Companion Task Execution](#test-execution-companion-task-execution)
8. [Test Execution: Multi-Turn Conversation](#test-execution-multi-turn-conversation)
9. [Test Execution: Strategist Analysis](#test-execution-strategist-analysis)
10. [Test Execution: Session Finalization](#test-execution-session-finalization)
11. [Verification Checklist](#verification-checklist)
12. [Cleanup](#cleanup)

---

## Overview

### Agents Under Test

| Agent | Role | Key Responsibilities |
|-------|------|---------------------|
| **Conductor** | Orchestrator | Continuous user conversation, skill discovery, task delegation, Companion management, result synthesis |
| **Companion** | Executor | Skill loading, task execution, result reporting (simple executor pattern) |
| **Strategist** | Advisor | Real-time session observation, pattern analysis, optimization recommendations |

### Key Differences from Phase 1

| Aspect | Phase 1 (Workflow) | Phase 2 (Delegated) |
|--------|-------------------|---------------------|
| Planning | Predetermined DAG upfront | Dynamic during conversation |
| Executors | Ephemeral Workers (per-workflow) | Session-scoped Companions |
| User Engagement | Paused during execution | **Continuous** |
| Coordination | Redis control plane + leases | Shared memory blocks + async messaging |
| Optimization | Post-workflow Reflector | **Real-time Strategist** |
| Skill Authority | Planner at workflow creation | **Conductor at each delegation** |

### Execution Flow

```
User → Conductor (continuous conversation)
         ↓
    Session Initialization (create_session_context)
         ↓
    Strategist Registration (register_strategist)
         ↓
    Companion Creation (create_companion)
         ↓
    ┌─────────────────────────────────────────────┐
    │  Conversation Loop (repeats per user turn)  │
    │                                             │
    │  User Request → Task Identification         │
    │       ↓                                     │
    │  Skill Discovery (get_skillset)             │
    │       ↓                                     │
    │  Check Strategist Guidelines                │
    │       ↓                                     │
    │  Delegate Task (delegate_task)              │
    │       ↓                                     │
    │  Companion: Load Skill → Execute → Report   │
    │       ↓                                     │
    │  Synthesize Response to User                │
    │       ↓                                     │
    │  Trigger Strategist Analysis (periodic)     │
    └─────────────────────────────────────────────┘
         ↓
    Session Finalization (finalize_session)
```

---

## E2E Testing Results

> **Testing Completed**: 2026-02-04

### Summary

All 12 DCF+ tools have been validated through end-to-end testing. Several issues were discovered and fixed during testing.

### Issues Discovered and Fixed

#### 1. Letta Client Tag Parsing Bug (Critical)

**Issue**: `letta_client` library's `agents.list()` and `agents.retrieve()` methods return empty tags, breaking all tag-based filtering.

**Root Cause**: The SDK doesn't properly parse the `tags` field from API responses.

**Fix**: Added `_get_agent_tags()` helper function using direct HTTP API calls:

```python
def _get_agent_tags(agent_id: str) -> List[str]:
    """Get agent tags via HTTP API (letta_client doesn't parse tags correctly)."""
    try:
        url = f"{LETTA_BASE_URL}/v1/agents/{agent_id}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
            return data.get("tags", []) or []
    except Exception:
        return []
```

**Files Fixed**:
- `list_session_companions.py`
- `delegate_task.py`
- `update_companion_status.py`
- `report_task_result.py`
- `broadcast_task.py`
- `finalize_session.py`
- `read_session_activity.py`

#### 2. Missing Model Parameter in create_companion

**Issue**: `create_companion()` failed with "Must specify either model or llm_config in request".

**Fix**: Added `model` parameter and `DCF_DEFAULT_MODEL` environment variable:

```python
DEFAULT_MODEL = os.getenv("DCF_DEFAULT_MODEL", "openai/gpt-4o-mini")

def create_companion(
    session_id: str,
    conductor_id: str,
    ...
    model: Optional[str] = None,  # NEW
) -> Dict[str, Any]:
```

### Correct Tool Signatures (Updated from Testing)

The testing revealed several parameter name discrepancies. Here are the **correct** signatures:

#### Session Management

```python
# create_session_context
def create_session_context(
    session_id: str,
    conductor_id: str,
    objective: Optional[str] = None,           # NOT user_goals_json
    initial_context_json: Optional[str] = None, # NOT preferences_json
) -> Dict[str, Any]

# finalize_session
def finalize_session(
    session_id: str,
    session_context_block_id: str,  # NOT conductor_id
    delete_companions: bool = True,  # NOT dismiss_companions
    delete_session_block: bool = False,
    preserve_wisdom: bool = True,
) -> Dict[str, Any]
```

#### Companion Lifecycle

```python
# create_companion
def create_companion(
    session_id: str,
    conductor_id: str,
    specialization: str = "generalist",
    shared_block_ids_json: Optional[str] = None,
    initial_skills_json: Optional[str] = None,
    companion_name: Optional[str] = None,
    persona_override: Optional[str] = None,
    model: Optional[str] = None,  # REQUIRED for agent creation
) -> Dict[str, Any]

# dismiss_companion - NO session_id parameter
def dismiss_companion(
    companion_id: str,
    unload_skills: bool = True,
    detach_shared_blocks: bool = True,
) -> Dict[str, Any]
```

#### Task Delegation

```python
# delegate_task
def delegate_task(
    conductor_id: str,
    companion_id: str,
    task_description: str,
    required_skills_json: Optional[str] = None,  # NOT skills_required
    input_data_json: Optional[str] = None,
    priority: str = "normal",
    timeout_seconds: int = 300,
    session_id: Optional[str] = None,
) -> Dict[str, Any]

# report_task_result
def report_task_result(
    companion_id: str,
    task_id: str,
    conductor_id: str,           # REQUIRED positional
    status: str,                  # "succeeded" | "failed" | "partial"
    summary: str,                 # REQUIRED
    output_data_json: Optional[str] = None,  # NOT output_json
    artifacts_json: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    metrics_json: Optional[str] = None,
) -> Dict[str, Any]
```

#### Strategist Integration

```python
# register_strategist
def register_strategist(
    conductor_agent_id: str,
    strategist_agent_id: str,
    initial_guidelines_json: str = None,
) -> Dict[str, Any]

# trigger_strategist_analysis
def trigger_strategist_analysis(
    session_id: str,
    conductor_agent_id: str,
    trigger_reason: str = "periodic",  # "periodic"|"milestone"|"on_demand"|"task_completed"
    tasks_since_last_analysis: int = None,
    recent_failures: int = None,
    include_full_history: bool = False,
    async_message: bool = True,
    max_steps: int = None,
) -> Dict[str, Any]

# update_conductor_guidelines
def update_conductor_guidelines(
    conductor_id: str,
    guidelines_json: Any = None,
    recommendation: Optional[str] = None,
    skill_preferences_json: Any = None,
    companion_scaling_json: Any = None,
    clear_guidelines: bool = False,
) -> Dict[str, Any]
```

### Tag-Based Status Tracking

Companions use tags for status management (verified working):

```
role:companion
session:{session_id}
specialization:{type}
status:idle | status:busy | status:error
conductor:{conductor_id}
task:{task_id}  # Only when busy
```

### Memory Block Labels (Verified)

| Block Label | Agent | Purpose |
|-------------|-------|---------|
| `session_context:{session_id}` | Shared | Session state, goals, announcements |
| `task_context` | Companion | Current task and history |
| `delegation_log` | Conductor | Task delegation tracking for Strategist |
| `strategist_registration` | Conductor | Registered Strategist ID |
| `strategist_guidelines` | Conductor (shared) | Strategist recommendations |
| `conductor_reference` | Strategist | Reference to Conductor |

### Tools Verification Status

| Tool | Status | Notes |
|------|--------|-------|
| `create_session_context` | ✅ Working | Creates shared session block |
| `create_companion` | ✅ Working | Requires `model` parameter |
| `list_session_companions` | ✅ Working | Uses HTTP API for tags |
| `update_companion_status` | ✅ Working | Updates tags correctly |
| `delegate_task` | ✅ Working | Logs to delegation_log, sends async message |
| `report_task_result` | ✅ Working | Updates status, logs completion |
| `dismiss_companion` | ✅ Working | No session_id parameter |
| `finalize_session` | ✅ Working | Requires session_context_block_id |
| `register_strategist` | ✅ Working | Creates 3 shared blocks |
| `trigger_strategist_analysis` | ✅ Working | Sends async analysis event |
| `read_session_activity` | ✅ Working | Returns comprehensive metrics |
| `update_conductor_guidelines` | ✅ Working | Updates recommendations |

---

### Prerequisites

Ensure all services are running:

```bash
docker compose up --build
```

Verify service health:

| Service | Health Check | Expected |
|---------|--------------|----------|
| Letta API | `curl -sf http://localhost:8283/v1/health/` | `{"status": "ok"}` |
| DCF MCP | `curl -sf http://localhost:8337/healthz` | `{"status": "healthy"}` |
| Stub MCP | `curl -sf http://localhost:8765/healthz` | `{"status": "ok"}` |
| Redis | `redis-cli -p 6379 ping` | `PONG` |

---

## Test Scenario: Customer Support Session

### Business Context

A customer support representative uses an AI-powered assistant to help resolve customer issues. During a support session, the assistant needs to:

1. **Look up customer information** — Retrieve account details and history
2. **Diagnose technical issues** — Analyze symptoms and identify root causes
3. **Compose responses** — Generate professional, helpful reply messages

The Conductor manages the conversation flow, delegating specific tasks to specialized Companions as needed.

### Test Customer Data

```json
{
  "customer_id": "ACCT-7890",
  "customer_name": "Michael Chen",
  "email": "m.chen@example.com",
  "account_type": "Premium",
  "issue": "Cannot access dashboard after password reset"
}
```

### Session Flow

1. User describes customer issue
2. Conductor delegates customer lookup to Companion A
3. Conductor delegates issue diagnosis to Companion B
4. Conductor synthesizes findings and requests response composition
5. Conductor presents final response to user
6. Strategist analyzes session and provides optimization recommendations

---

## Setup: Skill Definitions

Create the following skill files in `skills_src/skills/`:

### Skill 1: lookup.customer

**File:** `skills_src/skills/lookup.customer.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.lookup.customer@0.1.0
  name: lookup.customer
  version: 0.1.0
  description: Retrieves customer account information and interaction history
  tags:
    - support
    - customer
    - lookup
    - testing
spec:
  permissions:
    egress: intranet
    secrets: []
  directives: |
    You are a customer data specialist. Your task is to retrieve comprehensive
    customer information for support purposes.

    ## Lookup Steps
    1. Use `support:get_customer_profile` to retrieve basic account information
    2. Use `support:get_interaction_history` to retrieve recent support interactions

    ## Output Format
    Return a customer summary with:
    - `customer_id`: Account identifier
    - `profile`: Name, email, account type, status
    - `history`: Recent interactions (last 5)
    - `flags`: Any account flags or notes
  tools:
    - ref: support:get_customer_profile
      required: true
      description: Retrieves customer profile and account details
    - ref: support:get_interaction_history
      required: true
      description: Retrieves recent customer interactions
  dataSources: []
```

### Skill 2: diagnose.issue

**File:** `skills_src/skills/diagnose.issue.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.diagnose.issue@0.1.0
  name: diagnose.issue
  version: 0.1.0
  description: Analyzes customer issue symptoms and identifies root causes
  tags:
    - support
    - diagnosis
    - troubleshooting
    - testing
spec:
  permissions:
    egress: intranet
    secrets: []
  directives: |
    You are a technical diagnosis specialist. Your task is to analyze reported
    issues and identify root causes.

    ## Diagnosis Steps
    1. Use `support:search_known_issues` to check for matching known issues
    2. Use `support:check_system_status` to verify any system-wide problems
    3. Use `support:analyze_account_logs` to review account-specific events

    ## Output Format
    Return a diagnosis report with:
    - `issue_category`: Classification of the issue
    - `probable_cause`: Most likely root cause
    - `confidence`: Confidence level (high/medium/low)
    - `matched_known_issues`: Any matching known issues from KB
    - `recommended_resolution`: Suggested fix steps
    - `escalation_needed`: Whether to escalate to engineering
  tools:
    - ref: support:search_known_issues
      required: true
      description: Searches knowledge base for known issues
    - ref: support:check_system_status
      required: true
      description: Checks current system status and outages
    - ref: support:analyze_account_logs
      required: true
      description: Analyzes account activity logs for anomalies
  dataSources: []
```

### Skill 3: compose.response

**File:** `skills_src/skills/compose.response.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.compose.response@0.1.0
  name: compose.response
  version: 0.1.0
  description: Generates professional customer support response messages
  tags:
    - support
    - writing
    - response
    - testing
spec:
  permissions:
    egress: none
    secrets: []
  directives: |
    You are a customer communication specialist. Your task is to compose
    professional, empathetic support responses.

    ## Composition Guidelines
    1. Use `support:get_response_templates` to retrieve relevant templates
    2. Personalize the response with customer name and specific issue details
    3. Include clear resolution steps
    4. Maintain professional, empathetic tone

    ## Output Format
    Return a response package with:
    - `subject`: Email subject line
    - `greeting`: Personalized greeting
    - `body`: Main response content with resolution steps
    - `closing`: Professional closing
    - `internal_notes`: Notes for support team (not sent to customer)
  tools:
    - ref: support:get_response_templates
      required: true
      description: Retrieves response templates for issue category
  dataSources: []
```

### Generate Manifests

```bash
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'
```

Verify:
```bash
ls -la generated/manifests/skill.lookup.customer-0.1.0.json
ls -la generated/manifests/skill.diagnose.issue-0.1.0.json
ls -la generated/manifests/skill.compose.response-0.1.0.json
```

---

## Setup: Stub MCP Configuration

Add the following tool definitions to `skills_src/tools.yaml`:

### Support Server Tools

```yaml
support:
  transport:
    type: streamable_http
    endpoint: http://stub-mcp:8765/mcp
  tools:
    get_customer_profile:
      description: Retrieves customer profile and account details
      params:
        type: object
        properties:
          customer_id:
            type: string
            description: Customer account identifier
        required:
          - customer_id
      cases:
        - id: premium_customer
          match:
            strategy: exact
            path: customer_id
            value: "ACCT-7890"
          response:
            customer_id: "ACCT-7890"
            name: "Michael Chen"
            email: "m.chen@example.com"
            phone: "+1-555-0142"
            account_type: "Premium"
            account_status: "active"
            created_date: "2023-06-15"
            subscription_tier: "Business Plus"
            payment_status: "current"
            flags:
              - "VIP_CUSTOMER"
              - "BETA_FEATURES_ENABLED"
          latencyMs: 75
        - id: customer_not_found
          match:
            strategy: regex
            path: customer_id
            value: "ACCT-0000"
          response:
            error: "Customer not found"
            customer_id: null
          latencyMs: 50

    get_interaction_history:
      description: Retrieves recent customer interactions
      params:
        type: object
        properties:
          customer_id:
            type: string
          limit:
            type: integer
            default: 5
        required:
          - customer_id
      cases:
        - id: recent_interactions
          match:
            strategy: exact
            path: customer_id
            value: "ACCT-7890"
          response:
            customer_id: "ACCT-7890"
            interactions:
              - id: "INT-4521"
                date: "2025-01-28"
                channel: "email"
                type: "password_reset_request"
                status: "completed"
                agent: "auto"
                summary: "Customer requested password reset"
              - id: "INT-4498"
                date: "2025-01-15"
                channel: "chat"
                type: "billing_inquiry"
                status: "resolved"
                agent: "Sarah K."
                summary: "Question about invoice charges"
              - id: "INT-4312"
                date: "2024-12-20"
                channel: "phone"
                type: "feature_request"
                status: "logged"
                agent: "David M."
                summary: "Request for API access"
            total_interactions: 12
            avg_resolution_time_hours: 4.2
          latencyMs: 100

    search_known_issues:
      description: Searches knowledge base for known issues
      params:
        type: object
        properties:
          symptoms:
            type: string
            description: Issue symptoms to search for
          category:
            type: string
        required:
          - symptoms
      cases:
        - id: password_reset_issue
          match:
            strategy: regex
            path: symptoms
            value: ".*password.*reset.*dashboard.*"
          response:
            matches_found: 2
            known_issues:
              - id: "KB-2024-1847"
                title: "Dashboard access blocked after password reset"
                category: "authentication"
                severity: "medium"
                affected_versions: ["2.4.x", "2.5.0"]
                root_cause: "Session cache not cleared after password change"
                resolution: "Clear browser cache and cookies, then log in again"
                workaround: "Use incognito/private browsing window"
                status: "fix_deployed"
                fix_version: "2.5.1"
              - id: "KB-2024-1652"
                title: "MFA token sync delay after credential change"
                category: "authentication"
                severity: "low"
                root_cause: "MFA token propagation delay (up to 5 minutes)"
                resolution: "Wait 5 minutes after password reset before logging in"
                status: "known_limitation"
          latencyMs: 150
        - id: no_matches
          match:
            strategy: exact
            path: symptoms
            value: "unknown_issue"
          response:
            matches_found: 0
            known_issues: []
          latencyMs: 100

    check_system_status:
      description: Checks current system status and outages
      params:
        type: object
        properties:
          service:
            type: string
            default: "all"
        required: []
      cases:
        - id: all_systems_normal
          match:
            strategy: exact
            path: service
            value: "all"
          response:
            overall_status: "operational"
            last_updated: "2025-01-30T10:00:00Z"
            services:
              - name: "Authentication Service"
                status: "operational"
                uptime_30d: "99.98%"
              - name: "Dashboard"
                status: "operational"
                uptime_30d: "99.95%"
              - name: "API Gateway"
                status: "operational"
                uptime_30d: "99.99%"
              - name: "Database Cluster"
                status: "operational"
                uptime_30d: "99.99%"
            recent_incidents: []
            scheduled_maintenance: null
          latencyMs: 50

    analyze_account_logs:
      description: Analyzes account activity logs for anomalies
      params:
        type: object
        properties:
          customer_id:
            type: string
          hours_back:
            type: integer
            default: 24
        required:
          - customer_id
      cases:
        - id: password_reset_logs
          match:
            strategy: exact
            path: customer_id
            value: "ACCT-7890"
          response:
            customer_id: "ACCT-7890"
            analysis_period: "24 hours"
            events:
              - timestamp: "2025-01-30T08:15:22Z"
                event: "PASSWORD_RESET_INITIATED"
                source: "web_portal"
                ip: "192.168.1.105"
                status: "success"
              - timestamp: "2025-01-30T08:16:45Z"
                event: "PASSWORD_RESET_COMPLETED"
                source: "email_link"
                ip: "192.168.1.105"
                status: "success"
              - timestamp: "2025-01-30T08:17:30Z"
                event: "LOGIN_ATTEMPT"
                source: "web_portal"
                ip: "192.168.1.105"
                status: "success"
              - timestamp: "2025-01-30T08:17:35Z"
                event: "DASHBOARD_ACCESS"
                source: "web_portal"
                ip: "192.168.1.105"
                status: "failed"
                error_code: "SESSION_CACHE_STALE"
              - timestamp: "2025-01-30T08:18:00Z"
                event: "DASHBOARD_ACCESS"
                source: "web_portal"
                ip: "192.168.1.105"
                status: "failed"
                error_code: "SESSION_CACHE_STALE"
            anomalies:
              - type: "repeated_failure"
                description: "Multiple dashboard access failures after successful login"
                error_code: "SESSION_CACHE_STALE"
                recommendation: "Clear session cache or use private browsing"
          latencyMs: 200

    get_response_templates:
      description: Retrieves response templates for issue category
      params:
        type: object
        properties:
          category:
            type: string
          tone:
            type: string
            default: "professional"
        required:
          - category
      cases:
        - id: auth_templates
          match:
            strategy: exact
            path: category
            value: "authentication"
          response:
            templates:
              - id: "TPL-AUTH-001"
                name: "Password Reset Follow-up"
                subject_template: "Re: Access Issue After Password Reset - [TICKET_ID]"
                body_template: |
                  Hi [CUSTOMER_NAME],

                  Thank you for reaching out about the dashboard access issue you're experiencing after your recent password reset.

                  We've identified this as a known issue (KB-2024-1847) related to session caching. Here's how to resolve it:

                  **Quick Fix:**
                  1. Clear your browser cache and cookies
                  2. Close all browser windows
                  3. Open a new browser window and log in again

                  **Alternative:**
                  - Try accessing the dashboard in an incognito/private browsing window

                  This issue has been fixed in our latest release (v2.5.1), which will be automatically applied to your account within the next 24 hours.

                  If you continue experiencing issues after trying these steps, please reply to this email and we'll investigate further.

                  Best regards,
                  [AGENT_NAME]
                  Customer Support Team
                tone: "professional"
                tags: ["password", "access", "cache"]
          latencyMs: 75
```

### Regenerate Stub Config

```bash
python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
```

---

## Test Execution: Session Initialization

### Turn 1: User Initiates Session

**User Input:**
```
I have a customer on the line who can't access their dashboard after resetting
their password. Customer ID is ACCT-7890. Can you help me resolve this?
```

### Conductor Initializes Session

**Chain-of-Thought:**
```
New support session starting. I need to:
1. Create session context for shared state
2. Register Strategist for optimization advice
3. Create Companions for task execution
4. Identify required tasks: customer lookup, issue diagnosis, response composition

Starting with session initialization.
```

#### Create Session Context

**Tool Call:**
```json
{
  "tool": "create_session_context",
  "parameters": {
    "session_id": "session-support-001",
    "conductor_id": "conductor-001",
    "objective": "Resolve customer ACCT-7890 dashboard access issue",
    "initial_context_json": "{\"type\": \"customer_support\", \"customer_id\": \"ACCT-7890\"}"
  }
}
```

**Response:**
```json
{
  "status": "Created session context for session 'session-support-001'",
  "error": null,
  "session_id": "session-support-001",
  "block_id": "block-ctx-001",
  "block_label": "session_context:session-support-001"
}
```

#### Register Strategist

**Tool Call:**
```json
{
  "tool": "register_strategist",
  "parameters": {
    "conductor_agent_id": "conductor-001",
    "strategist_agent_id": "strategist-001",
    "initial_guidelines_json": "{\"recommendations\": [], \"skill_preferences\": {}}"
  }
}
```

**Response:**
```json
{
  "status": "Strategist 'strategist-001' registered as companion to Conductor 'conductor-001'",
  "error": null,
  "conductor_agent_id": "conductor-001",
  "strategist_agent_id": "strategist-001",
  "registration_block_id": "block-reg-001",
  "guidelines_block_id": "block-guide-001",
  "delegation_log_block_id": "block-log-001",
  "warnings": []
}
```

#### Create Companions

**Tool Calls (parallel):**

```json
{
  "tool": "create_companion",
  "parameters": {
    "session_id": "session-support-001",
    "conductor_id": "conductor-001",
    "specialization": "customer-data",
    "companion_name": "companion-lookup",
    "model": "openai/gpt-4o-mini"
  }
}
```

```json
{
  "tool": "create_companion",
  "parameters": {
    "session_id": "session-support-001",
    "conductor_id": "conductor-001",
    "specialization": "troubleshooting",
    "companion_name": "companion-diagnosis",
    "model": "openai/gpt-4o-mini"
  }
}
```

**Responses:**
```json
{
  "status": "Created Companion 'companion-lookup' for session 'session-support-001'",
  "error": null,
  "companion_id": "agent-abc12345-...",
  "companion_name": "companion-lookup",
  "tags": ["role:companion", "session:session-support-001", "specialization:customer-data", "status:idle", "conductor:conductor-001"],
  "shared_blocks_attached": [],
  "skills_loaded": [],
  "warnings": []
}
```

```json
{
  "status": "Created Companion 'companion-diagnosis' for session 'session-support-001'",
  "error": null,
  "companion_id": "agent-def67890-...",
  "companion_name": "companion-diagnosis",
  "tags": ["role:companion", "session:session-support-001", "specialization:troubleshooting", "status:idle", "conductor:conductor-001"],
  "shared_blocks_attached": [],
  "skills_loaded": [],
  "warnings": []
}
```

#### Update Session Context

**Tool Call:**
```json
{
  "tool": "update_session_context",
  "parameters": {
    "session_id": "session-support-001",
    "updates": {
      "goals": [
        "Resolve customer ACCT-7890 dashboard access issue",
        "Identify root cause after password reset",
        "Provide resolution steps"
      ],
      "customer_context": {
        "customer_id": "ACCT-7890",
        "reported_issue": "Cannot access dashboard after password reset"
      },
      "companion_pool": ["companion-lookup-001", "companion-diagnosis-001"]
    }
  }
}
```

---

## Test Execution: Task Delegation

### Conductor Identifies Tasks and Discovers Skills

**Chain-of-Thought:**
```
Session initialized with 2 Companions. Now I need to:
1. Look up customer information (delegate to companion-lookup)
2. Diagnose the issue (delegate to companion-diagnosis)

Let me discover available skills for these tasks.
```

**Tool Call:**
```json
{
  "tool": "get_skillset",
  "parameters": {
    "query": "customer lookup support diagnosis troubleshooting response",
    "tags": ["support", "customer", "diagnosis"]
  }
}
```

**Response:**
```json
{
  "status": "success",
  "skills": [
    {
      "manifest_id": "skill.lookup.customer@0.1.0",
      "name": "lookup.customer",
      "description": "Retrieves customer account information and interaction history",
      "tags": ["support", "customer", "lookup", "testing"]
    },
    {
      "manifest_id": "skill.diagnose.issue@0.1.0",
      "name": "diagnose.issue",
      "description": "Analyzes customer issue symptoms and identifies root causes",
      "tags": ["support", "diagnosis", "troubleshooting", "testing"]
    },
    {
      "manifest_id": "skill.compose.response@0.1.0",
      "name": "compose.response",
      "description": "Generates professional customer support response messages",
      "tags": ["support", "writing", "response", "testing"]
    }
  ]
}
```

### Check Strategist Guidelines (First Check)

**Tool Call:**
```json
{
  "tool": "read_shared_memory_blocks",
  "parameters": {
    "agent_id": "conductor-001",
    "block_names": ["strategist_guidelines"]
  }
}
```

**Response:**
```json
{
  "strategist_guidelines": {
    "skill_preferences": [],
    "delegation_advice": [],
    "updated_at": null
  }
}
```

*No guidelines yet — Strategist hasn't analyzed any tasks.*

### Delegate Task 1: Customer Lookup

**Tool Call:**
```json
{
  "tool": "delegate_task",
  "parameters": {
    "conductor_id": "conductor-001",
    "companion_id": "companion-lookup-001",
    "task_description": "Retrieve customer profile and interaction history for ACCT-7890",
    "required_skills_json": "[\"skill.lookup.customer@0.1.0\"]",
    "input_data_json": "{\"customer_id\": \"ACCT-7890\"}",
    "priority": "high",
    "session_id": "session-support-001"
  }
}
```

**Response:**
```json
{
  "status": "Task 'task-abc123' delegated to Companion 'companion-lookup'",
  "error": null,
  "task_id": "task-abc123",
  "conductor_id": "conductor-001",
  "companion_id": "companion-lookup-001",
  "message_sent": true,
  "delegation_logged": true,
  "run_id": "run-xyz789"
}
```

### Delegate Task 2: Issue Diagnosis (Parallel)

**Tool Call:**
```json
{
  "tool": "delegate_task",
  "parameters": {
    "conductor_id": "conductor-001",
    "companion_id": "companion-diagnosis-001",
    "task_description": "Diagnose dashboard access issue after password reset for customer ACCT-7890",
    "required_skills_json": "[\"skill.diagnose.issue@0.1.0\"]",
    "input_data_json": "{\"customer_id\": \"ACCT-7890\", \"symptoms\": \"Cannot access dashboard after password reset\", \"category\": \"authentication\"}",
    "priority": "high",
    "session_id": "session-support-001"
  }
}
```

**Response:**
```json
{
  "status": "Task 'task-def456' delegated to Companion 'companion-diagnosis'",
  "error": null,
  "task_id": "task-def456",
  "conductor_id": "conductor-001",
  "companion_id": "companion-diagnosis-001",
  "message_sent": true,
  "delegation_logged": true,
  "run_id": "run-abc123"
}
```

---

## Test Execution: Companion Task Execution

### Companion A: Customer Lookup

#### Receive Delegation

Companion receives delegation message with:
- Task description
- Skills to load
- Input data

#### Update Status to Busy

**Tool Call (by Companion):**
```json
{
  "tool": "update_companion_status",
  "parameters": {
    "companion_id": "companion-lookup-001",
    "status": "busy"
  }
}
```

#### Load Skill

**Tool Call:**
```json
{
  "tool": "load_skill",
  "parameters": {
    "agent_id": "companion-lookup-001",
    "skill_manifest_id": "skill.lookup.customer@0.1.0"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "skill_loaded": "skill.lookup.customer@0.1.0",
  "tools_added": ["support:get_customer_profile", "support:get_interaction_history"],
  "directives_injected": true
}
```

#### Execute Skill Tools

**Tool 1: Get Customer Profile**
```json
{
  "tool": "support:get_customer_profile",
  "parameters": { "customer_id": "ACCT-7890" }
}
```

**Stub Response:**
```json
{
  "customer_id": "ACCT-7890",
  "name": "Michael Chen",
  "email": "m.chen@example.com",
  "phone": "+1-555-0142",
  "account_type": "Premium",
  "account_status": "active",
  "created_date": "2023-06-15",
  "subscription_tier": "Business Plus",
  "payment_status": "current",
  "flags": ["VIP_CUSTOMER", "BETA_FEATURES_ENABLED"]
}
```

**Tool 2: Get Interaction History**
```json
{
  "tool": "support:get_interaction_history",
  "parameters": { "customer_id": "ACCT-7890", "limit": 5 }
}
```

**Stub Response:**
```json
{
  "customer_id": "ACCT-7890",
  "interactions": [
    {
      "id": "INT-4521",
      "date": "2025-01-28",
      "channel": "email",
      "type": "password_reset_request",
      "status": "completed",
      "agent": "auto",
      "summary": "Customer requested password reset"
    },
    {
      "id": "INT-4498",
      "date": "2025-01-15",
      "channel": "chat",
      "type": "billing_inquiry",
      "status": "resolved",
      "agent": "Sarah K.",
      "summary": "Question about invoice charges"
    }
  ],
  "total_interactions": 12,
  "avg_resolution_time_hours": 4.2
}
```

#### Report Result

**Tool Call:**
```json
{
  "tool": "report_task_result",
  "parameters": {
    "companion_id": "companion-lookup-001",
    "task_id": "task-abc123",
    "conductor_id": "conductor-001",
    "status": "succeeded",
    "summary": "Retrieved customer profile and interaction history for ACCT-7890",
    "output_data_json": "{\"customer_id\": \"ACCT-7890\", \"profile\": {\"name\": \"Michael Chen\", \"email\": \"m.chen@example.com\", \"account_type\": \"Premium\", \"account_status\": \"active\", \"flags\": [\"VIP_CUSTOMER\", \"BETA_FEATURES_ENABLED\"]}, \"history\": {\"recent_password_reset\": \"2025-01-28\", \"total_interactions\": 12, \"avg_resolution_hours\": 4.2}, \"notes\": \"VIP customer with Beta features enabled\"}",
    "metrics_json": "{\"duration_s\": 2.5, \"tool_calls\": 2}"
  }
}
```

**Response:**
```json
{
  "status": "Task 'task-abc123' result (succeeded) reported to Conductor",
  "error": null,
  "task_id": "task-abc123",
  "companion_id": "companion-lookup-001",
  "conductor_id": "conductor-001",
  "message_sent": true,
  "delegation_log_updated": true,
  "run_id": "run-result-001"
}
```

#### Cleanup

```json
{ "tool": "unload_skill", "parameters": { "agent_id": "companion-lookup-001", "skill_manifest_id": "skill.lookup.customer@0.1.0" } }
{ "tool": "update_companion_status", "parameters": { "companion_id": "companion-lookup-001", "status": "idle" } }
```

---

### Companion B: Issue Diagnosis

#### Load Skill and Execute

**Tool 1: Search Known Issues**
```json
{
  "tool": "support:search_known_issues",
  "parameters": {
    "symptoms": "Cannot access dashboard after password reset",
    "category": "authentication"
  }
}
```

**Stub Response:**
```json
{
  "matches_found": 2,
  "known_issues": [
    {
      "id": "KB-2024-1847",
      "title": "Dashboard access blocked after password reset",
      "category": "authentication",
      "severity": "medium",
      "root_cause": "Session cache not cleared after password change",
      "resolution": "Clear browser cache and cookies, then log in again",
      "workaround": "Use incognito/private browsing window",
      "status": "fix_deployed",
      "fix_version": "2.5.1"
    }
  ]
}
```

**Tool 2: Check System Status**
```json
{
  "tool": "support:check_system_status",
  "parameters": { "service": "all" }
}
```

**Stub Response:**
```json
{
  "overall_status": "operational",
  "services": [
    { "name": "Authentication Service", "status": "operational" },
    { "name": "Dashboard", "status": "operational" }
  ],
  "recent_incidents": []
}
```

**Tool 3: Analyze Account Logs**
```json
{
  "tool": "support:analyze_account_logs",
  "parameters": { "customer_id": "ACCT-7890", "hours_back": 24 }
}
```

**Stub Response:**
```json
{
  "customer_id": "ACCT-7890",
  "events": [
    { "timestamp": "2025-01-30T08:17:35Z", "event": "DASHBOARD_ACCESS", "status": "failed", "error_code": "SESSION_CACHE_STALE" }
  ],
  "anomalies": [
    {
      "type": "repeated_failure",
      "description": "Multiple dashboard access failures after successful login",
      "error_code": "SESSION_CACHE_STALE",
      "recommendation": "Clear session cache or use private browsing"
    }
  ]
}
```

#### Report Result

```json
{
  "tool": "report_task_result",
  "parameters": {
    "companion_id": "companion-diagnosis-001",
    "task_id": "task-def456",
    "conductor_id": "conductor-001",
    "status": "succeeded",
    "summary": "Diagnosed dashboard access issue - known issue KB-2024-1847 (session cache)",
    "output_data_json": "{\"issue_category\": \"authentication\", \"probable_cause\": \"Session cache not cleared after password change\", \"confidence\": \"high\", \"matched_known_issues\": [{\"id\": \"KB-2024-1847\", \"title\": \"Dashboard access blocked after password reset\"}], \"recommended_resolution\": [\"Clear browser cache and cookies\", \"Close all browser windows\", \"Log in again using a fresh browser window\", \"Alternative: Use incognito/private browsing\"], \"escalation_needed\": false, \"system_status\": \"All systems operational - no outages\"}",
    "metrics_json": "{\"duration_s\": 4.2, \"tool_calls\": 3}"
  }
}
```

---

## Test Execution: Multi-Turn Conversation

### Conductor Synthesizes Results

**Conductor receives results from both Companions and synthesizes:**

**Response to User:**
```
I've analyzed the situation for customer ACCT-7890 (Michael Chen). Here's what I found:

## Customer Profile
- **Name:** Michael Chen
- **Account:** Premium (Business Plus tier)
- **Status:** Active, VIP customer with Beta features
- **Recent Activity:** Password reset requested on Jan 28

## Diagnosis
This is a **known issue** (KB-2024-1847) with high confidence:

**Root Cause:** Session cache not cleared after password change
- The customer's login succeeded, but dashboard access fails with SESSION_CACHE_STALE error
- All systems are currently operational (no outages)

## Resolution Steps
1. Have the customer clear their browser cache and cookies
2. Close all browser windows completely
3. Open a fresh browser window and log in again

**Alternative:** Use an incognito/private browsing window as an immediate workaround

This fix has been deployed in v2.5.1 and will auto-apply within 24 hours.

Would you like me to compose a response email for the customer?
```

### Turn 2: User Requests Response

**User Input:**
```
Yes, please compose a professional response email I can send to the customer.
```

### Conductor Delegates Response Composition

**Tool Call:**
```json
{
  "tool": "delegate_task",
  "parameters": {
    "session_id": "session-support-001",
    "companion_id": "companion-lookup-001",
    "task_id": "task-003",
    "task_description": "Compose professional response email for ACCT-7890 regarding dashboard access issue resolution",
    "skills_required": ["skill.compose.response@0.1.0"],
    "input_data": {
      "customer_name": "Michael Chen",
      "issue_category": "authentication",
      "known_issue_id": "KB-2024-1847",
      "resolution_steps": [
        "Clear browser cache and cookies",
        "Close all browser windows",
        "Log in again using a fresh browser window"
      ],
      "alternative": "Use incognito/private browsing"
    },
    "priority": "high"
  }
}
```

### Companion Executes Response Composition

**Load Skill → Get Templates → Compose Response**

**Tool Call:**
```json
{
  "tool": "support:get_response_templates",
  "parameters": { "category": "authentication", "tone": "professional" }
}
```

**Report Result:**
```json
{
  "result": {
    "subject": "Re: Access Issue After Password Reset - ACCT-7890",
    "greeting": "Hi Michael,",
    "body": "Thank you for reaching out about the dashboard access issue you're experiencing after your recent password reset.\n\nWe've identified this as a known issue (KB-2024-1847) related to session caching. Here's how to resolve it:\n\n**Quick Fix:**\n1. Clear your browser cache and cookies\n2. Close all browser windows\n3. Open a new browser window and log in again\n\n**Alternative:**\n- Try accessing the dashboard in an incognito/private browsing window\n\nThis issue has been fixed in our latest release (v2.5.1), which will be automatically applied to your account within the next 24 hours.\n\nIf you continue experiencing issues after trying these steps, please reply to this email and we'll investigate further.",
    "closing": "Best regards,\n[Your Name]\nCustomer Support Team",
    "internal_notes": "Known issue KB-2024-1847. Customer is VIP with Beta features. Fix deployed in v2.5.1."
  }
}
```

### Conductor Presents Final Response

**Response to User:**
```
Here's the response email ready to send:

---

**Subject:** Re: Access Issue After Password Reset - ACCT-7890

Hi Michael,

Thank you for reaching out about the dashboard access issue you're experiencing
after your recent password reset.

We've identified this as a known issue (KB-2024-1847) related to session caching.
Here's how to resolve it:

**Quick Fix:**
1. Clear your browser cache and cookies
2. Close all browser windows
3. Open a new browser window and log in again

**Alternative:**
- Try accessing the dashboard in an incognito/private browsing window

This issue has been fixed in our latest release (v2.5.1), which will be
automatically applied to your account within the next 24 hours.

If you continue experiencing issues after trying these steps, please reply to
this email and we'll investigate further.

Best regards,
[Your Name]
Customer Support Team

---

**Internal Notes:** Known issue KB-2024-1847. Customer is VIP with Beta features.
Fix deployed in v2.5.1.

Is there anything else you need for this case?
```

---

## Test Execution: Strategist Analysis

### Trigger Strategist Analysis

After 3 tasks completed, Conductor triggers Strategist analysis:

**Tool Call:**
```json
{
  "tool": "trigger_strategist_analysis",
  "parameters": {
    "session_id": "session-support-001",
    "conductor_agent_id": "conductor-001",
    "trigger_reason": "periodic",
    "tasks_since_last_analysis": 3,
    "recent_failures": 0,
    "include_full_history": false,
    "async_message": true
  }
}
```

**Response:**
```json
{
  "status": "Analysis triggered for session 'session-support-001' (async, reason: periodic)",
  "error": null,
  "session_id": "session-support-001",
  "conductor_agent_id": "conductor-001",
  "strategist_agent_id": "strategist-001",
  "message_sent": true,
  "run_id": "run-analysis-001"
}
```

### Strategist Analysis Flow

#### Step 1: Read Session Activity

**Tool Call (by Strategist):**
```json
{
  "tool": "read_session_activity",
  "parameters": {
    "session_id": "session-support-001",
    "conductor_id": "conductor-001",
    "include_companion_details": true,
    "include_task_history": true,
    "include_skill_metrics": true
  }
}
```

**Response:**
```json
{
  "status": "Activity report for session 'session-support-001'",
  "error": null,
  "session_id": "session-support-001",
  "session_state": "active",
  "session_context": {"objective": "Resolve customer ACCT-7890 dashboard access issue"},
  "delegations": [
    {"task_id": "task-abc123", "companion_id": "companion-lookup-001", "status": "completed", "result_status": "succeeded", "duration_s": 2.5, "skills_assigned": ["skill.lookup.customer@0.1.0"]},
    {"task_id": "task-def456", "companion_id": "companion-diagnosis-001", "status": "completed", "result_status": "succeeded", "duration_s": 4.2, "skills_assigned": ["skill.diagnose.issue@0.1.0"]},
    {"task_id": "task-ghi789", "companion_id": "companion-lookup-001", "status": "completed", "result_status": "succeeded", "duration_s": 1.8, "skills_assigned": ["skill.compose.response@0.1.0"]}
  ],
  "companions": [
    {"companion_id": "companion-lookup-001", "companion_name": "companion-lookup", "specialization": "customer-data", "status": "idle", "tasks_completed": 2, "tasks_failed": 0, "skills_used": ["skill.lookup.customer@0.1.0", "skill.compose.response@0.1.0"]},
    {"companion_id": "companion-diagnosis-001", "companion_name": "companion-diagnosis", "specialization": "troubleshooting", "status": "idle", "tasks_completed": 1, "tasks_failed": 0, "skills_used": ["skill.diagnose.issue@0.1.0"]}
  ],
  "skill_metrics": {
    "skill.lookup.customer@0.1.0": {"usage_count": 1, "success_count": 1, "failure_count": 0, "success_rate": 100.0, "avg_duration_s": 2.5},
    "skill.diagnose.issue@0.1.0": {"usage_count": 1, "success_count": 1, "failure_count": 0, "success_rate": 100.0, "avg_duration_s": 4.2},
    "skill.compose.response@0.1.0": {"usage_count": 1, "success_count": 1, "failure_count": 0, "success_rate": 100.0, "avg_duration_s": 1.8}
  },
  "metrics": {
    "companion_count": 2,
    "idle_companions": 2,
    "busy_companions": 0,
    "error_companions": 0,
    "total_delegations": 3,
    "completed_tasks": 3,
    "failed_tasks": 0,
    "pending_tasks": 0,
    "success_rate": 100.0,
    "avg_task_duration_s": 2.83,
    "unique_skills_used": 3
  }
}
```

#### Step 2: Analyze Patterns

Strategist identifies:

| Pattern | Observation |
|---------|-------------|
| **Parallel opportunity** | Tasks 1 and 2 were delegated in parallel — good efficiency |
| **Companion reuse** | companion-lookup executed 2 different skills (lookup + compose) |
| **Skill effectiveness** | All 3 skills succeeded, diagnose.issue took longest |
| **Session efficiency** | 5-minute resolution for VIP customer issue |

#### Step 3: Generate Recommendations

```json
{
  "recommendations": [
    {
      "type": "skill_preference",
      "skill": "diagnose.issue@0.1.0",
      "observation": "Takes 4.2s due to 3 sequential tool calls",
      "suggestion": "Consider parallel execution of search_known_issues and check_system_status",
      "priority": "medium"
    },
    {
      "type": "companion_specialization",
      "observation": "companion-lookup handled both lookup and composition tasks",
      "suggestion": "For high-volume sessions, consider dedicated compose companion",
      "priority": "low"
    },
    {
      "type": "delegation_pattern",
      "observation": "Parallel delegation of lookup + diagnosis was effective",
      "suggestion": "Continue parallelizing independent tasks",
      "priority": "high"
    },
    {
      "type": "session_efficiency",
      "observation": "5-minute resolution for authentication issue",
      "metric": "Faster than avg_resolution_time_hours (4.2h) for this customer",
      "sentiment": "positive"
    }
  ]
}
```

#### Step 4: Persist to Graphiti

**Tool Call:**
```json
{
  "tool": "graphiti:add_episode",
  "parameters": {
    "episode_type": "SessionPattern",
    "data": {
      "session_id": "session-support-001",
      "pattern_type": "support_resolution",
      "tasks_completed": 3,
      "skills_used": ["lookup.customer", "diagnose.issue", "compose.response"],
      "resolution_time_minutes": 5,
      "outcome": "successful",
      "customer_type": "VIP",
      "timestamp": "2025-01-30T10:05:00Z"
    }
  }
}
```

```json
{
  "tool": "graphiti:add_episode",
  "parameters": {
    "episode_type": "SkillMetric",
    "data": {
      "skill_id": "diagnose.issue@0.1.0",
      "session_id": "session-support-001",
      "duration_seconds": 4.2,
      "success": true,
      "tools_invoked": 3,
      "optimization_note": "Consider parallel tool execution"
    }
  }
}
```

#### Step 5: Publish Guidelines

**Tool Call:**
```json
{
  "tool": "update_conductor_guidelines",
  "parameters": {
    "conductor_id": "conductor-001",
    "recommendation": "Delegate lookup and diagnosis tasks in parallel when both are needed",
    "skill_preferences_json": "{\"authentication\": [\"skill.diagnose.issue@0.1.0\"], \"customer_lookup\": [\"skill.lookup.customer@0.1.0\"], \"response_generation\": [\"skill.compose.response@0.1.0\"]}",
    "companion_scaling_json": "{\"min_companions\": 2, \"max_companions\": 4, \"scale_up_threshold\": 5}"
  }
}
```

**Response:**
```json
{
  "status": "Updated Conductor guidelines: recommendations, skill_preferences, companion_scaling",
  "error": null,
  "conductor_id": "conductor-001",
  "guidelines_block_id": "block-guide-001",
  "updated_fields": ["recommendations", "skill_preferences", "companion_scaling"]
}
```

### Conductor Reads Updated Guidelines

On next delegation, Conductor checks guidelines:

```json
{
  "tool": "read_shared_memory_blocks",
  "parameters": {
    "agent_id": "conductor-001",
    "block_names": ["strategist_guidelines"]
  }
}
```

**Response includes new recommendations for future delegations.**

---

## Test Execution: Session Finalization

### User Ends Session

**User Input:**
```
That's everything for this case. Thanks for the help!
```

### Conductor Finalizes Session

**Tool Call:**
```json
{
  "tool": "finalize_session",
  "parameters": {
    "session_id": "session-support-001",
    "session_context_block_id": "block-ctx-001",
    "delete_companions": true,
    "delete_session_block": false,
    "preserve_wisdom": true
  }
}
```

**Response:**
```json
{
  "status": "Session 'session-support-001' finalized - 2 Companions dismissed",
  "error": null,
  "session_id": "session-support-001",
  "companions_dismissed": ["companion-lookup-001", "companion-diagnosis-001"],
  "wisdom_preserved": [
    {
      "companion_id": "companion-lookup-001",
      "companion_name": "companion-lookup",
      "specialization": "customer-data",
      "tasks_completed": 2,
      "task_history": ["..."]
    },
    {
      "companion_id": "companion-diagnosis-001",
      "companion_name": "companion-diagnosis",
      "specialization": "troubleshooting",
      "tasks_completed": 1,
      "task_history": ["..."]
    }
  ],
  "session_block_deleted": false,
  "warnings": []
}
```

### Conductor Closes Conversation

**Response to User:**
```
Happy to help! Session closed.

**Session Summary:**
- Customer: Michael Chen (ACCT-7890)
- Issue: Dashboard access after password reset
- Resolution: Known issue KB-2024-1847 - cache clearing instructions provided
- Duration: 5 minutes

The session has been archived for future reference. Have a great day!
```

---

## Verification Checklist

### Pre-Execution Checks

| Check | Command | Expected |
|-------|---------|----------|
| Services healthy | See Prerequisites | All services responding |
| Skills exist | `ls generated/manifests/skill.lookup.customer*` | 3 manifest files |
| Stub config updated | `cat generated/stub/stub_config.json \| grep support` | support tools present |
| DCF+ tools available | `docker exec dcf-mcp python3 -c "from tools.dcf_plus.create_companion import create_companion; print('OK')"` | OK |

### During Execution Checks

| Check | Verification | Expected |
|-------|--------------|----------|
| Session created | `read_session_context` | Session active |
| Companions created | `list_session_companions` | 2 companions listed |
| Skills loaded | Agent tools query | Skill tools available |
| Tasks delegated | Session task log | 3 tasks logged |
| Strategist registered | Guidelines block exists | Block created |

### Post-Execution Checks

| Check | Verification | Expected |
|-------|--------------|----------|
| All tasks completed | Task log | 3/3 completed |
| Companions dismissed | `list_session_companions` | Empty list |
| Session archived | Archive path | Files present |
| Guidelines published | Read guidelines block | Recommendations present |
| Graphiti episodes | Query Graphiti | SessionPattern + SkillMetric episodes |

### Expected Final State

```
Session State:
  session-support-001              → finalized, archived

Letta Agents:
  conductor-001                    → exists, guidelines updated
  strategist-001                   → exists
  companion-lookup-001             → dismissed (deleted)
  companion-diagnosis-001          → dismissed (deleted)

Graphiti:
  SessionPattern episode           → session-support-001
  SkillMetric episodes             → 3 skills tracked

Memory Blocks:
  strategist_guidelines            → populated with recommendations
  session_context                  → archived

Archive:
  sessions/session-support-001/
    session.json                   → session metadata
    tasks.json                     → task log
    delegations.json               → delegation history
    results.json                   → task results
```

---

## Cleanup

To reset the test environment:

```bash
# Clear session data from Redis
redis-cli keys "session:session-support-001:*" | xargs redis-cli del

# Remove archive
rm -rf sessions/session-support-001/

# Delete any remaining test agents (if not auto-cleaned)
# Use Letta API to delete agents by name pattern

# Clear Graphiti test episodes (optional)
# Use Graphiti admin tools

# Restart services if needed
docker compose restart
```

---

## Summary

This Phase 2 testing plan validates the delegated execution pattern:

| Phase | Components Tested |
|-------|-------------------|
| **Session Init** | `create_session_context`, `register_strategist`, `create_companion` |
| **Continuous Conversation** | Conductor ↔ User multi-turn dialogue |
| **Skill Discovery** | `get_skillset` for dynamic capability matching |
| **Task Delegation** | `delegate_task` with skill assignment |
| **Companion Execution** | Skill loading, tool execution, result reporting |
| **Result Synthesis** | Conductor aggregates Companion outputs |
| **Real-time Optimization** | Strategist analysis, guideline publishing |
| **Session Finalization** | Companion dismissal, archival |

### Key Differences Demonstrated

| Capability | How Tested |
|------------|------------|
| **Continuous engagement** | Multi-turn conversation without pausing for execution |
| **Dynamic delegation** | Tasks delegated as conversation evolves |
| **Session-scoped Companions** | Same Companions reused across multiple tasks |
| **Real-time Strategist** | Analysis triggered mid-session, not post-workflow |
| **Conductor skill authority** | Conductor discovers and assigns skills per delegation |

### Skills Tested

- `lookup.customer@0.1.0` — Customer profile and history retrieval
- `diagnose.issue@0.1.0` — Issue analysis and root cause identification
- `compose.response@0.1.0` — Professional response generation

### Tools Tested (via Stub MCP)

- `support:get_customer_profile`, `support:get_interaction_history`
- `support:search_known_issues`, `support:check_system_status`, `support:analyze_account_logs`
- `support:get_response_templates`

---

## Related Documentation

- **[PHASE2_E2E_TESTING_SUMMARY.md](PHASE2_E2E_TESTING_SUMMARY.md)** — Detailed E2E testing results, fixes, and correct function signatures
- **[Testing_Plan_Phase_1_Opus.md](Testing_Plan_Phase_1_Opus.md)** — Phase 1 (Workflow Execution) testing plan
- **[PHASE1_E2E_TESTING_SUMMARY.md](PHASE1_E2E_TESTING_SUMMARY.md)** — Phase 1 E2E testing results

---

## Quick E2E Test Commands

Run the following to validate all Phase 2 tools:

```bash
# Test all DCF+ tool imports
docker exec lettaplus-dcf-mcp-1 python3 -c "
from tools.dcf_plus.create_session_context import create_session_context
from tools.dcf_plus.create_companion import create_companion
from tools.dcf_plus.list_session_companions import list_session_companions
from tools.dcf_plus.delegate_task import delegate_task
from tools.dcf_plus.report_task_result import report_task_result
from tools.dcf_plus.dismiss_companion import dismiss_companion
from tools.dcf_plus.finalize_session import finalize_session
from tools.dcf_plus.register_strategist import register_strategist
from tools.dcf_plus.trigger_strategist_analysis import trigger_strategist_analysis
from tools.dcf_plus.read_session_activity import read_session_activity
from tools.dcf_plus.update_conductor_guidelines import update_conductor_guidelines
from tools.dcf_plus.update_companion_status import update_companion_status
print('All 12 DCF+ tools imported successfully')
"

# Run comprehensive E2E test (creates real agents, delegates tasks, cleans up)
docker exec lettaplus-dcf-mcp-1 python3 -c "
# See PHASE2_E2E_TESTING_SUMMARY.md for full test script
print('Run the full E2E test from docs/PHASE2_E2E_TESTING_SUMMARY.md')
"
```
