# Advice Call Analysis End-to-End Worked Example

## 1. Introduction

This document provides a **worked example** that demonstrates how the Letta-based Planner and Worker agents deliver Selina Finance's *Advice Call Analysis* quality-assurance workflow. It narrates the full lifecycle across planning, capability discovery, skill orchestration, hybrid memory usage, and iterative improvement. Each phase is illustrated with representative artifacts - conversation turns, chain-of-thought (CoT) excerpts, workflow JSON, tool calls, memory updates, and knowledge-graph mutations.

### 1.1. The Business Use Case: Advice Call Analysis

As a financial services provider regulated by the Financial Conduct Authority (FCA), Selina Finance has a critical duty to ensure all customer interactions meet rigorous compliance and quality standards. Our advisors and case managers handle numerous phone calls daily, which are recorded for quality assurance (QA) and training purposes.

The traditional process involves line managers or compliance staff manually listening to hours of call recordings (`.mp3` files) to:

- Assess the performance of newly onboarded advisors.
- Verify that new financial products are being explained correctly and consistently.
- Ensure adherence to FCA regulations like Mandatory Disclosures and Consumer Duty.

This manual approach is incredibly time-consuming, difficult to scale, and prone to human inconsistency. The goal is to automate this entire process using an autonomous AI agent that can understand a user's analytical goal and execute the necessary steps to achieve it.

### 1.2. The AI-Powered Solution

Our system addresses this challenge with a **Planner Agent** that can leverage a rich ecosystem of version-controlled **Skills**. These skills provide the agent with the capabilities needed to perform the analysis, including:

- **Salesforce Integration:** To query customer, application, and staff data.
- **Recording Management:** To retrieve specific call recordings from cloud storage.
- **Transcription:** To convert audio files to text (with alternative backends like Whisper and AssemblyAI).
- **Diarization:** To identify and separate speakers in a conversation.
- **Labelling & Segmentation:** To categorize parts of a conversation (e.g., "Introduction," "Product Detail").
- **Sentiment Analysis:** To detect a customer's emotional state.
- **Compliance Analysis:** To evaluate a transcript against a set of compliance rules from a vector store.
- **Scoring:** To calculate an overall quality score based on a dynamic formula.

### 1.3. The System Diagram

[TODO: Lu will add the diagram and descriptions, AI assistant please ignore]

### 1.4. Scenarios to be Demonstrated

This document will walk through three key scenarios to illustrate the system's core features:

1. **Initial Capability Creation.** We will show how the Planner agent interacts with a user to understand a new request, identifies a "capability gap" (the lack of a pre-existing workflow), collaboratively designs a new workflow, and executes a test run.
2. **Capability Refinement and Reuse.** We will demonstrate how the agent can retrieve the previously saved workflow, adapt it to a new, more specific user request, and save the modified version as a new, reusable asset.
3. **Dynamic Failure Handling and Self-Healing.** We will simulate a runtime tool failure and show how a worker agent can dynamically swap to a substitute skill (by unloading the designated one, and loading an alternative one). We will also show how the system records these failures in its knowledge graph, allowing the Planner to proactively "heal" the master workflow for future runs, demonstrating self-evolution.

Through these scenarios, we will provide concrete examples of the agent's chain of thought (CoT), the artifacts it produces (like capability files, skill manifests, control-plane objects, notifications, etc), the tool calls it makes, and the updates it performs on its hybrid memory system (memory blocks, knowledge graph, and vector store).

### 1.5. Prerequisites

- Letta, Redis, Chroma, Graphiti, and Neo4j servers running locally.
- Vector store (e.g., Chroma) seeded with:
    - Regulatory rulebook chunks (`compliance_rules_v2024Q4.csv`).
    - Scoring formula document (`qa_scoring_formula_v3.md`).
    - Pre-existing capability files and skill manifests.
- Planner and Worker agent templates (see Appendix 5.7 and 5.8) configured with proper system instructions and built-in tools:
    - **Planner**: `get_skillset`, `validate_skill_manifest`, `validate_workflow`, `create_workflow_control_plane`,
      `create_worker_agents`, `read_workflow_control_plane`, `notify_next_worker_agent`, `notify_if_ready`,
      `finalize_workflow`, `store_memory`, `append_graph_episode`.
    - **Worker**: `read_workflow_control_plane`, `acquire_state_lease`, `update_workflow_control_plane`,
      `load_skill`, `unload_skill`, `invoke_skill_tool`, `store_memory`, `append_graph_episode`,
      `notify_next_worker_agent`, `notify_if_ready`.
- MCP server running locally, with SSE tooling endpoints accessible to Letta agents.
- Debugging level logging enabled for:
    - Planner/Worker conversations.
    - Tool inputs/outputs (JSON payloads).
    - Memory block writes (context window, working memory, archival memory).
    - Knowledge-graph mutations (episodes, entities, relationships, attributes).

---

## 2. Scenario 1: Initial Capability Creation

This scenario demonstrates the system's behavior when faced with a novel task for which no pre-defined workflow exists.

**Goal:** A compliance manager wants to review the performance of a newly hired advisor, Alex Wong, for calls made in the last week.

### 2.1. Conversation Timeline

> Turn 1 — User
>
>
> "Hi, I need to check the quality of advice calls made by Alex Wong last week. Can you help me analyse them?"
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Intent classification → *advisor QA review*.
> - Required outcomes: compliance verdicts, sentiment, score per call.
> - Check for existing workflow in semantic memory.
>
> </details>
>

> Turn 2 — Planner
>
>
> "Of course. To confirm, should I check compliance with the standard script, assess customer sentiment, and produce an overall score?"
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Clarify evaluation axes before designing workflow.
> - Prompt user for scoring rubric confirmation.
>
> </details>
>

> Turn 3 — User
>
>
> "Yes. Please use the existing QA scorecard."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - QA scorecard likely stored in vector store (`qa_scoring_formula_v3`).
> - Need skills: Salesforce lookup, recording retrieval, transcription, sentiment, compliance, scoring.
>
> </details>
>

> Turn 4 — Planner
>
>
> "Great. I'll source Alex's recordings for last week, transcribe them, analyse sentiment and compliance in parallel, and then compute the QA score. I'll run a single-call pilot first; if that looks good, I can scale to the whole set."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Confirmed plan; now evaluate capability catalog.
> - Expect capability gap (no prior workflow).
>
> </details>
>

### 2.2. Capability Assessment & Gap Detection (CoT)

1. **Intent Analysis:** The user wants to perform "Advice Call Analysis" for a specific advisor and date range. The key success metrics are **compliance**, **sentiment**, and a final **score**.
2. **Memory & Capability Check:**
    - **Vector Store Query:** Executes semantic vector search `search_embeddings(query="advice call analysis")`
    - **Result:** No existing capabilities found. **This is a capability gap.** I need to construct a new workflow JSON file. Planner records a **capability gap** memory block:

    ```json
    {
      "type": "capability_gap",
      "summary": "Advice Call Analysis capability missing; need to orchestrate Salesforce lookup, recording fetch, transcription, sentiment, compliance, scoring.",
      "tags": ["qa", "advisor_quality", "capability:new"]
    }
    ```

3. **Skill Discovery and Selection:**
    - **Vector Store Query:**Now that I know I need to build a new workflow, I must find the component skills. I will perform a series of semantic searches for skill manifests based on the required functions:
        - `search_embeddings(query="skill for salesforce data")` → Returns `skill://salesforce-integration@2.1.0`.
        - `search_embeddings(query="skill for retrieving call recordings")` → Returns `skill://recording-management@1.5.0`.
        - `search_embeddings(query="skill for audio transcription")` → Returns two alternatives: `skill://whisper-transcribe@1.0.0` and `skill://assemblyai-transcribe@1.2.0`.
        - `search_embeddings(query="skill for sentiment analysis")` → Returns `skill://sentiment-analysis@1.2.0`.
        - `search_embeddings(query="skill for compliance analysis")` → Returns `skill://compliance-analysis@1.3.0`.
        - `search_embeddings(query="skill for QA scoring")` → Returns `skill://scoring@1.1.0`.
    - **Knowledge Graph Query:**I have found two alternatives for the `transcription` step. To make an informed choice, I will now query the Knowledge Graph for their historical performance data.
        - `MATCH (s:Skill) WHERE s.manifestId IN ["skill://whisper-transcribe@1.0.0", "skill://assemblyai-transcribe@1.2.0"] RETURN s.manifestId, s.success_rate, s.p95_latency`.
        - **Result:**The graph shows both skills have a >99% success rate. I'll select the first candidate `whisper-transcribe` as the primary for this new workflow. The other skills have no alternatives, so I will use them directly.
4**Workflow Construction:**
   - Having discovered and selected all the necessary skills, I can now assemble them into a logical sequence.
   - **Step 1 (Get Apps):** The `salesforce-integration` skill can find applications by advisor name and date range.
   - **Step 2 (Get Recordings):** The `recording-management` skill can retrieve audio files by IDs.
   - **Step 3 (Transcribe):** The `whisper-transcribe` skill is selected.
   - **Step 4 (Analyze):** The problem splits here. I can run sentiment and compliance analysis in parallel to be more efficient. This requires a `Parallel` state in my ASL workflow. I will use the `sentiment-analysis` and `compliance-analysis` skills.
   - **Step 5 (Score):** The `scoring` skill can take the outputs from the parallel branches and compute a final score.
   - I will now compile this logic into a `letta-asl-workflow` JSON structure.

### 2.3. Workflow Drafting

The Planner composes a Letta-ASL workflow that conforms to `schemas/letta_asl_workflow_schema_v2.2.0.json` and validates it via `validate_workflow`.

[Note: ASL stands for Amazon States Language, a JSON-based language used to describe state machines declaratively. DCF capability/workflow schema uses a combination of Letta and ASL syntax.]

```json
{
  "workflow_schema_version": "2.2.0",
  "workflow_id": "c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21",
  "workflow_name": "Standard Advice Call Analysis",
  "description": "Analyse advisor call recordings for compliance, sentiment, and QA scoring.",
  "version": "1.0.0",
  "created_at": "2024-07-08T09:15:00Z",
  "author": "planner@selina",
  "tags": ["qa", "advisor_quality", "compliance"],
  "workflow_input_schema": {
    "type": "object",
    "properties": {
      "advisor_name": {"type": "string"},
      "start_date": {"type": "string", "format": "date"},
      "end_date": {"type": "string", "format": "date"}
    },
    "required": ["advisor_name", "start_date", "end_date"]
  },
  "skill_imports": [
    {"uri": "file://skills/salesforce-integration.json"},
    {"uri": "file://skills/recording-management.json"},
    {"uri": "file://skills/whisper-transcribe.json"},
    {"uri": "file://skills/sentiment-analysis.json"},
    {"uri": "file://skills/compliance-analysis.json"},
    {"uri": "file://skills/scoring.json"}
  ],
  "asl": {
    "Comment": "Salesforce lookup → recording retrieval → transcription → parallel sentiment/compliance → scoring",
    "StartAt": "GetApplicationIDs",
    "Version": "1.0",
    "States": {
      "GetApplicationIDs": {
        "Type": "Task",
        "Comment": "Find loan applications for the advisor over the date range.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
          "skills": ["skill://salesforce-integration@2.1.0"]
        },
        "Parameters": {
          "advisor_name.$": "$.advisor_name",
          "start_date.$": "$.start_date",
          "end_date.$": "$.end_date"
        },
        "ResultPath": "$.applications",
        "Next": "GetCallRecordings"
      },
      "GetCallRecordings": {
        "Type": "Task",
        "Comment": "Retrieve call recordings linked to the applications.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
          "skills": ["skill://recording-management@1.5.0"]
        },
        "Parameters": {
          "application_ids.$": "$.applications.data.ids"
        },
        "ResultPath": "$.recordings",
        "Next": "TranscribeRecording"
      },
      "TranscribeRecording": {
        "Type": "Task",
        "Comment": "Transcribe MP3 audio to text using Whisper backend.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
          "skills": ["skill://whisper-transcribe@1.0.0"]
        },
        "Parameters": {
          "recording_uri.$": "$.recordings.data[0].uri"
        },
        "ResultPath": "$.transcript",
        "Next": "ParallelAnalysis"
      },
      "ParallelAnalysis": {
        "Type": "Parallel",
        "Branches": [
          {
            "StartAt": "SentimentAnalysis",
            "States": {
              "SentimentAnalysis": {
                "Type": "Task",
                "Comment": "Assess overall sentiment and highlight issues.",
                "AgentBinding": {
                  "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
                  "skills": ["skill://sentiment-analysis@1.2.0"]
                },
                "Parameters": {
                  "transcript.$": "$.transcript.text"
                },
                "ResultPath": "$.sentiment",
                "End": true
              }
            }
          },
          {
            "StartAt": "ComplianceAnalysis",
            "States": {
              "ComplianceAnalysis": {
                "Type": "Task",
                "Comment": "Check transcript against compliance rules.",
                "AgentBinding": {
                  "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
                  "skills": ["skill://compliance-analysis@1.3.0"]
                },
                "Parameters": {
                  "transcript.$": "$.transcript.text",
                  "rule_set": "compliance_rules_v2024Q4"
                },
                "ResultPath": "$.compliance",
                "End": true
              }
            }
          }
        ],
        "ResultPath": "$.analysis",
        "Next": "CalculateScore"
      },
      "CalculateScore": {
        "Type": "Task",
        "Comment": "Combine sentiment and compliance outcomes into QA score.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
          "skills": ["skill://scoring@1.1.0"]
        },
        "Parameters": {
          "sentiment.$": "$.analysis.sentiment.report",
          "compliance.$": "$.analysis.compliance.verdicts",
          "formula": "qa_scoring_formula_v3"
        },
        "ResultPath": "$.qa_score",
        "End": true
      }
    }
  }
}
```

### 2.4. Tool Call Sequence

1. `salesforce-integration/applications.by_advisor`
2. `recording-management/recordings.by_application`
3. `whisper-transcribe/transcribe.audio`
4. `sentiment-analysis/analyse`
5. `compliance-analysis/evaluate`
6. `scoring/calculate`

Each tool call emits structured JSON responses captured in the control plane and persisted as artifacts.

### 2.5. Control Plane Objects

- **Meta document** (`schemas/control-plane-meta-1.0.0.json` compliant):

    ```json
    {
      "workflow_id": "c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21",
      "workflow_name": "Standard Advice Call Analysis",
      "schema_version": "1.0.0",
      "start_at": "GetApplicationIDs",
      "terminal_states": ["CalculateScore"],
      "states": [
        "GetApplicationIDs",
        "GetCallRecordings",
        "TranscribeRecording",
        "ParallelAnalysis",
        "SentimentAnalysis",
        "ComplianceAnalysis",
        "CalculateScore"
      ],
      "agents": {
        "planner": "agent://planner@1.0.0",
        "worker_pool": {"name": "agent_template_worker", "version": "1.0.0"}
      },
      "skills": {
        "GetApplicationIDs": ["skill://salesforce-integration@2.1.0"],
        "GetCallRecordings": ["skill://recording-management@1.5.0"],
        "TranscribeRecording": ["skill://whisper-transcribe@1.0.0"],
        "SentimentAnalysis": ["skill://sentiment-analysis@1.2.0"],
        "ComplianceAnalysis": ["skill://compliance-analysis@1.3.0"],
        "CalculateScore": ["skill://scoring@1.1.0"]
      },
      "deps": {
        "GetApplicationIDs": {"upstream": [], "downstream": ["GetCallRecordings"]},
        "GetCallRecordings": {"upstream": ["GetApplicationIDs"], "downstream": ["TranscribeRecording"]},
        "TranscribeRecording": {"upstream": ["GetCallRecordings"], "downstream": ["ParallelAnalysis"]},
        "ParallelAnalysis": {"upstream": ["TranscribeRecording"], "downstream": ["SentimentAnalysis", "ComplianceAnalysis"]},
        "SentimentAnalysis": {"upstream": ["ParallelAnalysis"], "downstream": ["CalculateScore"]},
        "ComplianceAnalysis": {"upstream": ["ParallelAnalysis"], "downstream": ["CalculateScore"]},
        "CalculateScore": {"upstream": ["SentimentAnalysis", "ComplianceAnalysis"], "downstream": []}
      }
    }
    ```

- **State document** (`TranscribeRecording` just before completion):

    ```json
    {
      "status": "running",
      "attempts": 1,
      "lease": {
        "token": "lease-5d40",
        "owner_agent_id": "worker-2",
        "ts": "2024-07-08T09:22:11Z",
        "ttl_s": 120
      },
      "started_at": "2024-07-08T09:22:10Z",
      "finished_at": null,
      "last_error": null
    }
    ```


### 2.6. Execution Flow: A Choreography of Workers

The Planner kicks off the workflow by calling `notify_next_worker_agent`. This begins a choreographed sequence of operations, with ephemeral worker agents performing each step.

1. **GetApplicationIDs:**
    - `Worker-1` receives the notification, acquires the lease for this state, and loads the `salesforce-integration` skill.
    - It calls the tool with `{advisor_name: "Alex Wong", ...}` and receives `{"ids": ["APP-49201"]}`.
    - It writes this output to the data plane, updates its state to `done`, releases the lease, and calls `notify_next_worker_agent` for `GetCallRecordings`.
2. **GetCallRecordings:**
    - `Worker-2` is activated, acquires the lease for `GetCallRecordings`, and loads the `recording-management` skill.
    - It reads the application ID from the data plane and retrieves the call recording URI.
    - It updates its state, releases the lease, and notifies the `TranscribeRecording` worker.
3. **TranscribeRecording:**
    - `Worker-3` acquires the lease and loads the `whisper-transcribe` skill.
    - It transcribes the audio, writes the full transcript text to the data plane, updates its state, releases its lease, and notifies the `ParallelAnalysis` state.
4. **ParallelAnalysis:**
    - The `ParallelAnalysis` state acts as a fork. It immediately notifies two *new* workers concurrently: `Worker-4` for `SentimentAnalysis` and `Worker-5` for `ComplianceAnalysis`.
    - `Worker-4 (Sentiment)`**:** Acquires the lease for its state, loads the `sentiment-analysis` skill, reads the transcript from the data plane, performs its analysis, and writes its result (`{ "overall": "Neutral", ...}`). It updates its state to `done` and releases its lease.
    - `Worker-5 (Compliance)`**:** Simultaneously, it acquires the lease for its state, loads the `compliance-analysis` skill, reads the transcript, and writes its result (`{"verdicts": [...]}`). It updates its state to `done` and releases its lease.
    - Both workers, upon completion, call `notify_if_ready` for the downstream `CalculateScore` state.
5. **CalculateScore:**
    - The `notify_if_ready` call from the last parallel worker to finish triggers the notification for `Worker-6`.
    - `Worker-6` acquires the lease, loads the `scoring` skill, reads the outputs from *both* the sentiment and compliance branches, calculates the final score, and writes it to the data plane.
    - It updates its state to `done` and releases the lease. The workflow is now complete.

### 2.7. Hybrid Memory Activity and Context Management

- **Letta's Virtual Context Management:** Throughout the workflow, the Planner Agent's context window could become cluttered with task details. Letta's virtual context manager works in the background to prevent this. For instance, after the Planner confirms the initial workflow with the user, it might have a large memory block containing the full conversation and the proposed plan. Letta can automatically summarize this:
    - **Original Memory Block:** `(User Interaction) "Hi, I need to check..." + (Agent Response) "Of course... here is the workflow..." + (User Confirmation) "Yes, that looks perfect."`
    - **Summarized Block (moved to working memory):** `User [Compliance Manager] requested QA analysis for Alex Wong. I proposed a 5-step workflow including parallel analysis, which the user approved.`
    - This frees up the main context window for the agent to focus on the next task: initiating and monitoring the workflow execution.
- **Vector Store for Retrieval:** The `capability_standard_advice_call_analysis_v1.json` file is chunked, embedded, and stored in the vector database. The key is that the *description* ("A standard workflow to analyze an advisor's call recordings...") is part of the embedded text. This allows the Planner in Scenario 2 to find this workflow later by performing a **semantic search** with a query like "find a workflow for checking compliance on calls."
- **The Sleep-Time Agent:** After the user interaction is complete, the Planner agent might become idle. This is when its companion **sleep-time agent** activates. This specialized agent performs offline optimization tasks without interrupting the main agent. It can:
    1. Review the Planner's recent working memory to a) consolidate transient working-memory blocks into an archival summary; and b) identify valuable, long-term memories (like the creation of a new, successful workflow).
    2. Move verbose artifacts (full transcripts) from the Planner’s context window into archival storage, replacing them with vector-store URIs.
    3. Call the `append_graph_episode` tool to update the Knowledge Graph with new nodes and relationships (e.g., creating the `WorkflowExecution` node and linking it to the skills used). This offloads the expensive task of graph updates from the main interactive loop.

---

## 3. Scenario 2: Workflow Refinement and Reuse

This scenario demonstrates how the system reuses and adapts existing workflows to solve similar, but distinct, problems.

**Goal:** A training manager wants to verify that all advisors are correctly explaining a new loan product, "HELOC 2.0," following a recent training course.

### 3.1. Conversation Timeline

> Turn 1 — User
>
>
> "I need to check if advisors are explaining the new HELOC 2.0 product correctly in their calls since the start of the month."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Trigger semantic search in workflow memory for "advice call analysis".
> - Evaluate if existing workflow matches narrower intent.
>
> </details>
>

> Turn 2 — Planner
>
>
> "I have a reusable Advice Call Analysis workflow. Shall I adapt it to isolate the advisor’s product explanation and run a compliance check just on that section?"
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Candidate workflow: `Standard Advice Call Analysis` (v1.0.0).
> - Need diarization + segmentation to isolate advisor speech.
>
> </details>
>

> Turn 3 — User
>
>
> "Yes, only the parts where the advisor describes the product matter."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Remove sentiment + scoring steps.
> - Add diarization and targeted compliance.
> - Save refined workflow as new asset; link via `REFINEMENT_OF` edge.
>
> </details>
>

### 3.2. The Agent's Internal Monologue (CoT)

1. **Intent Analysis:** The user wants to check for compliance on a specific topic ("HELOC 2.0" explanation) across all advisors.This is different from the previous general quality check.
2. **Memory & Capability Check (Hybrid Search for Adaptation):**
    - **Stage 1: Candidate Retrieval (Vector Store Query):** I'll perform a semantic search for existing workflows that are conceptually similar to the user's request.
        - `search_embeddings(query="compliance check for advisor product explanation")`
        - **Result:**The search returns two strong candidates:
            1. `capability_standard_advice_call_analysis_v1.json` (the general, foundational workflow).
            2. `capability_some_other_product_check_v1.json` (a *hypothetical*, previously-created workflow for a different product).
    - **Stage 2: Candidate Analysis & Selection (Knowledge Graph Query):** I now need to decide which of these two candidates is the better starting point. I will query the Knowledge Graph to enrich my understanding of them.
        - `MATCH (w:Workflow) WHERE w.id IN [...] RETURN w.id, w.description, w.skills_used, w.relationships`
        - **Result:** The graph shows that `capability_standard_advice_call_analysis_v1.json` is foundational. However, it also shows that `capability_some_other_product_check_v1.json` is a `REFINEMENT_OF` the standard one and, crucially, that it already contains the `diarization` and `segmentation` skills.
        - **Decision:** The user's new request also requires diarization and segmentation. Therefore, the derived workflow for the other product is a closer and more efficient starting point. Adapting it will require fewer changes (e.g., just changing the product name) than adapting the foundational workflow from scratch. **I will select the derived workflow as my template.**
3. **Workflow Refinement (illustrating both cases):**
    - Case A — a single foundational capability was found:
        - I will use the `workflow_advice_call_analysis_v1.json` as a template.
        - **Modify Step 1 (Get Apps):** Remove the 'advisor name' filter to get all applications in the date range.
        - **Keep Steps 2 & 3:** `GetCallRecordings` and `TranscribeRecording` are still needed.
        - **Insert New Step 4 (Diarize):** I need to add a diarization step to separate speakers. The `gpt4o-diarize` skill is available and has a high success rate according to the Knowledge Graph.
        - **Insert New Step 5 (Segment):** I need to add a `labelling-segmentation` skill to extract the relevant conversation parts.
        - **Modify Final Step:** Replace the `ParallelAnalysis` and `CalculateScore` states with a single `ComplianceAnalysis` task that operates on the output of the new segmentation step.
        - I will now compile this new logic into a new, versioned workflow JSON file.
    - Case B — a foundational and multiple derived capabilities were found:
        - I will use the selected derived workflow as my template.
        - The `diarization` and `segmentation` steps are already present, so I don't need to add them.
        - My only required change is to update the parameters to target the new product, "HELOC 2.0".
        - I will now compile this logic into a new, versioned workflow JSON file.

### 3.3. Capability Adaptation

Draft updated workflow, validate via schema, and version as `workflow_product_explanation_compliance_v1.json`.

```json
{
  "workflow_schema_version": "2.2.0",
  "workflow_id": "a8d3b1c9-9e8a-4f2b-9e3d-7c1b0d8a4b21",
  "workflow_name": "Product Explanation Compliance Check",
  "description": "Verify advisor delivery of HELOC 2.0 product details.",
  "version": "1.0.0",
  "created_at": "2024-08-05T10:02:00Z",
  "author": "planner@selina",
  "tags": ["qa", "product_training", "compliance"],
  "workflow_input_schema": {
    "type": "object",
    "properties": {
      "start_date": {"type": "string", "format": "date"},
      "end_date": {"type": "string", "format": "date"}
    },
    "required": ["start_date", "end_date"]
  },
  "skill_imports": [
    {"uri": "file://skills/salesforce-integration.json"},
    {"uri": "file://skills/recording-management.json"},
    {"uri": "file://skills/whisper-transcribe.json"},
    {"uri": "file://skills/gpt4o-diarize.json"},
    {"uri": "file://skills/labelling-segmentation.json"},
    {"uri": "file://skills/compliance-analysis.json"}
  ],
  "asl": {
    "Comment": "Focus on advisor narration of product details.",
    "StartAt": "GetApplicationIDs",
    "States": {
      "GetApplicationIDs": {
        "Type": "Task",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
          "skills": ["skill://salesforce-integration@2.1.0"]
        },
        "Parameters": {
          "start_date.$": "$.start_date",
          "end_date.$": "$.end_date"
        },
        "ResultPath": "$.applications",
        "Next": "GetCallRecordings"
      },
      "GetCallRecordings": {
        "Type": "Task",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
          "skills": ["skill://recording-management@1.5.0"]
        },
        "Parameters": {
          "application_ids.$": "$.applications.data.ids"
        },
        "ResultPath": "$.recordings",
        "Next": "TranscribeRecording"
      },
      "TranscribeRecording": {
        "Type": "Task",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
          "skills": ["skill://whisper-transcribe@1.0.0"]
        },
        "Parameters": {
          "recording_uri.$": "$.recordings.data[0].uri"
        },
        "ResultPath": "$.transcript",
        "Next": "DiarizeTranscript"
      },
      "DiarizeTranscript": {
        "Type": "Task",
        "Comment": "Isolate advisor speech segments.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
          "skills": ["skill://gpt4o-diarize@1.0.0"]
        },
        "Parameters": {
          "transcript.$": "$.transcript.segments",
          "target_speaker": "advisor"
        },
        "ResultPath": "$.advisor_segments",
        "Next": "SegmentAndLabel"
      },
      "SegmentAndLabel": {
        "Type": "Task",
        "Comment": "Apply taxonomy labels to advisor speech.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
          "skills": ["skill://labelling-segmentation@1.2.0"]
        },
        "Parameters": {
          "segments.$": "$.advisor_segments",
          "taxonomy": [
            "introduction",
            "security_check",
            "product_detail",
            "offer_explanation",
            "closing"
          ]
        },
        "ResultPath": "$.labelled_segments",
        "Next": "TargetedComplianceAnalysis"
      },
      "TargetedComplianceAnalysis": {
        "Type": "Task",
        "Comment": "Evaluate compliance on product-related segments only.",
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
          "skills": ["skill://compliance-analysis@1.3.0"]
        },
        "Parameters": {
          "segments.$": "$.labelled_segments",
          "allowed_labels": ["product_detail", "offer_explanation"],
          "rule_set": "compliance_rules_v2024Q4"
        },
        "ResultPath": "$.compliance",
        "End": true
      }
    }
  }
}
```

### 3.4. Memory and Knowledge Updates

- **Vector Store:** Refined workflow embedded and upserted with metadata `{"topic": "product_clarity", "origin": "c4b1a2e8-..."}`. Subsequent semantic searches for "product explanation compliance" rank it highly.
- **Planner Archival Memory:** Sleep-time agent summarises adaptation outcome: “Refined Standard Advice Call Analysis into Product Explanation Compliance Check; added diarization + segmentation; removed sentiment/scoring.”
- **Knowledge Graph:** Adds node `Workflow:a8d3b1c9...` with `REFINEMENT_OF` edge pointing to the original workflow. Advisor-product episodes link to `Product:HELOC 2.0` entity, enabling future analytics.

### 3.5. The Deeper Rationale: Why Track the `REFINEMENT_OF` Relationship?

1. **To Enable Intelligent Adaptation (Finding the "Closest Cousin"):** The primary benefit is allowing the agent to find the most efficient adaptation path. By understanding the "family tree" of capabilities, the agent can see that a derived capability (a "cousin") might share 90% of the DNA with the new request, while the foundational one (the "grandparent") only shares 60%. It can then choose the starting point that requires the least amount of work, making the agent faster and more efficient.
2. **To Improve Governance and Impact Analysis:** If a security flaw is found in a foundational capability or a business rule changes in the `Standard Advice Call Analysis` workflow, the `REFINEMENT_OF` edges provide an immediate, queryable dependency graph. A compliance officer can ask the system, "Show me all workflows that inherit from this one," and instantly see the full blast radius of a required change. This is impossible without explicitly tracking the lineage.
3. **To Facilitate Emergent Pattern Discovery:** Over time, by analyzing the structure of this "family tree" in the knowledge graph, the system can discover powerful meta-patterns. The sleep-time agent could identify that "95% of all product-specific compliance workflows are refinements of the standard analysis and always add a diarization step." This abstract knowledge can be used to accelerate future interactions even further. The Planner might one day say, "I see you're asking for a new product compliance check. Based on past experience, we will likely need to add diarization. Is that correct?" This demonstrates a higher level of understanding and true learning.

---

## 4. Scenario 3: Dynamic Failure Handling and Self-Healing

This scenario showcases the system's resilience and ability to learn from operational failures. Also, it illustrates how skills can be loaded and unloaded dynamically.

**Goal:** During the execution of the "Standard Advice Call Analysis" workflow, the primary transcription skill fails. The system must recover, complete the task, and learn from the failure to improve future runs.

### 4.1. Runtime Failure: A Skill Times Out

During a run of `workflow_advice_call_analysis_v1.json`, the worker agent responsible for the `TranscribeRecording` state attempts to use the `skill://whisper-transcribe@1.0.0`. However, the underlying service is unresponsive, and the tool call times out, returning an error.

- **Worker Agent's State:** The worker agent has acquired the lease for the `TranscribeRecording` state. Its current loaded skill has failed.
- **Control Plane Update:** The worker agent immediately updates the Redis state document for `TranscribeRecording`.

**State before failure:**

```json
{
  "status": "running",
  "attempts": 1,
  "lease": {"token": "xyz789", "owner_agent_id": "worker-3", ...},
  "started_at": "2024-07-15T10:02:30Z",
  "finished_at": null,
  "last_error": null
}
```

**State after failure:**

```json
{
  "status": "running", // Still running as it will be retried
  "attempts": 1, // Will be incremented to 2 on retry
  "lease": {"token": "xyz789", "owner_agent_id": "worker-3", ...},
  "started_at": "2024-07-15T10:02:30Z",
  "finished_at": null,
  "last_error": "TimeoutError: Tool call to whisper-transcribe timed out after 120s"
}
```

### 4.2. The Worker's Recovery Monologue (CoT)

- **Classify Error:** Timeout indicates transient or degraded service; retry with alternative backend rather than abort workflow.
- **Discover Alternative Skill:** Query vector store for `transcription` skills excluding Whisper. Top hit: `skill://assemblyai-transcribe@1.2.0` (success rate 0.99 per knowledge graph).
- **Swap Skills:**
  — `unload_skill("skill://whisper-transcribe@1.0.0")`
  — `load_skill("skill://assemblyai-transcribe@1.2.0")`
- **Retry:** Reinvoke transcription tool (`transcribe.async`) with webhook callback. Poll until job completes; update control plane state to `running` then `done` with new artifact pointer.

The AssemblyAI skill succeeds. The worker proceeds to write the output to the data plane, release its lease, and notify the downstream workers, allowing the workflow to continue. The updated control-plane state after recovery:

```json
{
  "status": "done",
  "attempts": 2,
  "lease": {
    "token": null,
    "owner_agent_id": null,
    "ts": null,
    "ttl_s": null
  },
  "started_at": "2024-07-15T10:05:50Z",
  "finished_at": "2024-07-15T10:11:14Z",
  "last_error": "TimeoutError: Tool call to whisper-transcribe timed out after 120s"
}
```

### 4.3. Post-Run Learning Loop

The workflow completes successfully, but the failure was logged permanently in the Knowledge Graph.

- **Adds archival memory block**:

    ```json
    {
      "type": "workflow_update",
      "workflow_id": "advice_call_analysis_product_focus",
      "version": "2",
      "reason": "Whisper timeout rate exceeded threshold; switched to AssemblyAI backend.",
      "timestamp": "2024-07-15T11:24:00Z"
    }
    ```

- **Knowledge Graph Update (via Sleep-Time Agent):** The raw event of the failure is now in the worker's archival memory. Later, during a period of inactivity, the Planner's **sleep-time agent** processes these archival records. It identifies the `workflow_update` block, understands its meaning, and translates it into a structured update for the knowledge graph. It calls the `append_graph_episode` tool to formally increment the `n_failures` count on the `(Skill:whisper-transcribe)` node and establish or reinforce the `(Skill:assemblyai-transcribe)` node as a reliable alternative. This offline processing ensures the main agent is not burdened with these analytical tasks.

### 4.4. The Evolved Workflow

A week later, after several more runs have experienced similar timeouts, the Planner Agent is tasked with another "Standard Advice Call Analysis."

- **Planner Agent's Monologue (Proactive Healing):**
    1. **Pre-flight Check:** Before executing `workflow_advice_call_analysis_v1.json`, I will validate its components against the Knowledge Graph for reliability.
    2. **Knowledge Graph Query:** `MATCH (s:Skill {name: 'whisper-transcribe'}) RETURN s.n_success, s.n_failures`.
    3. **Result:** The query shows that the failure rate for the Whisper skill (`n_failures / (n_success + n_failures)`) has now crossed a predefined threshold of 5%. The alternative, `assemblyai-transcribe`, has a failure rate below 1%.
    4. **Proactive Healing:** The primary transcription skill in the stored workflow is no longer reliable. I will recommend a new version of the workflow to the user.
    5. **Generate New Version:** I will programmatically create `workflow_advice_call_analysis_v1.0.1.json`, which is identical to the original except that the `TranscribeRecording` state's `AgentBinding` now lists `skill://assemblyai-transcribe@1.2.0` instead of the Whisper skill.
- **Updated Workflow Snippet:**

    ```json
    "TranscribeRecording": {
      "Type": "Task",
      "Comment": "Transcribe MP3 audio using AssemblyAI backend with async polling.",
      "AgentBinding": {
        "agent_template_ref": {"name": "agent_template_worker", "version": "1.0.0"},
        "skills": ["skill://assemblyai-transcribe@1.2.0"]
      },
      "Parameters": {
        "recording_uri.$": "$.recordings.data[0].uri",
        "webhook": "{{control_plane.webhook_url}}"
      },
      "ResultPath": "$.transcript",
      "Next": "ParallelAnalysis"
    }
    ```


**[PLANNER AGENT]:** "I am ready to start the Advice Call Analysis. I've noticed that a tool I normally use for transcription has become less reliable recently. I have updated the workflow to use a more stable alternative to ensure a smooth execution. I will proceed with this improved version."

The system doesn't just recover from failure; it learns from it. By persistently recording performance data in the knowledge graph, the Planner can identify degrading tools and proactively "heal" its own workflows, ensuring the system becomes more robust and reliable over time. This closes the loop on self-evolution.

---

## 5. Appendices

### 5.1 Capability Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://selinafinance.co.uk/schemas/letta-asl-workflow-2.2.0.json",
  "title": "Letta-ASL Workflow (v2.2.0, DAG + Ephemeral Workers + Skills)",
  "description": "Workflow schema aligned with AWS Step Functions (ASL) and Letta Agent File (.af) v2. Each Task spawns ephemeral workers from .af v2 agent templates and may load skills from skill manifests at runtime.",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "workflow_schema_version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "default": "2.2.0",
      "description": "Version of this workflow schema (semver)."
    },
    "workflow_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for this workflow instance."
    },
    "workflow_name": {
      "type": "string"
    },
    "description": {
      "type": "string"
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "description": "Semantic version of this workflow definition (author-controlled)."
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    },
    "author": {
      "type": "string"
    },
    "tags": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "default": []
    },
    "workflow_input_schema": {
      "type": "object",
      "description": "JSON Schema describing initial inputs for the workflow."
    },
    "af_imports": {
      "description": "External Letta .af v2 bundles to load (file paths or file:// URIs).",
      "type": "array",
      "items": {
        "$ref": "#/$defs/ImportItem"
      },
      "default": []
    },
    "skill_imports": {
      "description": "External skill manifests or bundles (file paths or file:// URIs).",
      "type": "array",
      "items": {
        "$ref": "#/$defs/SkillImport"
      },
      "default": []
    },
    "agents": {
      "description": "Optional named agents available to the workflow (referenced by agent_ref). Most executions will prefer per-state ephemeral workers via AgentBinding.agent_template_ref.",
      "type": "array",
      "items": {
        "$ref": "#/$defs/AgentDefinition"
      },
      "default": []
    },
    "asl": {
      "description": "AWS Step Functions-style state machine for execution (DAG-friendly).",
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "Comment": {
          "type": "string"
        },
        "StartAt": {
          "type": "string"
        },
        "Version": {
          "type": "string",
          "default": "1.0"
        },
        "TimeoutSeconds": {
          "type": "integer",
          "minimum": 1
        },
        "States": {
          "type": "object",
          "additionalProperties": {
            "$ref": "#/$defs/AslState"
          }
        }
      },
      "required": [
        "StartAt",
        "States"
      ]
    }
  },
  "required": [
    "workflow_id",
    "workflow_name",
    "version",
    "asl"
  ],
  "$defs": {
    "ImportItem": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "uri": {
          "type": "string",
          "description": "Path or file:// URI to a .af v2 JSON bundle."
        },
        "version": {
          "type": "string",
          "enum": [
            "2"
          ],
          "default": "2"
        },
        "integrity": {
          "type": [
            "string",
            "null"
          ],
          "description": "Optional integrity hash (e.g., sha256:...)"
        }
      },
      "required": [
        "uri"
      ]
    },
    "SkillImport": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "uri": {
          "type": "string",
          "description": "Path or file:// URI to a skill manifest (or a bundle with {\"skills\":[...]})."
        },
        "integrity": {
          "type": [
            "string",
            "null"
          ]
        }
      },
      "required": [
        "uri"
      ]
    },
    "AgentRef": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string"
        },
        "name": {
          "type": "string"
        }
      }
    },
    "AgentDefinition": {
      "title": "Agent Definition (reference only)",
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "agent_name": {
          "type": "string"
        },
        "agent_ref": {
          "$ref": "#/$defs/AgentRef"
        }
      },
      "required": [
        "agent_name",
        "agent_ref"
      ]
    },
    "Lifecycle": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "mode": {
          "type": "string",
          "enum": [
            "ephemeral",
            "pooled",
            "existing"
          ],
          "default": "ephemeral"
        },
        "destroy_on_end": {
          "type": "boolean",
          "default": true
        },
        "reuse_key": {
          "type": [
            "string",
            "null"
          ],
          "description": "Reusable key for pooled/existing modes."
        }
      },
      "default": {
        "mode": "ephemeral",
        "destroy_on_end": true
      }
    },
    "AslState": {
      "description": "Amazon States Language subset with Letta bindings for DAG + ephemeral workers.",
      "type": "object",
      "additionalProperties": true,
      "properties": {
        "Type": {
          "type": "string",
          "enum": [
            "Task",
            "Choice",
            "Pass",
            "Wait",
            "Parallel",
            "Map",
            "Fail",
            "Succeed"
          ]
        },
        "Comment": {
          "type": "string"
        },
        "Parameters": {
          "type": "object"
        },
        "ResultPath": {
          "type": "string"
        },
        "Next": {
          "type": "string"
        },
        "End": {
          "type": "boolean"
        },
        "Choices": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": true
          }
        },
        "Default": {
          "type": "string"
        },
        "Branches": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "StartAt": {
                "type": "string"
              },
              "States": {
                "type": "object",
                "additionalProperties": {
                  "$ref": "#/$defs/AslState"
                }
              }
            },
            "required": [
              "StartAt",
              "States"
            ]
          }
        },
        "ItemsPath": {
          "type": "string"
        },
        "Iterator": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "StartAt": {
              "type": "string"
            },
            "States": {
              "type": "object",
              "additionalProperties": {
                "$ref": "#/$defs/AslState"
              }
            }
          },
          "required": [
            "StartAt",
            "States"
          ]
        },
        "ResultSelector": {
          "type": "object"
        },
        "Catch": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": true
          }
        },
        "Retry": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": true
          }
        },
        "AgentBinding": {
          "description": "Bind a Task state to a Letta agent template (ephemeral worker) and load skills at runtime.",
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "agent_template_ref": {
              "$ref": "#/$defs/AgentRef",
              "description": "Reference to an .af v2 agent template used to spawn an ephemeral worker for this state."
            },
            "agent_ref": {
              "$ref": "#/$defs/AgentRef",
              "description": "Optional: existing agent to use instead of spawning a worker."
            },
            "skills": {
              "type": "array",
              "description": "List of skill IDs (e.g., skill://...@semver) to load before executing this state.",
              "items": {
                "type": "string"
              },
              "default": []
            },
            "tool_name": {
              "type": "string",
              "description": "Optional direct tool entrypoint (advanced; usually provided by loaded skills)."
            },
            "lifecycle": {
              "$ref": "#/$defs/Lifecycle"
            }
          }
        }
      },
      "required": [
        "Type"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "Type": {
                "const": "Task"
              }
            }
          },
          "then": {
            "properties": {
              "AgentBinding": {
                "type": "object"
              }
            },
            "required": [
              "AgentBinding"
            ]
          }
        }
      ]
    }
  }
}
```

### 5.2 Skill Manifest Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://selinafinance.co.uk/schemas/skill-manifest-v2.0.0.json",
  "title": "Skill Manifest v2.0.0",
  "description": "Defines a reusable Skill Package: directives, tools, and data sources that can be loaded into a Letta agent at runtime.",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "manifestApiVersion": { "type": "string", "enum": ["v2.0.0"] },
    "skillPackageId":     { "type": "string", "format": "uuid" },
    "manifestId":         { "type": "string", "format": "uuid" },
    "skillName":          { "type": "string", "minLength": 1 },
    "skillVersion":       { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+(?:-[0-9A-Za-z-.]+)?$" },
    "description":        { "type": "string" },
    "tags":               { "type": "array", "items": { "type": "string" }, "default": [] },
    "permissions": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "secrets": { "type": "array", "items": { "type": "string" }, "default": [] },
        "egress":  { "type": "string", "enum": ["none", "intranet", "internet"], "default": "none" }
      },
      "default": {}
    },

    "skillDirectives": { "type": "string", "minLength": 1 },

    "requiredTools": {
      "type": "array",
      "items": { "$ref": "#/$defs/ToolRequirement" },
      "default": []
    },

    "requiredDataSources": {
      "type": "array",
      "items": { "$ref": "#/$defs/DataSource" },
      "default": []
    }
  },
  "required": [
    "manifestApiVersion",
    "skillPackageId",
    "manifestId",
    "skillName",
    "skillVersion",
    "skillDirectives"
  ],

  "$defs": {
    "ToolRequirement": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "toolName":   { "type": "string", "minLength": 1 },
        "description":{ "type": "string", "minLength": 1 },
        "json_schema":{ "$ref": "#/$defs/ToolJSONSchema" },
        "definition": {
          "oneOf": [
            { "$ref": "#/$defs/ToolDefPython" },
            { "$ref": "#/$defs/ToolDefRegistered" },
            { "$ref": "#/$defs/ToolDefMcp" }
          ]
        }
      },
      "required": ["toolName", "description", "definition"]
    },

    "ToolJSONSchema": {
      "title": "Tool JSON Schema (OpenAI/Letta-compatible)",
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "name": { "type": "string" },
        "description": { "type": "string" },
        "parameters": {
          "type": "object",
          "additionalProperties": true,
          "properties": {
            "type": { "type": ["string", "null"], "default": "object" },
            "properties": {
              "type": "object",
              "additionalProperties": {
                "type": "object",
                "additionalProperties": true,
                "properties": {
                  "type": { "type": "string" },
                  "description": { "type": ["string", "null"] }
                },
                "required": ["type"]
              }
            },
            "required": { "type": "array", "items": { "type": "string" }, "default": [] }
          },
          "required": ["properties"]
        },
        "type": { "type": ["string", "null"] },
        "required": { "type": "array", "items": { "type": "string" }, "default": [] }
      },
      "required": ["name", "description", "parameters"]
    },

    "ToolDefPython": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": { "const": "python_source" },
        "sourceCode": { "type": "string", "minLength": 1 }
      },
      "required": ["type", "sourceCode"]
    },

    "ToolDefRegistered": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": { "const": "registered" },
        "platformToolId": { "type": "string", "minLength": 1 }
      },
      "required": ["type", "platformToolId"]
    },

    "ToolDefMcp": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": { "const": "mcp_server" },
        "endpointUrl": { "type": "string", "format": "uri" },
        "operationId": { "type": "string", "minLength": 1 },
        "openApiSpecUrl": { "type": "string", "format": "uri" }
      },
      "required": ["type", "endpointUrl", "operationId"]
    },

    "DataSource": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "dataSourceId": { "type": "string", "format": "uuid" },
        "description": { "type": "string" },
        "destination": { "type": "string", "enum": ["archival_memory"], "default": "archival_memory" },
        "content": {
          "oneOf": [ { "$ref": "#/$defs/DS_TextContent" } ]
        }
      },
      "required": ["dataSourceId", "destination", "content"]
    },

    "DS_TextContent": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": { "const": "text_content" },
        "text": { "type": "string", "minLength": 1 }
      },
      "required": ["type", "text"]
    }
  }
}
```

### 5.3 Workflow Control-Plane Metadata Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/control-plane-meta-1.0.0.json",
  "title": "Control Plane: Workflow Meta v1.0.0",
  "type": "object",
  "properties": {
    "workflow_id": {
      "type": "string",
      "format": "uuid"
    },
    "workflow_name": {
      "type": "string"
    },
    "schema_version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "start_at": {
      "type": "string"
    },
    "terminal_states": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "default": []
    },
    "states": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "agents": {
      "type": "object",
      "additionalProperties": {
        "type": "string"
      }
    },
    "skills": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": {
          "type": "string"
        }
      }
    },
    "deps": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "upstream": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "default": []
          },
          "downstream": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "default": []
          }
        },
        "required": [
          "upstream",
          "downstream"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "workflow_id",
    "start_at",
    "states",
    "deps"
  ],
  "additionalProperties": false
}
```

### 5.4 Workflow Control-Plane State Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/control-plane-state-1.0.0.json",
  "title": "Control Plane: State Record v1.0.0",
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": [
        "pending",
        "running",
        "done",
        "failed"
      ]
    },
    "attempts": {
      "type": "integer",
      "minimum": 0
    },
    "lease": {
      "type": "object",
      "properties": {
        "token": {
          "type": [
            "string",
            "null"
          ]
        },
        "owner_agent_id": {
          "type": [
            "string",
            "null"
          ]
        },
        "ts": {
          "type": [
            "string",
            "null"
          ],
          "format": "date-time"
        },
        "ttl_s": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 1
        }
      },
      "required": [
        "token",
        "owner_agent_id",
        "ts",
        "ttl_s"
      ],
      "additionalProperties": false
    },
    "started_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    },
    "finished_at": {
      "type": [
        "string",
        "null"
      ],
      "format": "date-time"
    },
    "last_error": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "status",
    "attempts",
    "lease"
  ],
  "additionalProperties": false
}
```

### 5.5 Workflow Notification Payload Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/notification-payload-1.0.0.json",
  "title": "Workflow Notification Payload v1.0.0",
  "type": "object",
  "properties": {
    "workflow_event": {
      "type": "object",
      "properties": {
        "type": {
          "type": "string",
          "enum": [
            "notify_start"
          ]
        },
        "workflow_id": {
          "type": "string",
          "format": "uuid"
        },
        "state": {
          "type": "string"
        },
        "reason": {
          "type": "string",
          "enum": [
            "initial",
            "upstream_done"
          ]
        },
        "nudge_id": {
          "type": "string",
          "format": "uuid"
        }
      },
      "required": [
        "type",
        "workflow_id",
        "state",
        "reason",
        "nudge_id"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "workflow_event"
  ],
  "additionalProperties": false
}
```

### 5.6 Workflow Data-Plane Output Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/data-plane-output-1.0.0.json",
  "title": "Data Plane: Output Envelope v1.0.0",
  "type": "object",
  "properties": {
    "ok": {
      "type": "boolean"
    },
    "summary": {
      "type": [
        "string",
        "null"
      ]
    },
    "data": {
      "type": "object",
      "additionalProperties": true
    },
    "metrics": {
      "type": "object",
      "properties": {
        "latency_ms": {
          "type": [
            "number",
            "integer"
          ],
          "minimum": 0
        }
      },
      "additionalProperties": true
    },
    "artifacts": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "ok"
  ],
  "additionalProperties": true
}
```

### 5.7 Planner Agent Template

```json
{
  "agents": [
    {
      "name": "planner",
      "tool_ids": [
        "tool-0",
        "tool-1",
        "tool-6",
        "tool-7",
        "tool-8",
        "tool-9",
        "tool-10",
        "tool-11",
        "tool-12",
        "tool-13",
        "tool-14",
        "tool-15",
        "tool-16"
      ],
      "block_ids": [
        "block-0",
        "block-1"
      ],
      "tool_rules": [
        {
          "tool_name": "conversation_search",
          "type": "continue_loop"
        },
        {
          "tool_name": "send_message",
          "type": "exit_loop"
        }
      ],
      "system": "<base_instructions>... ...</base_instructions>",
      "agent_type": "letta_v1_agent",
      "llm_config": {
        "model": "gpt-5",
        "model_endpoint_type": "openai",
        "model_endpoint": "https://api.openai.com/v1",
        "provider_name": "openai",
        "provider_category": "base",
        "model_wrapper": null,
        "context_window": 250000,
        "put_inner_thoughts_in_kwargs": false,
        "handle": "openai/gpt-5",
        "temperature": 0.2,
        "max_tokens": 16384,
        "enable_reasoner": true,
        "reasoning_effort": "minimal",
        "max_reasoning_tokens": 0,
        "frequency_penalty": null,
        "compatibility_type": null,
        "verbosity": "medium",
        "tier": null
      },
      "embedding_config": {
        "embedding_endpoint_type": "openai",
        "embedding_endpoint": "https://embeddings.letta.com/",
        "embedding_model": "letta-free",
        "embedding_dim": 1536
      },
      "description": "DCF Planner Agent with a sleep-time companion.",
      "id": "agent-0",
      "group_ids": [
        "group-0"
      ]
    },
    {
      "name": "planner-sleeptime",
      "tool_ids": [
        "tool-2",
        "tool-3",
        "tool-4",
        "tool-5"
      ],
      "block_ids": [
        "block-0",
        "block-1",
        "block-2"
      ],
      "tool_rules": [
        {
          "tool_name": "memory_finish_edits",
          "type": "exit_loop"
        },
        {
          "tool_name": "memory_insert",
          "type": "continue_loop"
        },
        {
          "tool_name": "memory_rethink",
          "type": "continue_loop"
        },
        {
          "tool_name": "memory_replace",
          "type": "continue_loop"
        }
      ],
      "system": "<base_instructions>... ...</base_instructions>",
      "agent_type": "sleeptime_agent",
      "llm_config": {
        "model": "letta-free",
        "model_endpoint_type": "openai",
        "model_endpoint": "https://inference.letta.com/v1/",
        "provider_name": "letta",
        "provider_category": "base",
        "model_wrapper": null,
        "context_window": 30000,
        "put_inner_thoughts_in_kwargs": false,
        "handle": "letta/letta-free",
        "temperature": 0.7,
        "max_tokens": null,
        "enable_reasoner": false,
        "reasoning_effort": null,
        "max_reasoning_tokens": 0,
        "frequency_penalty": null,
        "compatibility_type": null,
        "verbosity": null,
        "tier": null
      },
      "embedding_config": {
        "embedding_endpoint_type": "openai",
        "embedding_endpoint": "https://embeddings.letta.com/",
        "embedding_model": "letta-free",
        "embedding_dim": 1536
      },
      "timezone": "UTC",
      "max_files_open": 5,
      "per_file_view_window_char_limit": 15000,
      "id": "agent-1"
    }
  ],
  "groups": [
    {
      "agent_ids": [
        "agent-1"
      ],
      "manager_config": {
        "manager_type": "sleeptime",
        "manager_agent_id": "agent-0",
        "sleeptime_agent_frequency": 5
      },
      "id": "group-0"
    }
  ],
  "blocks": [
    {
      "value": "This is my section of core memory devoted to information about the human...",
      "limit": 20000,
      "project_id": null,
      "template_name": null,
      "is_template": false,
      "template_id": null,
      "base_template_id": null,
      "deployment_id": null,
      "entity_id": null,
      "preserve_on_migration": false,
      "label": "human",
      "read_only": false,
      "description": "The human block: Stores key details about the person you are conversing with, allowing for more personalized and friend-like conversation.",
      "metadata": {},
      "hidden": null,
      "id": "block-1"
    },
    {
      "value": "I am an expert conversation memory agent that can do the following:...",
      "limit": 20000,
      "project_id": null,
      "template_name": null,
      "is_template": false,
      "template_id": null,
      "base_template_id": null,
      "deployment_id": null,
      "entity_id": null,
      "preserve_on_migration": false,
      "label": "memory_persona",
      "read_only": false,
      "description": null,
      "metadata": {},
      "hidden": null,
      "id": "block-2"
    },
    {
      "value": "The following is my persona:..."",
      "limit": 20000,
      "project_id": null,
      "template_name": null,
      "is_template": false,
      "template_id": null,
      "base_template_id": null,
      "deployment_id": null,
      "entity_id": null,
      "preserve_on_migration": false,
      "label": "persona",
      "read_only": false,
      "description": "The persona block: Stores details about your current persona, guiding how you behave and respond. This helps you to maintain consistency and personality in your interactions.",
      "metadata": {},
      "hidden": null,
      "id": "block-0"
    }
  ],
  "tools": [
    {
      "id": "tool-0",
      "tool_type": "letta_core",
      "description": "Search prior conversation history using hybrid search...",
      "source_type": "python",
      "name": "conversation_search",
      "tags": [
        "letta_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-1",
      "tool_type": "letta_core",
      "description": "Sends a message to the human user...",
      "source_type": "python",
      "name": "send_message",
      "tags": [
        "letta_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-2",
      "tool_type": "letta_sleeptime_core",
      "description": "This function is called when the agent is done rethinking the memory...",
      "source_type": "python",
      "name": "memory_finish_edits",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-3",
      "tool_type": "letta_sleeptime_core",
      "description": "The memory_insert command allows you to insert text at a specific location in a memory block...",
      "source_type": "python",
      "name": "memory_insert",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-4",
      "tool_type": "letta_sleeptime_core",
      "description": "The memory_replace command allows you to replace a specific string in a memory block with a new string...",
      "source_type": "python",
      "name": "memory_replace",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-5",
      "tool_type": "letta_sleeptime_core",
      "description": "The memory_rethink command allows you to completely rewrite the contents of a memory block...",
      "source_type": "python",
      "name": "memory_rethink",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-6",
      "tool_type": "dcf",
      "description": "Discover Skill Manifests from a directory and summarize their metadata...",
      "source_type": "python",
      "name": "get_skillset",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-7",
      "tool_type": "dcf",
      "description": "Validate a Skill Manifest (v2.0.0) and run static sanity checks...",
      "source_type": "python",
      "name": "validate_skill_manifest",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-8",
      "tool_type": "dcf",
      "description": "Validate a Letta–ASL workflow (v2.2.0) and resolve .af and skill references...",
      "source_type": "python",
      "name": "validate_workflow",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-9",
      "tool_type": "dcf",
      "description": "Create idempotently the RedisJSON control-plane for a workflow (choreography style)...",
      "source_type": "python",
      "name": "create_workflow_control_plane",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-10",
      "tool_type": "dcf",
      "description": "Create one worker agent per ASL Task state using Letta .af v2 templates...",
      "source_type": "python",
      "name": "create_worker_agents",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-11",
      "tool_type": "dcf",
      "description": "Read workflow control-plane documents from RedisJSON and optionally compute readiness...",
      "source_type": "python",
      "name": "read_workflow_control_plane",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-12",
      "tool_type": "dcf",
      "description": "Notify downstream (or initial) worker agent(s) for a workflow state machine...",
      "source_type": "python",
      "name": "notify_next_worker_agent",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-13",
      "tool_type": "dcf",
      "description": "Notify a single target state's worker agent IFF the state is ready (or unconditionally if require_ready=False)...",
      "source_type": "python",
      "name": "notify_if_ready",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-14",
      "tool_type": "dcf",
      "description": "Finalize a workflow execution: optionally delete worker agents, close open states, and write final audit/summary metadata...",
      "source_type": "python",
      "name": "finalize_workflow",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-15",
      "tool_type": "dcf",
      "description": "Store workflow insights into long-term memory for downstream agents...",
      "source_type": "python",
      "name": "store_memory",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-16",
      "tool_type": "dcf",
      "description": "Append a workflow execution episode to the shared knowledge graph timeline...",
      "source_type": "python",
      "name": "append_graph_episode",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    }
  ],
  "metadata": {
    "revision_id": "c734cfc0d595"
  }
}
```

### 5.8 Worker Agent Template

```json
{
  "agents": [
    {
      "name": "worker",
      "tool_ids": [
        "tool-0",
        "tool-1",
        "tool-11",
        "tool-12",
        "tool-13",
        "tool-15",
        "tool-16",
        "tool-17",
        "tool-18",
        "tool-19",
        "tool-20",
        "tool-21"
      ],
      "block_ids": [
        "block-0",
        "block-1"
      ],
      "tool_rules": [
        {
          "tool_name": "conversation_search",
          "type": "continue_loop"
        },
        {
          "tool_name": "send_message",
          "type": "exit_loop"
        }
      ],
      "system": "<base_instructions>... ...</base_instructions>",
      "agent_type": "letta_v1_agent",
      "llm_config": {
        "model": "gpt-4.1",
        "model_endpoint_type": "openai",
        "model_endpoint": "https://api.openai.com/v1",
        "provider_name": "openai",
        "provider_category": "base",
        "model_wrapper": null,
        "context_window": 1000000,
        "put_inner_thoughts_in_kwargs": false,
        "handle": "openai/gpt-4.1",
        "temperature": 0.2,
        "max_tokens": 8192,
        "enable_reasoner": false,
        "reasoning_effort": null,
        "max_reasoning_tokens": 0,
        "frequency_penalty": null,
        "compatibility_type": null,
        "verbosity": null,
        "tier": null
      },
      "embedding_config": {
        "embedding_endpoint_type": "openai",
        "embedding_endpoint": "https://embeddings.letta.com/",
        "embedding_model": "letta-free",
        "embedding_dim": 1536
      },
      "description": "DCF Worker Agent with a sleep-time companion.",
      "id": "agent-0",
      "group_ids": [
        "group-0"
      ]
    },
    {
      "name": "worker-sleeptime",
      "tool_ids": [
        "tool-2",
        "tool-3",
        "tool-4",
        "tool-5"
      ],
      "block_ids": [
        "block-0",
        "block-1",
        "block-2"
      ],
      "tool_rules": [
        {
          "tool_name": "memory_finish_edits",
          "type": "exit_loop"
        },
        {
          "tool_name": "memory_insert",
          "type": "continue_loop"
        },
        {
          "tool_name": "memory_rethink",
          "type": "continue_loop"
        },
        {
          "tool_name": "memory_replace",
          "type": "continue_loop"
        }
      ],
      "system": "<base_instructions>... ...</base_instructions>",
      "agent_type": "sleeptime_agent",
      "llm_config": {
        "model": "letta-free",
        "model_endpoint_type": "openai",
        "model_endpoint": "https://inference.letta.com/v1/",
        "provider_name": "letta",
        "provider_category": "base",
        "model_wrapper": null,
        "context_window": 30000,
        "put_inner_thoughts_in_kwargs": true,
        "handle": "letta/letta-free",
        "temperature": 0.7,
        "max_tokens": null,
        "enable_reasoner": true,
        "reasoning_effort": null,
        "max_reasoning_tokens": 0,
        "frequency_penalty": null,
        "compatibility_type": null,
        "verbosity": null,
        "tier": null
      },
      "embedding_config": {
        "embedding_endpoint_type": "openai",
        "embedding_endpoint": "https://embeddings.letta.com/",
        "embedding_model": "letta-free",
        "embedding_dim": 1536
      },
      "timezone": "UTC",
      "max_files_open": 5,
      "per_file_view_window_char_limit": 15000,
      "id": "agent-1"
    }
  ],
  "groups": [
    {
      "agent_ids": [
        "agent-1"
      ],
      "manager_config": {
        "manager_type": "sleeptime",
        "manager_agent_id": "agent-0",
        "sleeptime_agent_frequency": 5
      },
      "id": "group-0"
    }
  ],
  "blocks": [
    {
      "value": "This is my section of core memory devoted to information about the human...",
      "limit": 20000,
      "project_id": null,
      "template_name": null,
      "is_template": false,
      "template_id": null,
      "base_template_id": null,
      "deployment_id": null,
      "entity_id": null,
      "preserve_on_migration": false,
      "label": "human",
      "read_only": false,
      "description": "The human block: Stores key details about the person you are conversing with, allowing for more personalized and friend-like conversation.",
      "metadata": {},
      "hidden": null,
      "id": "block-1"
    },
    {
      "value": "I am an expert conversation memory agent that can do the following:...",
      "limit": 20000,
      "project_id": null,
      "template_name": null,
      "is_template": false,
      "template_id": null,
      "base_template_id": null,
      "deployment_id": null,
      "entity_id": null,
      "preserve_on_migration": false,
      "label": "memory_persona",
      "read_only": false,
      "description": null,
      "metadata": {},
      "hidden": null,
      "id": "block-2"
    },
    {
      "value": "The following is my persona...",
      "limit": 20000,
      "project_id": null,
      "template_name": null,
      "is_template": false,
      "template_id": null,
      "base_template_id": null,
      "deployment_id": null,
      "entity_id": null,
      "preserve_on_migration": false,
      "label": "persona",
      "read_only": false,
      "description": "The persona block: Stores details about your current persona, guiding how you behave and respond. This helps you to maintain consistency and personality in your interactions.",
      "metadata": {},
      "hidden": null,
      "id": "block-0"
    }
  ],
  "tools": [
    {
      "id": "tool-0",
      "tool_type": "letta_core",
      "description": "Search prior conversation history using hybrid search...",
      "source_type": "python",
      "name": "conversation_search",
      "tags": [
        "letta_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-1",
      "tool_type": "letta_core",
      "description": "Sends a message to the human user.",
      "source_type": "python",
      "name": "send_message",
      "tags": [
        "letta_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-2",
      "tool_type": "letta_sleeptime_core",
      "description": "This function is called when the agent is done rethinking the memory...",
      "source_type": "python",
      "name": "memory_finish_edits",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-3",
      "tool_type": "letta_sleeptime_core",
      "description": "The memory_insert command allows you to insert text at a specific location in a memory block...",
      "source_type": "python",
      "name": "memory_insert",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-4",
      "tool_type": "letta_sleeptime_core",
      "description": "The memory_replace command allows you to replace a specific string in a memory block with a new string...",
      "source_type": "python",
      "name": "memory_replace",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-5",
      "tool_type": "letta_sleeptime_core",
      "description": "The memory_rethink command allows you to completely rewrite the contents of a memory block...",
      "source_type": "python",
      "name": "memory_rethink",
      "tags": [
        "letta_sleeptime_core"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-11",
      "tool_type": "dcf",
      "description": "Read workflow control-plane documents from RedisJSON and optionally compute readiness...",
      "source_type": "python",
      "name": "read_workflow_control_plane",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-12",
      "tool_type": "dcf",
      "description": "Notify downstream (or initial) worker agent(s) for a workflow state machine.",
      "source_type": "python",
      "name": "notify_next_worker_agent",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-13",
      "tool_type": "dcf",
      "description": "Notify a single target state's worker agent IFF the state is ready (or unconditionally if require_ready=False)...",
      "source_type": "python",
      "name": "notify_if_ready",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-15",
      "tool_type": "dcf",
      "description": "Store workflow insights into long-term memory for downstream agents...",
      "source_type": "python",
      "name": "store_memory",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-16",
      "tool_type": "dcf",
      "description": "Append a workflow execution episode to the shared knowledge graph timeline...",
      "source_type": "python",
      "name": "append_graph_episode",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-17",
      "tool_type": "dcf",
      "description": "Atomically acquire a lease on a workflow state in the RedisJSON control-plane...",
      "source_type": "python",
      "name": "acquire_state_lease",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-18",
      "tool_type": "dcf",
      "description": "Atomically update a state's control-plane JSON and optionally write data-plane output...",
      "source_type": "python",
      "name": "update_workflow_control_plane",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-19",
      "tool_type": "dcf",
      "description": "Load a skill into a Letta agent: attach directives, tools, and data sources...",
      "source_type": "python",
      "name": "load_skill",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-20",
      "tool_type": "dcf",
      "description": "Unload a previously loaded skill from a Letta agent...",
      "source_type": "python",
      "name": "unload_skill",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    },
    {
      "id": "tool-21",
      "tool_type": "dcf",
      "description": "Invoke a loaded skill tool and capture its structured response for the workflow...",
      "source_type": "python",
      "name": "invoke_skill_tool",
      "tags": [
        "dcf"
      ],
      "json_schema": {... ...}
    }
  ],
  "metadata": {
    "revision_id": "c734cfc0d595"
  }
}
```

### 5.9 Docker Compose File For The Execution Environment

```
services:
  letta:
    image: letta/letta:latest
    entrypoint: ["/entrypoint.sh"]
    command: ["./letta/server/startup.sh"]
    ports:
      - "8283:8283"
    environment:
      - LETTA_DEBUG=False
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY}
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
    volumes:
      - ./requirements.txt:/app/requirements.txt
      - ./entrypoint.sh:/entrypoint.sh
      - ~/.letta+/pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8283/v1/health/ || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 20
      start_period: 10s

  redis:
    image: redis/redis-stack:latest
    ports:
      - "6379:6379"
    volumes:
      - ~/.letta+/redis-data:/data
    restart: unless-stopped

  neo4j:
    image: neo4j:5.26.9
    ports:
      - "7474:7474" # HTTP
      - "7687:7687" # Bolt
    environment:
      - NEO4J_AUTH=neo4j/demodemo
      - NEO4J_server_memory_heap_initial__size=512m
      - NEO4J_server_memory_heap_max__size=1G
      - NEO4J_server_memory_pagecache_size=512m
    volumes:
      - ~/.letta+/neo4j_data:/data
      - ~/.letta+/neo4j_logs:/logs
    healthcheck:
      test: [ "CMD", "wget", "-O", "/dev/null", "http://localhost:7474" ]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  graphiti-mcp:
    build:
      context: ./graphiti
      dockerfile: Dockerfile
    depends_on:
      neo4j:
        condition: service_healthy
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - MODEL_NAME=gpt-5-mini
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=demodemo
    ports:
      - "8000:8000"
    command: [ "uv", "run", "graphiti_mcp_server_v2.py", "--transport", "sse", "--host", "0.0.0.0" ]

  chroma-mcp:
    build:
      context: ./chroma
      dockerfile: Dockerfile
    ports:
      - "3002:3002"
    volumes:
      - ~/.letta+/chroma:/data
    environment:
      - CHROMA_CLIENT_TYPE=persistent
      - CHROMA_DATA_DIR=/data
      - CHROMA_OPENAI_API_KEY=${OPENAI_API_KEY}
    command: >
      --host 0.0.0.0 --port 3002 --pass-environment -- chroma-mcp --client-type persistent --data-dir /data
    restart: unless-stopped
```

### 5.10 Sample Skill Manifests

**1. Salesforce Integration Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "manifestId": "skill://salesforce-integration@2.1.0",
  "skillName": "salesforce-integration",
  "skillVersion": "2.1.0",
  "description": "Provides tools to query Salesforce for application and advisor data.",
  "tags": ["salesforce", "crm", "data"],
  "permissions": {
    "secrets": ["SALESFORCE_API_KEY"],
    "egress": "internet"
  },
  "skillDirectives": "Use this skill to retrieve data from Salesforce. Ensure queries are specific to minimize data transfer.",
  "requiredTools": [
    {
      "toolName": "get_applications_by_advisor",
      "description": "Finds loan application IDs assigned to an advisor within a specific date range.",
      "json_schema": {
        "name": "get_applications_by_advisor",
        "description": "Finds loan application IDs assigned to an advisor within a specific date range.",
        "parameters": {
          "type": "object",
          "properties": {
            "advisor_name": {
              "type": "string",
              "description": "The full name of the advisor."
            },
            "start_date": {
              "type": "string",
              "format": "date",
              "description": "The start of the date range (YYYY-MM-DD)."
            },
            "end_date": {
              "type": "string",
              "format": "date",
              "description": "The end of the date range (YYYY-MM-DD)."
            }
          },
          "required": ["advisor_name", "start_date", "end_date"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "salesforce/getApplicationsByAdvisor",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**2. Recording Management Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "b2c3d4e5-f6a7-8901-2345-67890abcdef1",
  "manifestId": "skill://recording-management@1.5.0",
  "skillName": "recording-management",
  "skillVersion": "1.5.0",
  "description": "Provides tools to retrieve call recordings from cloud storage.",
  "tags": ["audio", "s3", "storage"],
  "permissions": {
    "secrets": ["S3_ACCESS_KEY"],
    "egress": "internet"
  },
  "skillDirectives": "Use this skill to get URIs for call recordings based on application IDs.",
  "requiredTools": [
    {
      "toolName": "get_recordings_by_application_ids",
      "description": "Retrieves call recording URIs for a list of application IDs.",
      "json_schema": {
        "name": "get_recordings_by_application_ids",
        "description": "Retrieves call recording URIs for a list of application IDs.",
        "parameters": {
          "type": "object",
          "properties": {
            "application_ids": {
              "type": "array",
              "items": { "type": "string" },
              "description": "A list of application IDs."
            }
          },
          "required": ["application_ids"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "recordings/getByApplicationIds",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**3. Transcription Skill (Whisper)**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "c3d4e5f6-a7b8-9012-3456-7890abcdef12",
  "manifestId": "skill://whisper-transcribe@1.0.0",
  "skillName": "whisper-transcribe",
  "skillVersion": "1.0.0",
  "description": "Transcribes audio files to text using the Whisper backend.",
  "tags": ["transcription", "audio", "whisper"],
  "permissions": {
    "secrets": ["WHISPER_API_KEY"],
    "egress": "internet"
  },
  "skillDirectives": "Provide an audio file URI to receive a text transcription. This skill is preferred for high accuracy.",
  "requiredTools": [
    {
      "toolName": "transcribe_audio",
      "description": "Transcribes an audio file from a given URI.",
      "json_schema": {
        "name": "transcribe_audio",
        "description": "Transcribes an audio file from a given URI.",
        "parameters": {
          "type": "object",
          "properties": {
            "recording_uri": {
              "type": "string",
              "format": "uri",
              "description": "The URI of the audio file to transcribe."
            }
          },
          "required": ["recording_uri"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "transcription/whisper",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**4. Transcription Skill (AssemblyAI)**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "d4e5f6a7-b8c9-0123-4567-890abcdef123",
  "manifestId": "skill://assemblyai-transcribe@1.2.0",
  "skillName": "assemblyai-transcribe",
  "skillVersion": "1.2.0",
  "description": "Transcribes audio files to text using the AssemblyAI backend. Good for noisy environments and as a backup.",
  "tags": ["transcription", "audio", "assemblyai"],
  "permissions": {
    "secrets": ["ASSEMBLYAI_API_KEY"],
    "egress": "internet"
  },
  "skillDirectives": "Use this skill for transcription, especially if the primary Whisper service fails. Supports asynchronous transcription via webhooks.",
  "requiredTools": [
    {
      "toolName": "transcribe_audio_async",
      "description": "Transcribes an audio file from a given URI asynchronously.",
      "json_schema": {
        "name": "transcribe_audio_async",
        "description": "Transcribes an audio file from a given URI asynchronously.",
        "parameters": {
          "type": "object",
          "properties": {
            "recording_uri": {
              "type": "string",
              "format": "uri",
              "description": "The URI of the audio file to transcribe."
            },
            "webhook_url": {
              "type": "string",
              "format": "uri",
              "description": "The URL to send the transcript to upon completion."
            }
          },
          "required": ["recording_uri", "webhook_url"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "transcription/assemblyai",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**5. Diarization Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "e5f6a7b8-c9d0-1234-5678-90abcdef1234",
  "manifestId": "skill://gpt4o-diarize@1.0.0",
  "skillName": "gpt4o-diarize",
  "skillVersion": "1.0.0",
  "description": "Identifies different speakers and their utterances from a transcript.",
  "tags": ["diarization", "text", "gpt4o"],
  "permissions": {
    "secrets": ["OPENAI_API_KEY"],
    "egress": "internet"
  },
  "skillDirectives": "Provide a raw transcript to reformat it into a dialogue with speaker labels (e.g., 'Advisor', 'Customer').",
  "requiredTools": [
    {
      "toolName": "diarize_transcript",
      "description": "Processes a transcript to identify and label speakers.",
      "json_schema": {
        "name": "diarize_transcript",
        "description": "Processes a transcript to identify and label speakers.",
        "parameters": {
          "type": "object",
          "properties": {
            "transcript_text": {
              "type": "string",
              "description": "The full text of the conversation transcript."
            }
          },
          "required": ["transcript_text"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "diarization/gpt4o",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**6. Labelling & Segmentation Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "f6a7b8c9-d0e1-2345-6789-0abcdef12345",
  "manifestId": "skill://labelling-segmentation@1.2.0",
  "skillName": "labelling-segmentation",
  "skillVersion": "1.2.0",
  "description": "Separates a long transcript into smaller segments and labels them with given categories.",
  "tags": ["segmentation", "labelling", "text"],
  "permissions": {
    "secrets": ["OPENAI_API_KEY"],
    "egress": "internet"
  },
  "skillDirectives": "Provide a transcript and a taxonomy of labels to break the conversation into logical, categorized parts.",
  "requiredTools": [
    {
      "toolName": "segment_and_label",
      "description": "Applies a taxonomy of labels to segment a transcript.",
      "json_schema": {
        "name": "segment_and_label",
        "description": "Applies a taxonomy of labels to segment a transcript.",
        "parameters": {
          "type": "object",
          "properties": {
            "transcript_text": {
              "type": "string",
              "description": "The full text of the conversation transcript."
            },
            "taxonomy": {
              "type": "array",
              "items": { "type": "string" },
              "description": "A list of category labels to apply."
            }
          },
          "required": ["transcript_text", "taxonomy"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "segmentation/label",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**7. Sentiment Analysis Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "a7b8c9d0-e1f2-3456-7890-bcdef1234567",
  "manifestId": "skill://sentiment-analysis@1.2.0",
  "skillName": "sentiment-analysis",
  "skillVersion": "1.2.0",
  "description": "Identifies potential issues in a conversation, such as anxiety, vulnerability, or confusion.",
  "tags": ["sentiment", "analysis", "text"],
  "permissions": {
    "secrets": [],
    "egress": "none"
  },
  "skillDirectives": "Analyzes text for emotional tone and flags potential customer vulnerability or confusion.",
  "requiredTools": [
    {
      "toolName": "analyze_sentiment",
      "description": "Performs sentiment analysis on a block of text.",
      "json_schema": {
        "name": "analyze_sentiment",
        "description": "Performs sentiment analysis on a block of text.",
        "parameters": {
          "type": "object",
          "properties": {
            "text": {
              "type": "string",
              "description": "The text to analyze."
            }
          },
          "required": ["text"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "analysis/sentiment",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**8. Compliance Analysis Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "b8c9d0e1-f2a3-4567-8901-cdef12345678",
  "manifestId": "skill://compliance-analysis@1.3.0",
  "skillName": "compliance-analysis",
  "skillVersion": "1.3.0",
  "description": "Evaluates a transcript against a set of regulatory rules retrieved from a vector store.",
  "tags": ["compliance", "analysis", "rag"],
  "permissions": {
    "secrets": [],
    "egress": "none"
  },
  "skillDirectives": "Evaluates a transcript for compliance. Requires a `rule_set` identifier to fetch the correct rules from the vector store.",
  "requiredTools": [
    {
      "toolName": "evaluate_compliance",
      "description": "Evaluates a transcript against a specified set of compliance rules.",
      "json_schema": {
        "name": "evaluate_compliance",
        "description": "Evaluates a transcript against a specified set of compliance rules.",
        "parameters": {
          "type": "object",
          "properties": {
            "transcript_text": {
              "type": "string",
              "description": "The text of the transcript to evaluate."
            },
            "rule_set_id": {
              "type": "string",
              "description": "The identifier for the compliance rule set in the vector store."
            }
          },
          "required": ["transcript_text", "rule_set_id"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "analysis/compliance",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```

**9. Scoring Skill**

```json
{
  "manifestApiVersion": "v2.0.0",
  "skillPackageId": "c9d0e1f2-a3b4-5678-9012-def123456789",
  "manifestId": "skill://scoring@1.1.0",
  "skillName": "scoring",
  "skillVersion": "1.1.0",
  "description": "Calculates a transcript's overall QA score given sentiment and compliance results, based on a formula from the vector store.",
  "tags": ["scoring", "qa", "rag"],
  "permissions": {
    "secrets": [],
    "egress": "none"
  },
  "skillDirectives": "Calculates a final score. Requires the `formula_id` to fetch the correct scoring rubric from the vector store.",
  "requiredTools": [
    {
      "toolName": "calculate_score",
      "description": "Calculates a quality score based on analysis results and a scoring formula.",
      "json_schema": {
        "name": "calculate_score",
        "description": "Calculates a quality score based on analysis results and a scoring formula.",
        "parameters": {
          "type": "object",
          "properties": {
            "sentiment_report": {
              "type": "object",
              "description": "The output object from the sentiment analysis skill."
            },
            "compliance_verdicts": {
              "type": "array",
              "description": "The list of verdict objects from the compliance analysis skill."
            },
            "formula_id": {
              "type": "string",
              "description": "The identifier for the scoring formula in the vector store."
            }
          },
          "required": ["sentiment_report", "compliance_verdicts", "formula_id"]
        }
      },
      "definition": {
        "type": "mcp_server",
        "endpointUrl": "ws://mcp-server:8765",
        "operationId": "scoring/calculate",
        "openApiSpecUrl": "<http://mcp-server/openapi.json>"
      }
    }
  ]
}
```