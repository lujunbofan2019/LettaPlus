# Testing Plan: Phase 2 — Delegated Execution

**Version**: 1.0.0
**Last Updated**: 2025-01-30
**Author**: Claude Opus 4.5

This document provides a comprehensive end-to-end testing playbook for Phase 2 of the Dynamic Capabilities Framework (DCF+). It validates the delegated execution pattern involving **Conductor**, **Companion**, and **Strategist** agents.

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
    "metadata": {
      "type": "customer_support",
      "initiated_by": "conductor-001",
      "customer_id": "ACCT-7890"
    }
  }
}
```

**Response:**
```json
{
  "status": "success",
  "session_id": "session-support-001",
  "shared_blocks": {
    "session_goals": "block-goals-001",
    "task_log": "block-tasks-001",
    "session_context": "block-ctx-001"
  },
  "created_at": "2025-01-30T10:00:00Z"
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
    "session_id": "session-support-001"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "relationship": {
    "conductor": "conductor-001",
    "strategist": "strategist-001",
    "session_id": "session-support-001"
  },
  "guidelines_block": "strategist_guidelines"
}
```

#### Create Companions

**Tool Calls (parallel):**

```json
{
  "tool": "create_companion",
  "parameters": {
    "session_id": "session-support-001",
    "companion_name": "companion-lookup",
    "template_path": "dcf_mcp/agents/companion.af",
    "initial_tags": ["status:idle", "specialty:customer-data"]
  }
}
```

```json
{
  "tool": "create_companion",
  "parameters": {
    "session_id": "session-support-001",
    "companion_name": "companion-diagnosis",
    "template_path": "dcf_mcp/agents/companion.af",
    "initial_tags": ["status:idle", "specialty:troubleshooting"]
  }
}
```

**Responses:**
```json
{
  "status": "success",
  "companion_id": "companion-lookup-001",
  "companion_name": "companion-lookup",
  "session_id": "session-support-001",
  "status_tag": "status:idle"
}
```

```json
{
  "status": "success",
  "companion_id": "companion-diagnosis-001",
  "companion_name": "companion-diagnosis",
  "session_id": "session-support-001",
  "status_tag": "status:idle"
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
    "session_id": "session-support-001",
    "companion_id": "companion-lookup-001",
    "task_id": "task-001",
    "task_description": "Retrieve customer profile and interaction history for ACCT-7890",
    "skills_required": ["skill.lookup.customer@0.1.0"],
    "input_data": {
      "customer_id": "ACCT-7890"
    },
    "priority": "high"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "delegation_id": "del-001",
  "task_id": "task-001",
  "companion_id": "companion-lookup-001",
  "skills_assigned": ["skill.lookup.customer@0.1.0"],
  "status": "delegated",
  "delegated_at": "2025-01-30T10:00:30Z"
}
```

### Delegate Task 2: Issue Diagnosis (Parallel)

**Tool Call:**
```json
{
  "tool": "delegate_task",
  "parameters": {
    "session_id": "session-support-001",
    "companion_id": "companion-diagnosis-001",
    "task_id": "task-002",
    "task_description": "Diagnose dashboard access issue after password reset for customer ACCT-7890",
    "skills_required": ["skill.diagnose.issue@0.1.0"],
    "input_data": {
      "customer_id": "ACCT-7890",
      "symptoms": "Cannot access dashboard after password reset",
      "category": "authentication"
    },
    "priority": "high"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "delegation_id": "del-002",
  "task_id": "task-002",
  "companion_id": "companion-diagnosis-001",
  "skills_assigned": ["skill.diagnose.issue@0.1.0"],
  "status": "delegated",
  "delegated_at": "2025-01-30T10:00:31Z"
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
    "session_id": "session-support-001",
    "task_id": "task-001",
    "companion_id": "companion-lookup-001",
    "status": "completed",
    "result": {
      "customer_id": "ACCT-7890",
      "profile": {
        "name": "Michael Chen",
        "email": "m.chen@example.com",
        "account_type": "Premium",
        "account_status": "active",
        "flags": ["VIP_CUSTOMER", "BETA_FEATURES_ENABLED"]
      },
      "history": {
        "recent_password_reset": "2025-01-28",
        "total_interactions": 12,
        "avg_resolution_hours": 4.2
      },
      "notes": "VIP customer with Beta features enabled"
    }
  }
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
    "session_id": "session-support-001",
    "task_id": "task-002",
    "companion_id": "companion-diagnosis-001",
    "status": "completed",
    "result": {
      "issue_category": "authentication",
      "probable_cause": "Session cache not cleared after password change",
      "confidence": "high",
      "matched_known_issues": [
        {
          "id": "KB-2024-1847",
          "title": "Dashboard access blocked after password reset"
        }
      ],
      "recommended_resolution": [
        "Clear browser cache and cookies",
        "Close all browser windows",
        "Log in again using a fresh browser window",
        "Alternative: Use incognito/private browsing"
      ],
      "escalation_needed": false,
      "system_status": "All systems operational - no outages"
    }
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
    "strategist_agent_id": "strategist-001",
    "analysis_scope": {
      "tasks_completed": 3,
      "skills_used": [
        "skill.lookup.customer@0.1.0",
        "skill.diagnose.issue@0.1.0",
        "skill.compose.response@0.1.0"
      ]
    }
  }
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
    "include_metrics": true
  }
}
```

**Response:**
```json
{
  "session_id": "session-support-001",
  "duration_minutes": 5,
  "tasks": [
    {
      "task_id": "task-001",
      "type": "customer_lookup",
      "companion": "companion-lookup-001",
      "skill": "lookup.customer@0.1.0",
      "duration_seconds": 2.5,
      "status": "completed"
    },
    {
      "task_id": "task-002",
      "type": "issue_diagnosis",
      "companion": "companion-diagnosis-001",
      "skill": "diagnose.issue@0.1.0",
      "duration_seconds": 4.2,
      "status": "completed"
    },
    {
      "task_id": "task-003",
      "type": "response_composition",
      "companion": "companion-lookup-001",
      "skill": "compose.response@0.1.0",
      "duration_seconds": 1.8,
      "status": "completed"
    }
  ],
  "delegation_patterns": {
    "parallel_delegations": 1,
    "sequential_delegations": 2,
    "companion_utilization": {
      "companion-lookup-001": 2,
      "companion-diagnosis-001": 1
    }
  },
  "skill_metrics": {
    "lookup.customer@0.1.0": { "invocations": 1, "avg_duration": 2.5, "success_rate": 1.0 },
    "diagnose.issue@0.1.0": { "invocations": 1, "avg_duration": 4.2, "success_rate": 1.0 },
    "compose.response@0.1.0": { "invocations": 1, "avg_duration": 1.8, "success_rate": 1.0 }
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
    "conductor_agent_id": "conductor-001",
    "guidelines": {
      "skill_preferences": [
        {
          "skill": "diagnose.issue@0.1.0",
          "rating": "effective",
          "notes": "4.2s execution, consider for optimization",
          "use_for": ["authentication", "troubleshooting"]
        },
        {
          "skill": "compose.response@0.1.0",
          "rating": "fast",
          "notes": "1.8s execution, efficient for response generation"
        }
      ],
      "delegation_advice": [
        {
          "pattern": "lookup_and_diagnosis",
          "recommendation": "Delegate in parallel when customer lookup and issue diagnosis are both needed"
        },
        {
          "pattern": "companion_reuse",
          "recommendation": "Acceptable for low-volume sessions; consider specialization for high-volume"
        }
      ],
      "session_insights": {
        "avg_resolution_time": "5 minutes",
        "benchmark": "Significantly faster than historical average (4.2 hours)",
        "factors": ["Known issue match", "VIP customer prioritization", "Parallel delegation"]
      },
      "updated_at": "2025-01-30T10:05:30Z"
    }
  }
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
    "dismiss_companions": true,
    "archive_data": true,
    "summary": {
      "outcome": "resolved",
      "customer_id": "ACCT-7890",
      "issue_type": "authentication",
      "resolution": "KB-2024-1847 - Session cache workaround provided",
      "tasks_completed": 3,
      "duration_minutes": 5
    }
  }
}
```

**Response:**
```json
{
  "status": "success",
  "session_id": "session-support-001",
  "finalized_at": "2025-01-30T10:06:00Z",
  "companions_dismissed": 2,
  "archived": true,
  "archive_path": "sessions/session-support-001/",
  "metrics": {
    "total_tasks": 3,
    "total_delegations": 3,
    "skills_used": 3,
    "total_duration_minutes": 6
  }
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
| Companion template | `ls dcf_mcp/agents/companion.af` | File exists |

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
