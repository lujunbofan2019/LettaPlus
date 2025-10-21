# Advice Call Analysis End-to-End Worked Example

## 1. Introduction

This document provides a **worked example** that demonstrates how the Letta-based Planner and Worker agents deliver Selina Finance's *Advice Call Analysis* quality-assurance workflow. It narrates the full lifecycle across planning, capability discovery, skill orchestration, hybrid memory usage, and iterative improvement. Each phase is illustrated with representative artifacts—conversation turns, chain-of-thought (CoT) excerpts, workflow JSON, tool calls, memory updates, and knowledge-graph mutations.

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

    - **Knowledge Graph Query:** What is the historical performance of skills tagged with `compliance`, `sentiment`, `transcription`?
    - **Result:** The graph shows `skill://whisper-transcribe@1.0.0` has a 99% success rate, and `skill://assemblyai-transcribe@1.2.0` has a 99% success rate. I'll select the Whisper-based skill as the primary for now. The `compliance-analyzer` and `sentiment-analyzer` skills show 100% reliability.
3. **Workflow Construction:**
    - The user's request maps to a sequence of steps. I'll need skills for each step.
    - **Step 1 (Get Apps):** The `salesforce-integration` skill can find applications by advisor name and date range.
    - **Step 2 (Get Recordings):** The `recording-management` skill can retrieve audio files by IDs.
    - **Step 3 (Transcribe):** The `whisper-transcribe` skill is selected.
    - **Step 4 (Analyze):** The problem splits here. I can run sentiment and compliance analysis in parallel to be more efficient. This requires a `Parallel` state in my ASL workflow. I will use the `sentiment-analysis` and `compliance-analysis` skills.
    - **Step 5 (Score):** The `scoring` skill can take the outputs from the parallel branches and compute a final score.
    - I will now compile this logic into a `letta-asl-workflow` JSON structure.

### 2.3. Workflow Drafting

The Planner composes a Letta-ASL workflow that conforms to `schemas/letta_asl_workflow_schema_v2.2.0.json` and validates it via `validate_workflow`.

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

- **State document example** (`TranscribeRecording` just before completion):

    ```json
    {
      "status": "running",
      "attempts": 1,
      "lease": {
        "token": "lease-5d40",
        "owner_agent_id": "worker-qa-002",
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

*Table 1: Multi-Worker Execution Trace has been removed for clarity, as the narrative description above is more accurate.*

### 2.7. Hybrid Memory Activity and Context Management

- **Letta's Virtual Context Management:** Throughout the workflow, the Planner Agent's context window could become cluttered with task details. Letta's virtual context manager works in the background to prevent this. For instance, after the Planner confirms the initial workflow with the user, it might have a large memory block containing the full conversation and the proposed plan. Letta can automatically summarize this:
    - **Original Memory Block:** `(User Interaction) "Hi, I need to check..." + (Agent Response) "Of course... here is the workflow..." + (User Confirmation) "Yes, that looks perfect."`
    - **Summarized Block (moved to working memory):** `User [Compliance Manager] requested QA analysis for Alex Wong. I proposed a 5-step workflow including parallel analysis, which the user approved.`
    - This frees up the main context window for the agent to focus on the next task: initiating and monitoring the workflow execution.
- **Vector Store for Retrieval:** The `capability_standard_advice_call_analysis_v1.json` file is chunked, embedded, and stored in the vector database. The key is that the *description* ("A standard workflow to analyze an advisor's call recordings...") is part of the embedded text. This allows the Planner in Scenario 2 to find this workflow later by performing a **semantic search** with a query like "find a workflow for checking compliance on calls," rather than just indexing by tags.
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
2. **Memory & Capability Check:**
    - **Stage 1: Candidate Retrieval (Vector Store Query):** Search for capabilities regarding `advice call`, `product explanation`, `compliance`.
    - **Result:** The search returns `workflow_advice_call_analysis_v1.json`. **This is a capability match.** I can adapt this existing workflow.
    - [*Hypothetically*] **Stage 2: Candidate Ranking (Knowledge Graph Query):** If **Stage 1** returned multiple candidate capabilities, query the knowledge graph for those workflow IDs to understand their relationships and history. E.g., the knoledge graph reveals that `workflow_advice_call_analysis_v1.json` is a foundational workflow (it has `REFINEMENT_OF` edges pointing **away** from it) and has a high success rate. This confirms it's a reliable template to adapt.
    - **Analysis of User Need vs. Existing Workflow:** The user's request requires more granular processing. The existing workflow transcribes the whole call, but the user only wants specific parts. I will need to add diarization and segmentation steps. The sentiment and scoring steps are not needed.
3. **Workflow Refinement:**
    - I will use the `workflow_advice_call_analysis_v1.json` as a template.
    - **Modify Step 1 (Get Apps):** Remove the 'advisor name' filter to get all applications in the date range.
    - **Keep Steps 2 & 3:** `GetCallRecordings` and `TranscribeRecording` are still needed.
    - **Insert New Step 4 (Diarize):** I need to add a diarization step to separate speakers. The `gpt4o-diarize` skill is available and has a high success rate according to the Knowledge Graph.
    - **Insert New Step 5 (Segment):** I need to add a `labelling-segmentation` skill to extract the relevant conversation parts.
    - **Modify Final Step:** Replace the `ParallelAnalysis` and `CalculateScore` states with a single `ComplianceAnalysis` task that operates on the output of the new segmentation step.
    - I will now compile this new logic into a new, versioned workflow JSON file.

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