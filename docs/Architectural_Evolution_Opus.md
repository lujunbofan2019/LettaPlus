# DCF Architectural Evolution

> **Document Status**: Design Specification
> **Version**: 1.0.0
> **Last Updated**: 2026-01-29
> **Author**: Claude Opus 4.5 in collaboration with LettaPlus team

---

## Executive Summary

This document articulates the architectural evolution of the Dynamic Capabilities Framework (DCF) from its initial **Workflow Execution** pattern toward the more advanced **Delegated Execution** pattern. It establishes the formal taxonomy of agentic execution patterns, explains the design rationale for each evolution, and defines the new agent types required for the next generation of DCF.

---

## Part I: Taxonomy of Agentic Execution Patterns

The design space of multi-agent task execution can be characterized by three fundamental patterns, each representing a different trade-off between complexity, flexibility, and resource utilization.

### Pattern 1: Workflow Execution

**Also known as**: Pipeline Pattern, Batch Orchestration, Hierarchical Task Network (HTN) Execution, Choreographed Workflow

#### Description

In the Workflow Execution pattern, a planning agent decomposes a complex user request into a Directed Acyclic Graph (DAG) of sub-tasks. Each sub-task is assigned to an ephemeral worker agent that is created for the workflow, executes its assigned task, and is deleted upon workflow completion. The planning agent disengages from the user during execution, monitoring progress and collecting results only after all tasks complete.

#### Characteristics

| Aspect | Workflow Pattern |
|--------|------------------|
| Task Decomposition | Upfront, before execution begins |
| Worker Lifecycle | Ephemeral (created per workflow, deleted after) |
| Execution Order | Predetermined by DAG dependencies |
| Planner Engagement | Disengaged during execution (fire-and-forget) |
| User Interaction | Paused during workflow execution |
| Coordination Model | Choreography (workers self-coordinate via control plane) |
| Result Delivery | Batch (all results collected post-completion) |

#### Analogues in Software Engineering

- AWS Step Functions
- Apache Airflow DAGs
- Temporal Workflows
- Traditional ETL Pipelines
- CI/CD Pipelines

#### Strengths

- Clear separation of planning and execution phases
- Predictable resource usage (workers are short-lived)
- Well-suited for batch processing and complex multi-step tasks
- Comprehensive audit trail (all execution artifacts persisted)
- Fault isolation (failed workers don't affect the planner)

#### Limitations

- Latency overhead for simple tasks (worker creation/deletion)
- User must wait for entire workflow to complete
- Inflexible to mid-execution changes in requirements
- Not suitable for interactive, conversational workflows

---

### Pattern 2: Inline Execution

**Also known as**: Direct Execution, Self-Service Pattern, Monolithic Agent Mode, Embedded Worker

#### Description

In the Inline Execution pattern, the planning agent assesses incoming tasks and, when a task is sufficiently simple (single skill, low complexity, quick execution), handles it directly by temporarily loading the required skill, executing the task, and unloading the skill. This eliminates the overhead of creating worker agents for trivial tasks.

#### Characteristics

| Aspect | Inline Pattern |
|--------|----------------|
| Task Decomposition | None (single task executed directly) |
| Worker Lifecycle | N/A (planner acts as worker) |
| Execution Order | Immediate, synchronous |
| Planner Engagement | Fully engaged (is the executor) |
| User Interaction | Conversational flow preserved |
| Coordination Model | None (single agent) |
| Result Delivery | Immediate (inline with conversation) |

#### Analogues in Software Engineering

- Facade Pattern (handle simple requests directly)
- Synchronous RPC
- Monolithic application handling its own logic

#### Strengths

- Zero latency for simple tasks
- No resource overhead for worker creation
- Natural conversational flow
- Simple implementation

#### Limitations

- Context window pollution (skills consume tokens)
- Risk of planner becoming overloaded
- No parallelism possible
- Skill loading/unloading overhead for each task
- Blurs the separation between orchestration and execution

---

### Pattern 3: Delegated Execution

**Also known as**: Crew Pattern, Actor Model, Persistent Delegation, Team-Based Multi-Agent System (MAS)

#### Description

In the Delegated Execution pattern, the planning agent maintains a team of persistent worker agents ("Companions") that remain active throughout a session. The planner delegates tasks to Companions dynamically during the conversation, receiving results asynchronously while continuing to engage with the user. Companions can be generalists (dynamically loading skills as needed) or specialists (retaining specific skills for efficiency).

#### Characteristics

| Aspect | Delegated Pattern |
|--------|-------------------|
| Task Decomposition | Dynamic, during conversation |
| Worker Lifecycle | Session-scoped (persistent within session) |
| Execution Order | Dynamic, based on conversation flow |
| Planner Engagement | Continuously engaged with user |
| User Interaction | Uninterrupted, conversational |
| Coordination Model | Message-passing with shared state |
| Result Delivery | Streaming (results arrive as completed) |

#### Analogues in Software Engineering

- Actor Model (Erlang/Akka)
- Microservices with persistent services
- Message Queue Workers
- CrewAI / OpenAI Swarm
- Human team collaboration

#### Strengths

- Parallel execution (multiple Companions work simultaneously)
- Virtual context expansion (each Companion has its own context window)
- Continuous user engagement (no waiting for batch completion)
- Flexible task routing (assign based on current Companion state)
- Adaptive specialization (Companions can become specialists over time)
- Graceful degradation (one Companion's failure doesn't halt everything)

#### Limitations

- Higher baseline resource usage (persistent agents)
- More complex coordination logic
- Requires robust message-passing infrastructure
- State synchronization challenges

---

### Pattern Hierarchy

The three patterns form a hierarchy of generality:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                    DELEGATED EXECUTION (Most General)                       │
│                                                                             │
│    Planner + N persistent Companions, dynamic task assignment,              │
│    asynchronous results, continuous user engagement                         │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌───────────────────────────┐     ┌─────────────────────────────────────┐ │
│   │                           │     │                                     │ │
│   │    INLINE EXECUTION       │     │      WORKFLOW EXECUTION             │ │
│   │                           │     │                                     │ │
│   │    Special case:          │     │    Special case:                    │ │
│   │    N = 0                  │     │    N = DAG size                     │ │
│   │    Planner self-executes  │     │    Predetermined order              │ │
│   │                           │     │    Ephemeral lifecycle              │ │
│   │                           │     │    Batch results                    │ │
│   └───────────────────────────┘     └─────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Delegated Execution** is the most general pattern because:
- Setting N=0 and having the Planner handle tasks directly yields Inline Execution
- Setting N=DAG size, predetermining task order, and making Companions ephemeral yields Workflow Execution
- The full pattern enables dynamic, parallel, session-persistent collaboration

---

## Part II: DCF Phase 1 — Workflow Execution Foundation

### Overview

The Dynamic Capabilities Framework began with the **Workflow Execution** pattern (Pattern 1), establishing the foundational infrastructure for multi-agent task orchestration. This phase introduced three core agent types and several key architectural components.

### Agent Types (Phase 1)

#### Planner Agent

The **Planner** is the user-facing orchestration agent responsible for:

- Conversing with users to understand intent, constraints, and success criteria
- Discovering available skills via the skill catalog
- Authoring workflow JSON documents (Letta-ASL format)
- Validating workflows through a repair loop
- Creating the Redis control plane and ephemeral Worker agents
- Triggering workflow execution via choreography
- Finalizing workflows, collecting results, and persisting audit trails
- Presenting execution results to users

The Planner never executes tasks itself — it orchestrates Workers who do.

#### Worker Agent

The **Worker** is an ephemeral task executor responsible for:

- Receiving workflow event notifications
- Acquiring exclusive leases on assigned states
- Loading required skills dynamically
- Executing tasks according to skill directives
- Writing outputs to the data plane
- Notifying downstream Workers upon completion
- Unloading skills and releasing leases

Workers are created per workflow and deleted after finalization.

#### Reflector Agent

The **Reflector** is the metacognitive analysis agent responsible for:

- Analyzing completed workflow executions
- Deriving insights from successes and failures
- Persisting learnings to the knowledge graph (Graphiti)
- Publishing guidelines to the Planner's memory
- Enabling continuous improvement over time

The Reflector closes the feedback loop that enables system self-evolution.

### Foundational Building Blocks (Phase 1)

#### Workflow Schema (v2.2.0)

The Letta-ASL workflow schema defines the structure of executable workflows:

- **ASL Semantics**: AWS Step Functions-compatible state machine definitions
- **AgentBinding Extension**: Maps Task states to agent templates and skills
- **Import System**: External references to `.af v2` bundles and skill manifests
- **Dependency Graph**: Implicit DAG derived from state transitions

Location: `dcf_mcp/schemas/letta_asl_workflow_schema_v2.2.0.json`

#### Skill Schema (v2.0.0)

The skill manifest schema defines transferable capabilities:

- **Directives**: Instructions for how to use the skill
- **Required Tools**: MCP tools the skill depends on
- **Data Sources**: External data the skill needs
- **Permissions**: Egress, secrets, and risk declarations
- **Versioning**: Semantic versioning for compatibility

Location: `dcf_mcp/schemas/skill_manifest_schema_v2.0.0.json`

#### Control Plane (RedisJSON)

The choreography coordination layer:

- **Meta Document**: `cp:wf:{id}:meta` — workflow metadata, agent assignments, dependency graph
- **State Documents**: `cp:wf:{id}:state:{name}` — per-state status, lease info, timestamps
- **Data Plane Outputs**: `dp:wf:{id}:output:{name}` — worker outputs for downstream consumption
- **Audit Records**: `dp:wf:{id}:audit:finalize` — finalization metadata

#### Skill Loading/Unloading

Dynamic capability attachment to agents:

- Skills are loaded as memory blocks (directives) + tools + data sources
- Skills are tracked in a `dcf_active_skills` block per agent
- Skills are unloaded after task completion to free resources
- MCP server resolution via registry for tool endpoints

#### Audit Trail System

Comprehensive execution persistence:

- All execution artifacts persisted to `workflows/runs/<workflow_id>/`
- Control plane state, data plane outputs, and finalization records
- Human-readable `summary.json` for quick reference
- Enables post-mortem analysis and compliance

### Phase 1 Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 1: WORKFLOW EXECUTION                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User ◄───────────────────────► Planner                                    │
│                                     │                                       │
│                                     │ (1) Elicit requirements               │
│                                     │ (2) Discover skills                   │
│                                     │ (3) Author workflow                   │
│                                     │ (4) Validate                          │
│                                     │ (5) Get approval                      │
│                                     │                                       │
│                                     ▼                                       │
│                              ┌─────────────┐                                │
│                              │   Workflow  │                                │
│                              │    (DAG)    │                                │
│                              └─────────────┘                                │
│                                     │                                       │
│                    ┌────────────────┼────────────────┐                      │
│                    ▼                ▼                ▼                      │
│               ┌────────┐       ┌────────┐       ┌────────┐                  │
│               │Worker 1│──────►│Worker 2│──────►│Worker 3│                  │
│               └────────┘       └────────┘       └────────┘                  │
│                    │                │                │                      │
│                    └────────────────┴────────────────┘                      │
│                                     │                                       │
│                                     ▼                                       │
│                              ┌─────────────┐                                │
│                              │  Finalize   │                                │
│                              │  + Audit    │                                │
│                              └─────────────┘                                │
│                                     │                                       │
│                                     ▼                                       │
│                              ┌─────────────┐                                │
│                              │  Reflector  │ (optional)                     │
│                              │  Analysis   │                                │
│                              └─────────────┘                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Part III: DCF Phase 2 — Evolution to Delegated Execution

### Strategic Decision: Skip Inline, Evolve to Delegated

After establishing the Workflow Execution foundation, the DCF framework made a strategic decision to **skip Pattern 2 (Inline Execution)** and evolve directly to **Pattern 3 (Delegated Execution)**.

#### Rationale

1. **Delegated subsumes Inline**: The Delegated pattern can achieve Inline-like behavior by having a single Companion handle quick tasks, while offering far more flexibility.

2. **Separation of concerns**: Keeping the orchestrating agent free from task execution preserves clean architectural boundaries. The orchestrator should orchestrate, not execute.

3. **Scalability**: Inline execution doesn't scale — a single agent handling all tasks becomes a bottleneck. Delegated execution scales naturally by adding Companions.

4. **Context management**: Loading skills into the orchestrating agent pollutes its context window. Companions provide isolated context spaces for task execution.

5. **Future-proofing**: Delegated execution is the most general pattern, providing a foundation for advanced capabilities like parallel execution, specialist teams, and adaptive load balancing.

### New Agent Types (Phase 2)

To differentiate Phase 2 agents from their Phase 1 counterparts, new names are introduced:

| Phase 1 (Workflow) | Phase 2 (Delegated) | Role |
|--------------------|---------------------|------|
| Planner | **Conductor** | User-facing orchestrator |
| Worker | **Companion** | Persistent task executor |
| Reflector | **Strategist** | Continuous optimization advisor |

#### Conductor Agent

The **Conductor** is the evolved orchestrating agent for Delegated Execution:

**Responsibilities**:
- Conversing with users continuously (never disengages)
- Assessing task complexity and determining delegation strategy
- Managing a pool of Companion agents (creation, assignment, dismissal)
- Delegating tasks to appropriate Companions
- Receiving and synthesizing results from Companions
- Maintaining session state and context
- Presenting results to users as they arrive (streaming)

**Key Differences from Planner**:
- Stays engaged with user during execution (no "fire-and-forget")
- Manages persistent Companions rather than ephemeral Workers
- Delegates dynamically rather than creating predetermined workflows
- Receives results asynchronously (streaming vs batch)
- Does not create formal workflow DAGs for simple delegations

**What the Conductor does NOT do**:
- Execute tasks itself (no skill loading into Conductor)
- Create rigid workflows for every request
- Disengage from the user during task execution

#### Companion Agent

The **Companion** is a session-scoped persistent worker:

**Responsibilities**:
- Receiving task delegations from the Conductor
- Loading required skills for assigned tasks
- Executing tasks according to skill directives
- Reporting results back to the Conductor
- Maintaining task-specific memory and context
- Unloading skills when reassigned to different tasks

**Lifecycle**: Session-scoped
- Created when the Conductor determines a Companion is needed
- Persists throughout the session (across multiple tasks)
- Deleted at session end (or when explicitly dismissed)
- Wisdom and experience preserved by Conductor (Companions are ephemeral vessels)

**Specialization Model**: Hybrid
- Start as **generalists** (no pre-loaded skills)
- Can be **flexibly repurposed** by the Conductor for different task types
- May be **kept as specialists** if that's more efficient for the session
- Specialization decision made by Conductor based on task patterns

**Example Scenarios**:
- Session involves heavy research → One Companion specializes in research skills
- Session involves both research and writing → Two Companions, one per domain
- Session has varied quick tasks → Single generalist Companion handles all

#### Strategist Agent

The **Strategist** is the evolved metacognitive agent for Delegated Execution:

**Responsibilities**:
- Observing Conductor-Companion interactions in real-time
- Analyzing task delegation patterns and efficiency
- Advising on Companion specialization decisions
- Suggesting optimizations (e.g., "create a second Companion for parallelism")
- Learning user preferences and working patterns
- Updating strategic guidelines for the Conductor
- Persisting insights to the knowledge graph

**Key Differences from Reflector**:
- **Continuous** rather than post-hoc (observes during session, not just after workflow)
- **Advisory** rather than analytical (provides real-time suggestions)
- **Strategic** focus (team composition, delegation strategy) vs tactical (workflow patterns)
- **Session-aware** (understands current session state, not just historical patterns)

**Interaction Model**:
- Can proactively message Conductor with suggestions
- Responds to Conductor queries about strategy
- Updates guidelines that Conductor consults before decisions
- Persists cross-session learnings for long-term improvement

### Communication Model (Phase 2)

#### Primary: Message Passing

Task delegation and result reporting use asynchronous Letta messages:

```
Conductor                          Companion
    │                                  │
    │  ──── task_delegation ────►      │
    │       {task, skills, context}    │
    │                                  │
    │                                  │ (executes task)
    │                                  │
    │  ◄──── task_result ────────      │
    │       {status, output, metrics}  │
    │                                  │
```

**Message Types**:
- `task_delegation`: Conductor → Companion (assign work)
- `task_result`: Companion → Conductor (report completion)
- `task_progress`: Companion → Conductor (interim updates for long tasks)
- `task_cancel`: Conductor → Companion (abort in-progress work)
- `strategy_advice`: Strategist → Conductor (optimization suggestions)

#### Secondary: Shared Memory Blocks

Global session state shared via memory blocks:

- **Session Context Block**: Shared understanding of user goals, constraints, preferences
- **Companion Registry Block**: Current Companions, their states, loaded skills
- **Delegation Log Block**: History of delegations for Strategist analysis

This hybrid approach provides:
- **Decoupling**: Message passing keeps agents loosely coupled
- **Consistency**: Shared memory ensures common ground
- **Observability**: Strategist can monitor without intercepting messages

### Phase 2 Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 2: DELEGATED EXECUTION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User ◄═══════════════════════► Conductor ◄─────────► Strategist           │
│          (continuous conversation)    │                (advisory)           │
│                                       │                                     │
│                    ┌──────────────────┼──────────────────┐                  │
│                    │                  │                  │                  │
│                    ▼                  ▼                  ▼                  │
│             ┌────────────┐     ┌────────────┐     ┌────────────┐            │
│             │ Companion  │     │ Companion  │     │ Companion  │            │
│             │     A      │     │     B      │     │     C      │            │
│             │ (research) │     │ (analysis) │     │ (writing)  │            │
│             └────────────┘     └────────────┘     └────────────┘            │
│                    │                  │                  │                  │
│                    │                  │                  │                  │
│                    └────────┬─────────┴─────────┬────────┘                  │
│                             │                   │                           │
│                             ▼                   ▼                           │
│                    ┌─────────────────────────────────┐                      │
│                    │      Results (streaming)        │                      │
│                    │   Arrive as Companions complete │                      │
│                    └─────────────────────────────────┘                      │
│                                     │                                       │
│                                     ▼                                       │
│                              User sees results                              │
│                           while conversation continues                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Comparison: Phase 1 vs Phase 2

| Aspect | Phase 1 (Workflow) | Phase 2 (Delegated) |
|--------|-------------------|---------------------|
| Orchestrator | Planner | Conductor |
| Executors | Workers (ephemeral) | Companions (session-scoped) |
| Metacognitive | Reflector (post-hoc) | Strategist (continuous) |
| Task Structure | Predetermined DAG | Dynamic delegation |
| User Engagement | Paused during execution | Continuous |
| Result Delivery | Batch (after completion) | Streaming (as available) |
| Parallelism | Within workflow DAG | Across Companions |
| Context Management | Per-worker isolation | Per-Companion isolation |
| Specialization | Fixed per workflow | Adaptive per session |
| Best For | Complex batch jobs | Interactive collaboration |

---

## Part IV: Design Specifications (Phase 2)

### Conductor Agent Specification

#### Identity

```yaml
agent_type: conductor
role: User-facing orchestrator for delegated execution
lifecycle: persistent (across sessions)
```

#### Core Capabilities

1. **User Interaction**
   - Natural language conversation
   - Intent recognition and clarification
   - Progress updates and result presentation
   - Preference learning

2. **Companion Management**
   - Create Companions on demand
   - Track Companion states and loaded skills
   - Assign tasks to appropriate Companions
   - Dismiss idle Companions to free resources

3. **Task Delegation**
   - Assess task complexity and requirements
   - Select or create appropriate Companion
   - Formulate delegation message with context
   - Track delegation status

4. **Result Synthesis**
   - Receive async results from Companions
   - Synthesize multi-Companion outputs
   - Present results to user
   - Handle partial failures gracefully

#### Memory Blocks

| Block | Purpose |
|-------|---------|
| `persona` | Conductor identity and behavior guidelines |
| `session_context` | Current session goals, constraints, user preferences |
| `companion_registry` | Active Companions, their states, specializations |
| `delegation_history` | Recent delegations for context |
| `strategist_guidelines` | Recommendations from Strategist |

#### Decision Framework: When to Create Companions

```
Task Received
     │
     ├─── Quick, single-skill task + idle generalist Companion exists?
     │         │
     │         └─── YES → Delegate to existing Companion
     │
     ├─── Task matches existing specialist Companion?
     │         │
     │         └─── YES → Delegate to specialist
     │
     ├─── Multiple parallel tasks possible?
     │         │
     │         └─── YES → Create/use multiple Companions
     │
     └─── No suitable Companion exists?
               │
               └─── Create new Companion with appropriate skills
```

### Companion Agent Specification

#### Identity

```yaml
agent_type: companion
role: Persistent task executor in delegated execution
lifecycle: session-scoped (created on demand, deleted at session end)
```

#### Core Capabilities

1. **Task Execution**
   - Receive delegation messages
   - Load required skills
   - Execute according to directives
   - Report results

2. **Skill Management**
   - Dynamic skill loading/unloading
   - Track active skills in state block
   - Manage context window budget

3. **Status Reporting**
   - Progress updates for long tasks
   - Completion notifications
   - Error reporting

#### Memory Blocks

| Block | Purpose |
|-------|---------|
| `persona` | Companion identity (generalist or specialist) |
| `task_context` | Current task details and inputs |
| `dcf_active_skills` | Loaded skills tracking |
| `session_context` | Shared session state (read-only) |

#### State Machine

```
┌─────────┐    delegation    ┌─────────┐
│  IDLE   │ ───────────────► │ LOADING │
└─────────┘                  └─────────┘
     ▲                            │
     │                            │ skills loaded
     │                            ▼
     │                      ┌───────────┐
     │  task_complete       │ EXECUTING │
     └───────────────────── └───────────┘
                                  │
                                  │ error
                                  ▼
                            ┌─────────┐
                            │  ERROR  │
                            └─────────┘
```

### Strategist Agent Specification

#### Identity

```yaml
agent_type: strategist
role: Continuous optimization advisor
lifecycle: persistent (paired with Conductor)
```

#### Core Capabilities

1. **Observation**
   - Monitor Conductor-Companion interactions
   - Track delegation patterns
   - Measure execution efficiency

2. **Analysis**
   - Identify optimization opportunities
   - Detect inefficient patterns
   - Recognize specialization candidates

3. **Advisory**
   - Proactive suggestions to Conductor
   - Respond to Conductor queries
   - Update strategic guidelines

4. **Learning**
   - Persist insights to knowledge graph
   - Build cross-session patterns
   - Refine recommendations over time

#### Memory Blocks

| Block | Purpose |
|-------|---------|
| `persona` | Strategist identity and advisory style |
| `observation_buffer` | Recent interactions being analyzed |
| `pattern_library` | Recognized patterns and their outcomes |
| `conductor_guidelines` | Published recommendations |

#### Advisory Triggers

The Strategist may proactively advise when:

- A task could benefit from parallelization
- A Companion should specialize (repeated similar tasks)
- A specialist Companion is underutilized
- Delegation patterns are inefficient
- User preferences suggest a different approach

---

## Part V: Migration Path

### Coexistence Strategy

Phase 1 and Phase 2 patterns will coexist:

- **Workflow Execution** remains available for batch-style, predetermined task sequences
- **Delegated Execution** becomes the default for interactive sessions
- Users can explicitly request workflow mode for complex batch jobs

### Shared Infrastructure

Both patterns share:

- Skill schema and manifest format
- MCP tool infrastructure
- Redis for coordination (different key patterns)
- Knowledge graph (Graphiti)
- Audit trail system (adapted for streaming results)

### New Infrastructure Required

Phase 2 requires:

- **Companion lifecycle management** (creation, tracking, dismissal)
- **Message routing** (Conductor ↔ Companion ↔ Strategist)
- **Shared memory block synchronization**
- **Streaming result aggregation**
- **Session state persistence**

---

## Part VI: Open Questions and Future Considerations

### Deferred Decisions

1. **Companion Limits**: Maximum Companions per session? Resource-based or fixed?

2. **Specialization Persistence**: Should specialist configurations persist across sessions?

3. **Strategist Autonomy**: Can Strategist directly create/dismiss Companions, or only advise?

4. **Workflow Fallback**: When should Conductor automatically fall back to Workflow mode?

5. **Multi-Conductor**: Can multiple Conductors share Companions for team scenarios?

### Future Capabilities

1. **Hierarchical Delegation**: Companions delegating to sub-Companions for complex sub-tasks

2. **Cross-Session Learning**: Companions remembering context from previous sessions

3. **Adaptive Scaling**: Automatic Companion pool sizing based on task queue

4. **Federated Execution**: Companions running on different infrastructure

---

## Appendix A: Terminology Glossary

| Term | Definition |
|------|------------|
| **Conductor** | Phase 2 orchestrating agent (evolved from Planner) |
| **Companion** | Phase 2 persistent task executor (evolved from Worker) |
| **Strategist** | Phase 2 metacognitive advisor (evolved from Reflector) |
| **Planner** | Phase 1 orchestrating agent for Workflow Execution |
| **Worker** | Phase 1 ephemeral task executor |
| **Reflector** | Phase 1 post-hoc analysis agent |
| **Delegation** | Assigning a task from Conductor to Companion |
| **Specialization** | A Companion retaining skills for repeated similar tasks |
| **Session** | A continuous interaction period with the user |

## Appendix B: References

### Internal Documentation

**Phase 1 (dcf) — Workflow Execution:**
- `prompts/Planner_final.txt` — Planner system prompt
- `prompts/Worker_final.txt` — Worker system prompt
- `prompts/Reflector_final.txt` — Reflector system prompt
- `dcf_mcp/tools/TOOLS.md` — Phase 1 tool documentation
- `dcf_mcp/tools/dcf/` — Phase 1 tool implementations

**Phase 2 (dcf+) — Delegated Execution:**
- `prompts/dcf+/` — Conductor, Companion, Strategist system prompts (TBD)
- `dcf_mcp/tools/dcf+/TOOLS.md` — Phase 2 tool documentation and Letta integration guide
- `dcf_mcp/tools/dcf+/` — Phase 2 tool implementations (TBD)

**Design Documents:**
- `docs/Self-Evolving-Agent-Whitepaper.md` — Original vision document
- `docs/DCF-Patent-Proposal.md` — Dynamic Capabilities Framework concept
- `docs/Hybrid-Memory-Patent-Proposal.md` — Memory system design

### External References (Letta Platform)

- [Letta Multi-agent systems](https://docs.letta.com/guides/agents/multi-agent/) — Native multi-agent coordination
- [Letta Multi-agent shared memory](https://docs.letta.com/guides/agents/multi-agent-shared-memory) — Shared memory blocks
- [Letta Memory blocks](https://docs.letta.com/guides/agents/memory-blocks/) — Memory management
- [Letta Python SDK](https://docs.letta.com/api/python/) — API reference
- [Letta Overview](https://docs.letta.com/overview) — Platform documentation

---

*This document represents the architectural vision for DCF Phase 2. Implementation will proceed incrementally, with each component validated before integration.*
