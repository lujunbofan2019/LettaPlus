# Testing Plan: Phase 1 — Workflow Execution

**Version**: 1.0.0
**Last Updated**: 2025-01-30
**Author**: Claude Opus 4.5

This document provides a comprehensive end-to-end testing playbook for Phase 1 of the Dynamic Capabilities Framework (DCF). It validates the complete workflow execution lifecycle involving **Planner**, **Worker**, and **Reflector** agents.

---

## Table of Contents

1. [Overview](#overview)
2. [Test Scenario: Order Processing Pipeline](#test-scenario-order-processing-pipeline)
3. [Setup: Skill Definitions](#setup-skill-definitions)
4. [Setup: Stub MCP Configuration](#setup-stub-mcp-configuration)
5. [Test Execution: User Conversation](#test-execution-user-conversation)
6. [Test Execution: Workflow Compilation](#test-execution-workflow-compilation)
7. [Test Execution: Worker Execution](#test-execution-worker-execution)
8. [Test Execution: Result Collection](#test-execution-result-collection)
9. [Test Execution: Reflector Analysis](#test-execution-reflector-analysis)
10. [Verification Checklist](#verification-checklist)
11. [Cleanup](#cleanup)

---

## Overview

### Agents Under Test

| Agent | Role | Key Responsibilities |
|-------|------|---------------------|
| **Planner** | Orchestrator | User conversation, skill discovery, workflow design, ASL compilation, execution monitoring, result presentation |
| **Worker** | Executor | State lease management, skill loading, task execution, output writing, downstream notification |
| **Reflector** | Advisor | Post-workflow analysis, pattern recognition, guideline generation, Graphiti persistence |

### Execution Flow

```
User → Planner (conversation)
         ↓
    Skill Discovery (get_skillset)
         ↓
    Workflow Design (ASL)
         ↓
    Validation (validate_workflow)
         ↓
    Control Plane Setup (create_workflow_control_plane)
         ↓
    Worker Creation (create_worker_agents)
         ↓
    Execution Trigger (notify_next_worker_agent)
         ↓
Workers ←→ Redis Control Plane (leases, state updates)
         ↓
    Finalization (finalize_workflow)
         ↓
    Result Presentation to User
         ↓
    Reflection Trigger (trigger_reflection)
         ↓
Reflector → Analysis → Guidelines → Graphiti
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

## Test Scenario: Order Processing Pipeline

### Business Context

An e-commerce operations manager wants to automate order processing. When a new order arrives, the system should:

1. **Validate** the order data (customer exists, items in stock, addresses valid)
2. **Calculate** the final pricing (subtotal, taxes, discounts, shipping)
3. **Generate** a formatted invoice document

### Test Order Data

```json
{
  "order_id": "ORD-2025-0042",
  "customer_id": "CUST-1234",
  "items": [
    { "sku": "WIDGET-A", "quantity": 3, "unit_price": 29.99 },
    { "sku": "GADGET-B", "quantity": 1, "unit_price": 149.99 }
  ],
  "shipping_address": {
    "street": "123 Main St",
    "city": "Austin",
    "state": "TX",
    "zip": "78701"
  },
  "discount_code": "SAVE10"
}
```

### Expected Outcome

A validated order with calculated totals and a formatted invoice ready for delivery.

---

## Setup: Skill Definitions

Create the following skill files in `skills_src/skills/`:

### Skill 1: validate.order

**File:** `skills_src/skills/validate.order.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.validate.order@0.1.0
  name: validate.order
  version: 0.1.0
  description: Validates order data including customer, inventory, and address verification
  tags:
    - validation
    - order
    - testing
spec:
  permissions:
    egress: intranet
    secrets: []
  directives: |
    You are an order validation specialist. Your task is to validate incoming orders.

    ## Validation Steps
    1. Use `orders:verify_customer` to confirm the customer exists and is in good standing
    2. Use `orders:check_inventory` to verify all items are in stock
    3. Use `orders:validate_address` to confirm the shipping address is deliverable

    ## Output Format
    Return a validation result with:
    - `valid`: boolean indicating overall validity
    - `customer_status`: customer verification details
    - `inventory_status`: per-item availability
    - `address_status`: address validation result
    - `errors`: array of any validation errors (empty if valid)
  tools:
    - ref: orders:verify_customer
      required: true
      description: Verifies customer exists and is in good standing
    - ref: orders:check_inventory
      required: true
      description: Checks inventory availability for order items
    - ref: orders:validate_address
      required: true
      description: Validates shipping address is deliverable
  dataSources: []
```

### Skill 2: calculate.pricing

**File:** `skills_src/skills/calculate.pricing.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.calculate.pricing@0.1.0
  name: calculate.pricing
  version: 0.1.0
  description: Calculates order totals including taxes, discounts, and shipping
  tags:
    - calculation
    - pricing
    - testing
spec:
  permissions:
    egress: intranet
    secrets: []
  directives: |
    You are a pricing calculation specialist. Your task is to compute final order totals.

    ## Calculation Steps
    1. Use `pricing:calculate_subtotal` to sum item prices
    2. Use `pricing:apply_discount` to apply any discount codes
    3. Use `pricing:calculate_tax` to compute taxes based on shipping address
    4. Use `pricing:calculate_shipping` to determine shipping costs

    ## Output Format
    Return a pricing breakdown with:
    - `subtotal`: sum of item prices before discounts
    - `discount_amount`: discount value applied
    - `tax_amount`: calculated tax
    - `shipping_amount`: shipping cost
    - `total`: final order total
    - `currency`: "USD"
  tools:
    - ref: pricing:calculate_subtotal
      required: true
      description: Calculates subtotal from order items
    - ref: pricing:apply_discount
      required: true
      description: Applies discount code and returns discount amount
    - ref: pricing:calculate_tax
      required: true
      description: Calculates tax based on address and subtotal
    - ref: pricing:calculate_shipping
      required: true
      description: Calculates shipping cost based on items and address
  dataSources: []
```

### Skill 3: generate.invoice

**File:** `skills_src/skills/generate.invoice.skill.yaml`

```yaml
apiVersion: skill/v1
kind: Skill
metadata:
  manifestId: skill.generate.invoice@0.1.0
  name: generate.invoice
  version: 0.1.0
  description: Generates formatted invoice documents from validated and priced orders
  tags:
    - generation
    - invoice
    - document
    - testing
spec:
  permissions:
    egress: none
    secrets: []
  directives: |
    You are an invoice generation specialist. Your task is to create formatted invoices.

    ## Generation Steps
    1. Use `documents:create_invoice` to generate the invoice document
    2. The tool will return a formatted invoice with all order details

    ## Output Format
    Return the generated invoice with:
    - `invoice_id`: unique invoice identifier
    - `invoice_date`: generation timestamp
    - `order_id`: reference to original order
    - `customer_info`: customer details
    - `line_items`: itemized list with prices
    - `totals`: pricing breakdown
    - `payment_terms`: standard NET-30 terms
    - `document_url`: link to PDF version (simulated)
  tools:
    - ref: documents:create_invoice
      required: true
      description: Creates formatted invoice document from order data
  dataSources: []
```

### Generate Manifests

After creating the skill files, regenerate manifests:

```bash
python -c 'from dcf_mcp.tools.dcf.generate import generate_all; print(generate_all())'
```

Verify the new manifests exist:

```bash
ls -la generated/manifests/skill.validate.order-0.1.0.json
ls -la generated/manifests/skill.calculate.pricing-0.1.0.json
ls -la generated/manifests/skill.generate.invoice-0.1.0.json
```

---

## Setup: Stub MCP Configuration

Add the following tool definitions to `skills_src/tools.yaml`:

### Orders Server Tools

```yaml
orders:
  transport:
    type: streamable_http
    endpoint: http://stub-mcp:8765/mcp
  tools:
    verify_customer:
      description: Verifies customer exists and is in good standing
      params:
        type: object
        properties:
          customer_id:
            type: string
            description: Customer identifier
        required:
          - customer_id
      cases:
        - id: customer_valid
          match:
            strategy: exact
            path: customer_id
            value: "CUST-1234"
          response:
            valid: true
            customer_name: "Jane Smith"
            account_status: "active"
            credit_limit: 5000.00
            current_balance: 250.00
          latencyMs: 50
        - id: customer_not_found
          match:
            strategy: regex
            path: customer_id
            value: "CUST-9999"
          response:
            valid: false
            error: "Customer not found"
          latencyMs: 50

    check_inventory:
      description: Checks inventory availability for order items
      params:
        type: object
        properties:
          items:
            type: array
            description: Array of items with sku and quantity
        required:
          - items
      cases:
        - id: items_in_stock
          match:
            strategy: regex
            path: items[0].sku
            value: "WIDGET.*"
          response:
            all_available: true
            items:
              - sku: "WIDGET-A"
                requested: 3
                available: 150
                status: "in_stock"
              - sku: "GADGET-B"
                requested: 1
                available: 25
                status: "in_stock"
          latencyMs: 75
        - id: items_out_of_stock
          match:
            strategy: exact
            path: items[0].sku
            value: "RARE-ITEM"
          response:
            all_available: false
            items:
              - sku: "RARE-ITEM"
                requested: 1
                available: 0
                status: "out_of_stock"
          latencyMs: 75

    validate_address:
      description: Validates shipping address is deliverable
      params:
        type: object
        properties:
          address:
            type: object
            description: Shipping address object
        required:
          - address
      cases:
        - id: texas_address
          match:
            strategy: exact
            path: address.state
            value: "TX"
          response:
            valid: true
            normalized_address:
              street: "123 Main Street"
              city: "Austin"
              state: "TX"
              zip: "78701-1234"
            delivery_zone: "ZONE-A"
            estimated_delivery_days: 3
          latencyMs: 100
        - id: invalid_address
          match:
            strategy: exact
            path: address.zip
            value: "00000"
          response:
            valid: false
            error: "Invalid ZIP code"
          latencyMs: 100
```

### Pricing Server Tools

```yaml
pricing:
  transport:
    type: streamable_http
    endpoint: http://stub-mcp:8765/mcp
  tools:
    calculate_subtotal:
      description: Calculates subtotal from order items
      params:
        type: object
        properties:
          items:
            type: array
            description: Order items with quantity and unit_price
        required:
          - items
      cases:
        - id: standard_order
          match:
            strategy: regex
            path: items[0].sku
            value: ".*"
          response:
            subtotal: 239.96
            item_count: 4
            line_items:
              - sku: "WIDGET-A"
                quantity: 3
                unit_price: 29.99
                line_total: 89.97
              - sku: "GADGET-B"
                quantity: 1
                unit_price: 149.99
                line_total: 149.99
          latencyMs: 25

    apply_discount:
      description: Applies discount code and returns discount amount
      params:
        type: object
        properties:
          subtotal:
            type: number
          discount_code:
            type: string
        required:
          - subtotal
      cases:
        - id: save10_discount
          match:
            strategy: exact
            path: discount_code
            value: "SAVE10"
          response:
            discount_applied: true
            discount_code: "SAVE10"
            discount_type: "percentage"
            discount_percent: 10
            discount_amount: 24.00
            subtotal_after_discount: 215.96
          latencyMs: 25
        - id: no_discount
          match:
            strategy: exact
            path: discount_code
            value: ""
          response:
            discount_applied: false
            discount_amount: 0
            subtotal_after_discount: 239.96
          latencyMs: 25

    calculate_tax:
      description: Calculates tax based on address and subtotal
      params:
        type: object
        properties:
          subtotal:
            type: number
          state:
            type: string
        required:
          - subtotal
          - state
      cases:
        - id: texas_tax
          match:
            strategy: exact
            path: state
            value: "TX"
          response:
            tax_rate: 0.0825
            tax_amount: 17.82
            jurisdiction: "Texas State + Austin Local"
          latencyMs: 25
        - id: oregon_no_tax
          match:
            strategy: exact
            path: state
            value: "OR"
          response:
            tax_rate: 0.0
            tax_amount: 0.0
            jurisdiction: "Oregon (No Sales Tax)"
          latencyMs: 25

    calculate_shipping:
      description: Calculates shipping cost based on items and address
      params:
        type: object
        properties:
          item_count:
            type: integer
          delivery_zone:
            type: string
        required:
          - item_count
          - delivery_zone
      cases:
        - id: zone_a_shipping
          match:
            strategy: exact
            path: delivery_zone
            value: "ZONE-A"
          response:
            shipping_method: "Ground"
            shipping_amount: 8.99
            estimated_days: 3
            carrier: "FastShip"
          latencyMs: 25
```

### Documents Server Tools

```yaml
documents:
  transport:
    type: streamable_http
    endpoint: http://stub-mcp:8765/mcp
  tools:
    create_invoice:
      description: Creates formatted invoice document from order data
      params:
        type: object
        properties:
          order_id:
            type: string
          customer_info:
            type: object
          line_items:
            type: array
          totals:
            type: object
        required:
          - order_id
          - totals
      cases:
        - id: standard_invoice
          match:
            strategy: regex
            path: order_id
            value: "ORD-.*"
          response:
            invoice_id: "INV-2025-0042"
            invoice_date: "2025-01-30T10:30:00Z"
            order_id: "ORD-2025-0042"
            status: "generated"
            customer_info:
              customer_id: "CUST-1234"
              name: "Jane Smith"
              billing_address: "123 Main Street, Austin, TX 78701"
            line_items:
              - description: "WIDGET-A"
                quantity: 3
                unit_price: 29.99
                amount: 89.97
              - description: "GADGET-B"
                quantity: 1
                unit_price: 149.99
                amount: 149.99
            totals:
              subtotal: 239.96
              discount: -24.00
              tax: 17.82
              shipping: 8.99
              total: 242.77
            payment_terms: "NET-30"
            due_date: "2025-03-01"
            document_url: "https://docs.example.com/invoices/INV-2025-0042.pdf"
          latencyMs: 150
```

### Regenerate Stub Config

After updating `tools.yaml`, regenerate the stub configuration:

```bash
python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
```

The stub MCP server will hot-reload the new configuration.

---

## Test Execution: User Conversation

### Turn 1: Initial Request

**User Input:**
```
I need to process a new order. Order ID is ORD-2025-0042 from customer CUST-1234.
They ordered 3 WIDGET-A at $29.99 each and 1 GADGET-B at $149.99. Shipping to
123 Main St, Austin, TX 78701. They have a discount code SAVE10.

Please validate the order, calculate the final price, and generate an invoice.
```

**Expected Planner Chain-of-Thought:**
```
The user needs order processing with three distinct steps:
1. Validate order data (customer, inventory, address)
2. Calculate pricing (subtotal, discount, tax, shipping)
3. Generate invoice document

I should discover available skills that match these requirements.
```

**Expected Tool Call — Skill Discovery:**
```json
{
  "tool": "get_skillset",
  "parameters": {
    "query": "validate order calculate pricing generate invoice",
    "tags": ["validation", "pricing", "invoice"]
  }
}
```

**Expected Response:**
```json
{
  "status": "success",
  "skills": [
    {
      "manifest_id": "skill.validate.order@0.1.0",
      "name": "validate.order",
      "description": "Validates order data including customer, inventory, and address verification",
      "tags": ["validation", "order", "testing"]
    },
    {
      "manifest_id": "skill.calculate.pricing@0.1.0",
      "name": "calculate.pricing",
      "description": "Calculates order totals including taxes, discounts, and shipping",
      "tags": ["calculation", "pricing", "testing"]
    },
    {
      "manifest_id": "skill.generate.invoice@0.1.0",
      "name": "generate.invoice",
      "description": "Generates formatted invoice documents from validated and priced orders",
      "tags": ["generation", "invoice", "document", "testing"]
    }
  ]
}
```

### Turn 2: Planner Proposes Workflow

**Planner Response:**
```
I can process this order using a three-step workflow:

1. **Validate Order** — Verify customer CUST-1234, check inventory for WIDGET-A
   and GADGET-B, and validate the Austin, TX shipping address

2. **Calculate Pricing** — Compute subtotal ($239.96), apply SAVE10 discount,
   calculate Texas tax, and determine shipping cost

3. **Generate Invoice** — Create a formatted invoice document with all details

Shall I proceed with this workflow?
```

**User Input:**
```
Yes, proceed.
```

---

## Test Execution: Workflow Compilation

### Planner Compiles ASL Workflow

**Generated Workflow JSON:**

```json
{
  "workflow_schema_version": "2.2.0",
  "workflow_id": "wf-order-proc-001",
  "workflow_name": "Order Processing Pipeline",
  "description": "Validates, prices, and invoices order ORD-2025-0042",
  "version": "1.0.0",
  "created_at": "2025-01-30T10:00:00Z",
  "author": "planner",
  "tags": ["order-processing", "testing", "phase-1"],
  "workflow_input_schema": {
    "type": "object",
    "properties": {
      "order_id": { "type": "string" },
      "customer_id": { "type": "string" },
      "items": { "type": "array" },
      "shipping_address": { "type": "object" },
      "discount_code": { "type": "string" }
    },
    "required": ["order_id", "customer_id", "items", "shipping_address"]
  },
  "af_imports": [
    { "name": "worker", "path": "dcf_mcp/agents/worker.af" }
  ],
  "skill_imports": [
    "skill://validate.order@0.1.0",
    "skill://calculate.pricing@0.1.0",
    "skill://generate.invoice@0.1.0"
  ],
  "asl": {
    "Comment": "Order processing pipeline: validate → price → invoice",
    "StartAt": "ValidateOrder",
    "Version": "1.0",
    "States": {
      "ValidateOrder": {
        "Type": "Task",
        "Comment": "Validate customer, inventory, and shipping address",
        "AgentBinding": {
          "agent_template_ref": { "name": "worker" },
          "skills": ["skill://validate.order@0.1.0"]
        },
        "Parameters": {
          "customer_id.$": "$.customer_id",
          "items.$": "$.items",
          "shipping_address.$": "$.shipping_address"
        },
        "ResultPath": "$.validation",
        "Next": "CalculatePricing"
      },
      "CalculatePricing": {
        "Type": "Task",
        "Comment": "Calculate subtotal, discount, tax, and shipping",
        "AgentBinding": {
          "agent_template_ref": { "name": "worker" },
          "skills": ["skill://calculate.pricing@0.1.0"]
        },
        "Parameters": {
          "items.$": "$.items",
          "discount_code.$": "$.discount_code",
          "shipping_address.$": "$.shipping_address",
          "delivery_zone.$": "$.validation.address_status.delivery_zone"
        },
        "ResultPath": "$.pricing",
        "Next": "GenerateInvoice"
      },
      "GenerateInvoice": {
        "Type": "Task",
        "Comment": "Generate formatted invoice document",
        "AgentBinding": {
          "agent_template_ref": { "name": "worker" },
          "skills": ["skill://generate.invoice@0.1.0"]
        },
        "Parameters": {
          "order_id.$": "$.order_id",
          "customer_info.$": "$.validation.customer_status",
          "line_items.$": "$.pricing.line_items",
          "totals.$": "$.pricing"
        },
        "ResultPath": "$.invoice",
        "End": true
      }
    }
  }
}
```

### Validate Workflow

**Tool Call:**
```json
{
  "tool": "validate_workflow",
  "parameters": {
    "workflow_json": "<workflow above>",
    "resolve_imports": true
  }
}
```

**Expected Response:**
```json
{
  "status": "success",
  "valid": true,
  "errors": [],
  "warnings": [],
  "resolved_skills": [
    "skill.validate.order@0.1.0",
    "skill.calculate.pricing@0.1.0",
    "skill.generate.invoice@0.1.0"
  ],
  "state_count": 3,
  "execution_order": ["ValidateOrder", "CalculatePricing", "GenerateInvoice"]
}
```

### Create Control Plane

**Tool Call:**
```json
{
  "tool": "create_workflow_control_plane",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "workflow_json": "<workflow above>",
    "initial_inputs": {
      "order_id": "ORD-2025-0042",
      "customer_id": "CUST-1234",
      "items": [
        { "sku": "WIDGET-A", "quantity": 3, "unit_price": 29.99 },
        { "sku": "GADGET-B", "quantity": 1, "unit_price": 149.99 }
      ],
      "shipping_address": {
        "street": "123 Main St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701"
      },
      "discount_code": "SAVE10"
    }
  }
}
```

**Redis State Created:**

```
cp:wf:wf-order-proc-001:meta
cp:wf:wf-order-proc-001:state:ValidateOrder      → status: pending
cp:wf:wf-order-proc-001:state:CalculatePricing   → status: pending, blocked
cp:wf:wf-order-proc-001:state:GenerateInvoice    → status: pending, blocked
```

### Create Worker Agents

**Tool Call:**
```json
{
  "tool": "create_worker_agents",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "template_path": "dcf_mcp/agents/worker.af"
  }
}
```

**Expected Response:**
```json
{
  "status": "success",
  "workers_created": [
    {
      "state_name": "ValidateOrder",
      "agent_id": "worker-vo-001",
      "agent_name": "worker-wf-order-proc-001-ValidateOrder"
    },
    {
      "state_name": "CalculatePricing",
      "agent_id": "worker-cp-001",
      "agent_name": "worker-wf-order-proc-001-CalculatePricing"
    },
    {
      "state_name": "GenerateInvoice",
      "agent_id": "worker-gi-001",
      "agent_name": "worker-wf-order-proc-001-GenerateInvoice"
    }
  ]
}
```

---

## Test Execution: Worker Execution

### Trigger Initial State

**Planner Tool Call:**
```json
{
  "tool": "notify_next_worker_agent",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "source_state": null
  }
}
```

---

### Worker 1: ValidateOrder

#### Acquire Lease

```json
{
  "tool": "acquire_state_lease",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "state_name": "ValidateOrder",
    "ttl_seconds": 300
  }
}
```

**Response:** `{ "lease_token": "lease-vo-abc123", "expires_at": "..." }`

#### Load Skill

```json
{
  "tool": "load_skill",
  "parameters": {
    "agent_id": "worker-vo-001",
    "skill_manifest_id": "skill.validate.order@0.1.0"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "skill_loaded": "skill.validate.order@0.1.0",
  "tools_added": ["orders:verify_customer", "orders:check_inventory", "orders:validate_address"],
  "directives_injected": true
}
```

#### Execute Validation Tools

**Tool 1: Verify Customer**
```json
{
  "tool": "orders:verify_customer",
  "parameters": { "customer_id": "CUST-1234" }
}
```

**Stub Response:**
```json
{
  "valid": true,
  "customer_name": "Jane Smith",
  "account_status": "active",
  "credit_limit": 5000.00,
  "current_balance": 250.00
}
```

**Tool 2: Check Inventory**
```json
{
  "tool": "orders:check_inventory",
  "parameters": {
    "items": [
      { "sku": "WIDGET-A", "quantity": 3 },
      { "sku": "GADGET-B", "quantity": 1 }
    ]
  }
}
```

**Stub Response:**
```json
{
  "all_available": true,
  "items": [
    { "sku": "WIDGET-A", "requested": 3, "available": 150, "status": "in_stock" },
    { "sku": "GADGET-B", "requested": 1, "available": 25, "status": "in_stock" }
  ]
}
```

**Tool 3: Validate Address**
```json
{
  "tool": "orders:validate_address",
  "parameters": {
    "address": { "street": "123 Main St", "city": "Austin", "state": "TX", "zip": "78701" }
  }
}
```

**Stub Response:**
```json
{
  "valid": true,
  "normalized_address": {
    "street": "123 Main Street",
    "city": "Austin",
    "state": "TX",
    "zip": "78701-1234"
  },
  "delivery_zone": "ZONE-A",
  "estimated_delivery_days": 3
}
```

#### Write Output

```json
{
  "tool": "update_workflow_control_plane",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "state_name": "ValidateOrder",
    "lease_token": "lease-vo-abc123",
    "status": "done",
    "output_json": {
      "valid": true,
      "customer_status": {
        "valid": true,
        "customer_name": "Jane Smith",
        "account_status": "active"
      },
      "inventory_status": {
        "all_available": true,
        "items": [
          { "sku": "WIDGET-A", "status": "in_stock" },
          { "sku": "GADGET-B", "status": "in_stock" }
        ]
      },
      "address_status": {
        "valid": true,
        "delivery_zone": "ZONE-A",
        "estimated_delivery_days": 3
      },
      "errors": []
    }
  }
}
```

#### Cleanup and Notify

```json
{ "tool": "unload_skill", "parameters": { "agent_id": "worker-vo-001", "skill_manifest_id": "skill.validate.order@0.1.0" } }
{ "tool": "release_state_lease", "parameters": { "workflow_id": "wf-order-proc-001", "state_name": "ValidateOrder", "lease_token": "lease-vo-abc123" } }
{ "tool": "notify_next_worker_agent", "parameters": { "workflow_id": "wf-order-proc-001", "source_state": "ValidateOrder" } }
```

---

### Worker 2: CalculatePricing

*Pattern: acquire lease → load skill → execute tools → write output → cleanup → notify*

#### Execute Pricing Tools

**Tool 1: Calculate Subtotal**
```json
{
  "tool": "pricing:calculate_subtotal",
  "parameters": {
    "items": [
      { "sku": "WIDGET-A", "quantity": 3, "unit_price": 29.99 },
      { "sku": "GADGET-B", "quantity": 1, "unit_price": 149.99 }
    ]
  }
}
```

**Response:** `{ "subtotal": 239.96, "item_count": 4, ... }`

**Tool 2: Apply Discount**
```json
{
  "tool": "pricing:apply_discount",
  "parameters": { "subtotal": 239.96, "discount_code": "SAVE10" }
}
```

**Response:** `{ "discount_applied": true, "discount_amount": 24.00, "subtotal_after_discount": 215.96 }`

**Tool 3: Calculate Tax**
```json
{
  "tool": "pricing:calculate_tax",
  "parameters": { "subtotal": 215.96, "state": "TX" }
}
```

**Response:** `{ "tax_rate": 0.0825, "tax_amount": 17.82 }`

**Tool 4: Calculate Shipping**
```json
{
  "tool": "pricing:calculate_shipping",
  "parameters": { "item_count": 4, "delivery_zone": "ZONE-A" }
}
```

**Response:** `{ "shipping_amount": 8.99, "carrier": "FastShip" }`

#### Write Output

```json
{
  "output_json": {
    "subtotal": 239.96,
    "discount_amount": 24.00,
    "subtotal_after_discount": 215.96,
    "tax_amount": 17.82,
    "shipping_amount": 8.99,
    "total": 242.77,
    "currency": "USD",
    "line_items": [
      { "sku": "WIDGET-A", "quantity": 3, "unit_price": 29.99, "line_total": 89.97 },
      { "sku": "GADGET-B", "quantity": 1, "unit_price": 149.99, "line_total": 149.99 }
    ]
  }
}
```

---

### Worker 3: GenerateInvoice

#### Execute Invoice Generation

```json
{
  "tool": "documents:create_invoice",
  "parameters": {
    "order_id": "ORD-2025-0042",
    "customer_info": { "customer_id": "CUST-1234", "name": "Jane Smith" },
    "line_items": [ ... ],
    "totals": { "subtotal": 239.96, "discount": -24.00, "tax": 17.82, "shipping": 8.99, "total": 242.77 }
  }
}
```

**Stub Response:**
```json
{
  "invoice_id": "INV-2025-0042",
  "invoice_date": "2025-01-30T10:30:00Z",
  "order_id": "ORD-2025-0042",
  "status": "generated",
  "customer_info": {
    "customer_id": "CUST-1234",
    "name": "Jane Smith",
    "billing_address": "123 Main Street, Austin, TX 78701"
  },
  "line_items": [
    { "description": "WIDGET-A", "quantity": 3, "unit_price": 29.99, "amount": 89.97 },
    { "description": "GADGET-B", "quantity": 1, "unit_price": 149.99, "amount": 149.99 }
  ],
  "totals": {
    "subtotal": 239.96,
    "discount": -24.00,
    "tax": 17.82,
    "shipping": 8.99,
    "total": 242.77
  },
  "payment_terms": "NET-30",
  "due_date": "2025-03-01",
  "document_url": "https://docs.example.com/invoices/INV-2025-0042.pdf"
}
```

---

## Test Execution: Result Collection

### Finalize Workflow

**Planner Tool Call:**
```json
{
  "tool": "finalize_workflow",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "delete_worker_agents": true
  }
}
```

**Response:**
```json
{
  "status": "success",
  "workflow_status": "completed",
  "states_completed": 3,
  "states_failed": 0,
  "workers_deleted": 3,
  "audit_record": "dp:wf:wf-order-proc-001:audit:finalize",
  "duration_seconds": 12
}
```

### Present Results to User

**Planner Response:**
```
## Order Processing Complete ✓

**Order ID:** ORD-2025-0042
**Invoice ID:** INV-2025-0042

### Validation Results
- Customer: Jane Smith (CUST-1234) — ✓ Active account
- Inventory: All items in stock — ✓
- Shipping Address: 123 Main Street, Austin, TX 78701-1234 — ✓ Zone A (3-day delivery)

### Pricing Summary
| Item | Qty | Unit Price | Amount |
|------|-----|------------|--------|
| WIDGET-A | 3 | $29.99 | $89.97 |
| GADGET-B | 1 | $149.99 | $149.99 |

| | |
|---|---|
| Subtotal | $239.96 |
| Discount (SAVE10) | -$24.00 |
| Tax (TX 8.25%) | $17.82 |
| Shipping | $8.99 |
| **Total** | **$242.77** |

### Invoice
- Payment Terms: NET-30
- Due Date: March 1, 2025
- Document: https://docs.example.com/invoices/INV-2025-0042.pdf

Workflow completed in 12 seconds.
```

### Persist Audit Trail

**Files written to `workflows/runs/wf-order-proc-001/`:**
```
workflow.json                           # Original workflow definition
summary.json                            # Execution summary
control_plane/
  meta.json                             # Workflow metadata
  states/
    ValidateOrder.json
    CalculatePricing.json
    GenerateInvoice.json
data_plane/
  outputs/
    ValidateOrder.json
    CalculatePricing.json
    GenerateInvoice.json
  audit/
    finalize.json
```

---

## Test Execution: Reflector Analysis

### Register and Trigger Reflector

**Planner Tool Calls:**
```json
{
  "tool": "register_reflector",
  "parameters": {
    "planner_agent_id": "planner-001",
    "reflector_agent_id": "reflector-001"
  }
}
```

```json
{
  "tool": "trigger_reflection",
  "parameters": {
    "workflow_id": "wf-order-proc-001",
    "reflector_agent_id": "reflector-001"
  }
}
```

### Reflector Analysis Flow

#### Step 1: Ingest Workflow Data

Reflector receives `reflection_event` containing:
- Workflow definition
- Execution timeline (12 seconds total)
- All worker outputs
- Success status (3/3 states completed)

#### Step 2: Analyze Patterns

Reflector identifies:

| Observation | Analysis |
|-------------|----------|
| Linear workflow | All states sequential; no parallelization |
| Skill success rate | 3/3 skills executed without error |
| Execution efficiency | 12 seconds total, reasonable for 3 states |
| Data flow | Clean handoff between states via ResultPath |

#### Step 3: Generate Insights

```json
{
  "insights": [
    {
      "type": "workflow_optimization",
      "observation": "ValidateOrder executes 3 independent tool calls sequentially",
      "recommendation": "Consider parallel tool execution within validate.order skill",
      "impact": "Potential 40% reduction in validation time",
      "confidence": 0.78
    },
    {
      "type": "skill_effectiveness",
      "skill": "validate.order",
      "success_rate": 1.0,
      "avg_duration_ms": 225,
      "quality_notes": "Comprehensive validation with clear error reporting"
    },
    {
      "type": "skill_effectiveness",
      "skill": "calculate.pricing",
      "success_rate": 1.0,
      "avg_duration_ms": 100,
      "quality_notes": "Accurate calculations, good discount handling"
    },
    {
      "type": "skill_effectiveness",
      "skill": "generate.invoice",
      "success_rate": 1.0,
      "avg_duration_ms": 150,
      "quality_notes": "Complete invoice with proper formatting"
    },
    {
      "type": "pattern_recognition",
      "pattern": "order-processing-pipeline",
      "description": "validate → calculate → generate sequence",
      "recommendation": "Consider creating reusable workflow template"
    }
  ]
}
```

#### Step 4: Persist to Graphiti

```json
{
  "tool": "graphiti:add_episode",
  "parameters": {
    "episode_type": "WorkflowExecution",
    "data": {
      "workflow_id": "wf-order-proc-001",
      "workflow_name": "Order Processing Pipeline",
      "status": "completed",
      "duration_seconds": 12,
      "state_count": 3,
      "skills_used": ["validate.order@0.1.0", "calculate.pricing@0.1.0", "generate.invoice@0.1.0"],
      "success": true,
      "timestamp": "2025-01-30T10:30:15Z"
    }
  }
}
```

```json
{
  "tool": "graphiti:add_episode",
  "parameters": {
    "episode_type": "LearningInsight",
    "data": {
      "insight_type": "workflow_optimization",
      "source_workflow": "wf-order-proc-001",
      "recommendation": "Consider parallel tool execution within validate.order skill",
      "confidence": 0.78,
      "timestamp": "2025-01-30T10:30:20Z"
    }
  }
}
```

#### Step 5: Publish Guidelines

```json
{
  "tool": "update_reflector_guidelines",
  "parameters": {
    "planner_agent_id": "planner-001",
    "guidelines": {
      "skill_preferences": [
        {
          "skill": "validate.order@0.1.0",
          "rating": "preferred",
          "notes": "Reliable, comprehensive validation"
        },
        {
          "skill": "calculate.pricing@0.1.0",
          "rating": "preferred",
          "notes": "Accurate, handles discounts well"
        },
        {
          "skill": "generate.invoice@0.1.0",
          "rating": "preferred",
          "notes": "Complete output with document URL"
        }
      ],
      "workflow_patterns": [
        {
          "name": "order-processing",
          "template": ["validate.*", "calculate.*", "generate.*"],
          "recommendation": "Consider as reusable template for similar tasks"
        }
      ],
      "optimization_hints": [
        {
          "context": "validation_with_multiple_checks",
          "hint": "Three independent checks can run in parallel"
        }
      ],
      "updated_at": "2025-01-30T10:30:25Z"
    }
  }
}
```

### Verification: Planner Reads Guidelines

On next workflow planning, Planner checks guidelines:

```json
{
  "tool": "read_shared_memory_blocks",
  "parameters": {
    "agent_id": "planner-001",
    "block_names": ["reflector_guidelines"]
  }
}
```

---

## Verification Checklist

### Pre-Execution Checks

| Check | Command | Expected |
|-------|---------|----------|
| Services healthy | See Prerequisites section | All services responding |
| Skills exist | `ls generated/manifests/skill.validate.order*` | 3 manifest files |
| Stub config updated | `cat generated/stub/stub_config.json \| grep orders` | orders tools present |

### During Execution Checks

| Check | Command | Expected |
|-------|---------|----------|
| Control plane created | `redis-cli keys "cp:wf:wf-order-proc-001:*"` | 4 keys (meta + 3 states) |
| Workers exist | `curl localhost:8283/v1/agents \| jq '.[].name'` | 3 worker agents |
| State transitions | `redis-cli JSON.GET cp:wf:wf-order-proc-001:state:ValidateOrder` | `status: "done"` after completion |

### Post-Execution Checks

| Check | Verification | Expected |
|-------|--------------|----------|
| Workflow completed | `finalize_workflow` response | `workflow_status: "completed"` |
| Workers cleaned up | Agent list query | No worker agents remain |
| Audit trail | `ls workflows/runs/wf-order-proc-001/` | All files present |
| Graphiti episode | Query Graphiti | WorkflowExecution episode exists |
| Guidelines published | Read Planner memory | `reflector_guidelines` populated |

### Expected Final State

```
Redis Keys:
  cp:wf:wf-order-proc-001:meta          → status: completed
  cp:wf:wf-order-proc-001:state:*       → all status: done
  dp:wf:wf-order-proc-001:output:*      → output data present
  dp:wf:wf-order-proc-001:audit:finalize → finalization record

Letta Agents:
  planner-001                           → exists, guidelines block updated
  reflector-001                         → exists
  worker-*                              → deleted (cleanup successful)

Graphiti:
  WorkflowExecution episode             → wf-order-proc-001
  LearningInsight episode               → parallel execution hint
  SkillMetric episodes                  → 3 skills tracked

Files:
  workflows/runs/wf-order-proc-001/     → complete audit trail
```

---

## Cleanup

To reset the test environment for re-execution:

```bash
# Clear workflow data from Redis
redis-cli keys "cp:wf:wf-order-proc-001:*" | xargs redis-cli del
redis-cli keys "dp:wf:wf-order-proc-001:*" | xargs redis-cli del

# Remove audit trail
rm -rf workflows/runs/wf-order-proc-001/

# Clear Graphiti test data (optional)
# Use Graphiti admin tools to delete test episodes

# Restart services if needed
docker compose restart
```

---

## Summary

This Phase 1 testing plan validates the complete workflow execution lifecycle:

| Phase | Components Tested |
|-------|-------------------|
| **Conversation** | Planner ↔ User dialogue, intent understanding |
| **Discovery** | `get_skillset` returns matching skills |
| **Compilation** | ASL workflow generation with AgentBinding |
| **Validation** | Schema validation, import resolution |
| **Control Plane** | Redis state management, dependency tracking |
| **Worker Execution** | Lease coordination, skill loading, tool execution |
| **Data Flow** | ResultPath handoff between states |
| **Finalization** | Cleanup, audit trail, result presentation |
| **Reflection** | Pattern analysis, Graphiti persistence, guideline publishing |

**Skills Tested:**
- `validate.order@0.1.0` — Customer, inventory, address verification
- `calculate.pricing@0.1.0` — Subtotal, discount, tax, shipping calculation
- `generate.invoice@0.1.0` — Invoice document generation

**Tools Tested (via Stub MCP):**
- `orders:verify_customer`, `orders:check_inventory`, `orders:validate_address`
- `pricing:calculate_subtotal`, `pricing:apply_discount`, `pricing:calculate_tax`, `pricing:calculate_shipping`
- `documents:create_invoice`
