# Advice Call Analysis End-to-End Worked Example

## 1. Introduction

This document provides a **worked example** that demonstrates how the Letta-based Planner and Worker agents deliver Selina Finance's *Advice Call Analysis* quality-assurance workflow. It narrates the full lifecycle across planning, capability discovery, skill orchestration, hybrid memory usage, and iterative improvement. Each phase is illustrated with representative artifacts—conversation turns, chain-of-thought (CoT) excerpts, workflow JSON, tool calls, memory updates, and knowledge-graph mutations.

### 1.1. The Business Use Case: Advice Call Analysis

As a financial services provider regulated by the Financial Conduct Authority (FCA), Selina Finance must guarantee that every customer interaction complies with rigorous standards. Advisors and case managers conduct hundreds of phone calls daily, all captured as MP3 recordings. Legal & Compliance reviewers rely on those recordings to:

- Assess newly onboarded advisors against onboarding scripts and disclosure policies.
- Confirm that staff explain freshly launched products accurately after training.
- Evidence compliance with FCA regulations covering Consumer Duty, Mandatory Disclosures, and Financial Promotions.

Manual review is slow, hard to scale, and inconsistent. The goal is to delegate the end-to-end review to an autonomous AI agent that can understand the analyst’s intent, assemble the right capabilities, and execute the workflow reliably.

### 1.2. The AI-Powered Solution

Our system centers on a **Planner Agent** that orchestrates a pool of ephemeral **Worker Agents**. The Planner negotiates intent with the user, evaluates capability gaps, and composes workflows expressed in Letta’s ASL dialect. Workers execute each step by dynamically loading versioned **Skills**, which expose tools, prompts, and data adapters. Key skills for this use case include:

- **Salesforce Integration:** Queries advisor assignments, opportunities, and loan applications via REST APIs.
- **Recording Management:** Enumerates and downloads MP3 call recordings from secure object storage.
- **Transcription:** Converts audio to text; interchangeable backends include Whisper and AssemblyAI.
- **Diarization:** Separates speakers and timestamps dialogue; GPT-4o and Gemini 2.5 Pro variants exist.
- **Labelling & Segmentation:** Tags transcript spans with taxonomy labels (e.g., security check, product detail).
- **Sentiment Analysis:** Detects customer sentiment and conversational red flags.
- **Compliance Analysis:** Retrieves up-to-date regulatory rules from a vector store and evaluates transcripts.
- **Scoring:** Applies the active QA scoring rubric (also retrieved semantically from the vector store).

### 1.3. The System Diagram

[TODO: Lu will add the diagram and descriptions, AI assistant please ignore]

### 1.4. Scenarios to be Demonstrated

We will explore three scenarios that highlight the system’s core behaviours:

1. **Initial Capability Creation** – The Planner encounters a novel request, discovers a capability gap, co-designs a workflow with the user, and executes a trial run.
2. **Capability Refinement and Reuse** – The Planner retrieves an existing workflow via semantic search, adapts it to a product-specific audit, and publishes the refined version.
3. **Dynamic Failure Handling and Self-Healing** – A Worker recovers from a failing skill by loading an alternative, while the Planner evolves the master workflow after analysing knowledge-graph telemetry.

Throughout, we expose CoT snippets, workflow JSON, skill manifests, control-plane states, notifications, memory transitions, knowledge-graph mutations, and vector-store operations.

### 1.5. Prerequisites

- Letta, Redis, Chroma, Graphiti, and Neo4j services running locally.
- Vector store seeded with:
    - Regulatory rulebook chunks (`compliance_rules_v2024Q4.csv`).
    - QA scoring rubric (`qa_scoring_formula_v3.md`).
    - Skill manifests and previously approved workflows.
- Planner and Worker agent templates (Appendix 5.7/5.8) exposing tools:
    - **Planner:** `get_skillset`, `validate_skill_manifest`, `validate_workflow`, `create_workflow_control_plane`, `create_worker_agents`, `read_workflow_control_plane`, `notify_next_worker_agent`, `notify_if_ready`, `finalize_workflow`, `store_memory`, `append_graph_episode`.
    - **Worker:** `read_workflow_control_plane`, `acquire_state_lease`, `update_workflow_control_plane`, `load_skill`, `unload_skill`, `invoke_skill_tool`, `store_memory`, `append_graph_episode`, `notify_next_worker_agent`, `notify_if_ready`.
- MCP server hosting Recording Management and Salesforce proxy endpoints.
- Debug-level logging enabled for agent dialogues, tool payloads, memory writes, and knowledge-graph transactions.

---

## 2. Scenario 1: Initial Capability Creation

**Goal:** A compliance manager wants to review advice calls made by advisor **Alex Wong** between **2024‑07‑01** and **2024‑07‑07**, assessing compliance, sentiment, and QA scores.

### 2.1. Conversation Timeline

> **Turn 1 — User**  
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

> **Turn 2 — Planner**  
> "Of course. To confirm, should I check compliance with the standard script, assess customer sentiment, and produce an overall score?"
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Clarify evaluation axes before designing workflow.
> - Prompt user for scoring rubric confirmation.
>
> </details>

> **Turn 3 — User**  
> "Yes. Please use the existing QA scorecard."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - QA scorecard likely stored in vector store (`qa_scoring_formula_v3`).
> - Need skills: Salesforce lookup, recording retrieval, transcription, sentiment, compliance, scoring.
>
> </details>

> **Turn 4 — Planner**  
> "Great. I'll source Alex's recordings for last week, transcribe them, analyse sentiment and compliance in parallel, and then compute the QA score. I'll run a single-call pilot first; if that looks good, I can scale to the whole set."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Confirmed plan; now evaluate capability catalog.
> - Expect capability gap (no prior workflow).
>
> </details>

### 2.2. Capability Assessment & Gap Detection

1. Planner invokes `get_skillset` → receives registry listing required skills but no orchestrated workflow.
2. Executes semantic vector search (`search_embeddings(query="Alex Wong advice call analysis")`) → **no matching workflow**. Capability gap detected.
3. Planner writes a working-memory block in the active context window documenting the gap. Letta’s runtime flags the block for archival.
4. Planner queries the knowledge graph for historical success rates of `skill://whisper-transcribe@1.0.0`, `skill://sentiment-analysis@1.2.0`, and `skill://compliance-analysis@1.3.0`; reliability ≥ 0.98, suitable for initial draft.

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
      "ParallelAnalysis.SentimentAnalysis",
      "ParallelAnalysis.ComplianceAnalysis",
      "CalculateScore"
    ],
    "agents": {
      "planner": "agent://planner@1.0.0",
      "worker_pool": "agent_template_worker@1.0.0"
    },
    "skills": {
      "GetApplicationIDs": ["skill://salesforce-integration@2.1.0"],
      "GetCallRecordings": ["skill://recording-management@1.5.0"],
      "TranscribeRecording": ["skill://whisper-transcribe@1.0.0"],
      "ParallelAnalysis.SentimentAnalysis": ["skill://sentiment-analysis@1.2.0"],
      "ParallelAnalysis.ComplianceAnalysis": ["skill://compliance-analysis@1.3.0"],
      "CalculateScore": ["skill://scoring@1.1.0"]
    },
    "deps": {
      "GetApplicationIDs": {"upstream": [], "downstream": ["GetCallRecordings"]},
      "GetCallRecordings": {"upstream": ["GetApplicationIDs"], "downstream": ["TranscribeRecording"]},
      "TranscribeRecording": {"upstream": ["GetCallRecordings"], "downstream": ["ParallelAnalysis"]},
      "ParallelAnalysis.SentimentAnalysis": {"upstream": ["TranscribeRecording"], "downstream": ["CalculateScore"]},
      "ParallelAnalysis.ComplianceAnalysis": {"upstream": ["TranscribeRecording"], "downstream": ["CalculateScore"]},
      "CalculateScore": {"upstream": ["ParallelAnalysis.SentimentAnalysis", "ParallelAnalysis.ComplianceAnalysis"], "downstream": []}
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

### 2.6. Multi-Worker Execution Trace

| Phase | Worker | Actions |
|-------|--------|---------|
| 1. Lease Acquisition | `worker-qa-001` | `acquire_state_lease` for `GetApplicationIDs`; loads Salesforce skill; invokes tool; writes result to control plane; unloads skill; notifies Planner. |
| 2. Recording Retrieval | `worker-qa-002` | Loads Recording Management skill; streams manifest; persists artifact `artifact://recordings/APP-49201.json`; updates state to `done`. |
| 3. Transcription | `worker-qa-003` | Loads Whisper skill; transcribes audio; stores transcript chunks in working memory; posts artifact `artifact://transcripts/APP-49201.txt`; releases lease. |
| 4a. Sentiment Branch | `worker-qa-004` | Spawned automatically when parallel state opens; loads Sentiment skill; produces report; updates branch state to `done`. |
| 4b. Compliance Branch | `worker-qa-005` | Loads Compliance skill; pulls `compliance_rules_v2024Q4` via semantic pointer; records verdicts; updates knowledge graph with `NON_COMPLIANT_IN` edge. |
| 5. Scoring | `worker-qa-006` | Loads Scoring skill; retrieves `qa_scoring_formula_v3` vector document via semantic fetch; generates final QA score artifact. |

Parallel branches 4a and 4b execute concurrently; the control plane waits for both to reach `done` before activating `CalculateScore`.

### 2.7. Hybrid Memory Activity

- **Context Window → Working Memory:** During each step, Workers append concise summaries (e.g., Salesforce IDs retrieved) into the context window for the Planner. Letta automatically tags these blocks with TTLs.
- **Automatic Summarisation:** Once the conversation exceeds 6k tokens, Letta’s runtime compresses earlier turns into a working-memory summary block to avoid overflow.
- **Sleep-Time Agent:** After the trial run completes, the Planner’s paired sleep-time agent activates during idle cycles. It:
    1. Consolidates transient working-memory blocks into an archival summary (“Created and validated Standard Advice Call Analysis workflow …”).
    2. Moves verbose artifacts (full transcripts) from the Planner’s context window into archival storage, replacing them with vector-store URIs.
    3. Writes an analytics note into the knowledge graph, linking the workflow execution to the advisor, call, and rules touched.
- **Vector Store:** The new workflow is embedded (`embed(workflow_json)`) and stored via `vector_store.upsert`, enabling later retrieval through semantic search rather than direct indexing by ID.

---

## 3. Scenario 2: Workflow Refinement and Reuse

**Goal:** A training manager wants to confirm that advisors explain the **HELOC 2.0** product correctly in calls since **2024‑08‑01**, focusing solely on the advisor’s product narration.

### 3.1. Conversation Timeline

> **Turn 1 — User**  
> "I need to check if advisors are explaining the new HELOC 2.0 product correctly in their calls since the start of the month."
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Trigger semantic search in workflow memory for "advice call analysis".
> - Evaluate if existing workflow matches narrower intent.
>
> </details>

> **Turn 2 — Planner**  
> "I have a reusable Advice Call Analysis workflow. Shall I adapt it to isolate the advisor’s product explanation and run a compliance check just on that section?"
>
> <details>
> <summary>Planner CoT Snapshot</summary>
>
> - Candidate workflow: `Standard Advice Call Analysis` (v1.0.0).
> - Need diarization + segmentation to isolate advisor speech.
>
> </details>

> **Turn 3 — User**  
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

### 3.2. Semantic Retrieval and Adaptation

1. Planner issues `vector_store.similarity_search(query_embedding(advisor_product_focus))` → highest score: `workflow_advice_call_analysis_v1.json`.
2. Planner clones workflow structure in CoT, marking modifications (diarization, segmentation, targeted compliance).
3. Draft updated workflow, validate via schema, and version as `workflow_product_explanation_compliance_v1.json`.

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
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
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
        "AgentBinding": {
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
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
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
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
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
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
          "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
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

### 3.3. Memory and Knowledge Updates

- **Vector Store:** Refined workflow embedded and upserted with metadata `{"topic": "product_clarity", "origin": "c4b1a2e8-..."}`. Subsequent semantic searches for "product explanation compliance" rank it highly.
- **Planner Archival Memory:** Sleep-time agent summarises adaptation outcome: “Refined Standard Advice Call Analysis into Product Explanation Compliance Check; added diarization + segmentation; removed sentiment/scoring.”
- **Knowledge Graph:** Adds node `Workflow:a8d3b1c9...` with `REFINEMENT_OF` edge pointing to the original workflow. Advisor-product episodes link to `Product:HELOC 2.0` entity, enabling future analytics.

---

## 4. Scenario 3: Dynamic Failure Handling and Self-Healing

**Goal:** During a later execution of the Standard workflow, the Whisper transcription skill begins timing out. Workers must recover in-flight, and the Planner must evolve the workflow for future reliability.

### 4.1. Failure Event and Control Plane Trace

When `worker-qa-011` processes `TranscribeRecording`, the Whisper backend times out after 120 seconds. The control-plane state transitions as follows:

```json
{
  "status": "failed",
  "attempts": 1,
  "lease": {
    "token": "lease-77fa",
    "owner_agent_id": "worker-qa-011",
    "ts": "2024-08-12T14:03:32Z",
    "ttl_s": 0
  },
  "started_at": "2024-08-12T14:01:30Z",
  "finished_at": "2024-08-12T14:03:32Z",
  "last_error": "TimeoutError: Whisper transcription exceeded 120s SLA"
}
```

The worker emits `notify_if_ready(status="needs_attention")`, and the Planner inspects the failure payload.

### 4.2. Worker Recovery CoT

<details>
<summary>Worker CoT Highlights</summary>

1. **Classify Error** – Timeout indicates transient or degraded service; retry with alternative backend rather than abort workflow.
2. **Discover Alternative Skill** – Query vector store for `transcription` skills excluding Whisper. Top hit: `skill://assemblyai-transcribe@1.2.0` (success rate 0.99 per knowledge graph).
3. **Swap Skills** –
    - `unload_skill("skill://whisper-transcribe@1.0.0")`
    - `load_skill("skill://assemblyai-transcribe@1.2.0")`
4. **Retry** – Reinvoke transcription tool (`transcribe.async`) with webhook callback. Poll until job completes; update control plane state to `running` then `done` with new artifact pointer.

</details>

The updated control-plane state after recovery:

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
  "started_at": "2024-08-12T14:01:30Z",
  "finished_at": "2024-08-12T14:07:05Z",
  "last_error": "TimeoutError: Whisper transcription exceeded 120s SLA"
}
```

### 4.3. Post-Run Learning Loop

1. **Archival Memory Entry** – Worker stores remediation summary, later compressed by sleep-time agent:

   ```json
   {
     "type": "workflow_update_candidate",
     "workflow_id": "c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21",
     "observation": "Whisper transcription timed out; AssemblyAI fallback succeeded.",
     "timestamp": "2024-08-12T14:07:10Z"
   }
   ```

2. **Sleep-Time Agent Processing** – During the next idle window, the Planner’s sleep-time companion:
    - Aggregates multiple timeout incidents.
    - Writes knowledge-graph updates: increments `n_failures` on edge `(Workflow→Skill)` for Whisper; adds `USED_SKILL` edge for AssemblyAI with latency metrics.
    - Generates a recommendation memory block: “Failure rate for Whisper transcription is 7% over last 20 runs; suggest workflow revision.”

3. **Planner Self-Healing** – When the Planner is asked to rerun the workflow:
    - Executes pre-flight reliability check using knowledge-graph query (`MATCH (w:Workflow {id: ...})-[:USES]->(s:Skill)`).
    - Detects Whisper failure rate > threshold (5%).
    - Drafts `workflow_advice_call_analysis_v1.0.1.json` swapping the transcription skill to AssemblyAI and updates `skill_imports` accordingly.
    - Validates, stores new version, and announces change to stakeholders.

4. **Updated Workflow Snippet** –

   ```json
   "TranscribeRecording": {
     "Type": "Task",
     "Comment": "Transcribe MP3 audio using AssemblyAI backend with async polling.",
     "AgentBinding": {
       "agent_template_ref": {"name": "agent_template_worker@1.0.0"},
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

5. **Knowledge Graph Evolution** – Adds edge `(:Workflow {version: "1.0.1"})-[:REPLACES]->(:Workflow {version: "1.0.0"})`, ensuring provenance. Reliability metrics for AssemblyAI skill propagate into future planning decisions.

---

## 5. Evidence Checklist

| Phase | Evidence | Storage Location |
|-------|----------|------------------|
| Capability Gap Detection | Archival memory block `capability_gap` | Redis archival memory export |
| Workflow Validation | Control-plane meta/state documents | Redis (`cp:meta:*`, `cp:state:*`) |
| Tool Execution | Tool payload logs per skill | `logs/tools/*.jsonl` |
| Transcript Artifact | Text file reference | `artifact://transcripts/APP-49201.txt` (vector store pointer) |
| Sentiment & Compliance Verdicts | Knowledge-graph relations | `graphiti/export/episodes/AdviceCallAnalysisTrial.json` |
| Workflow Persistence | Embedded workflow documents | Chroma collection `workflows` |
| Workflow Refinement | `REFINEMENT_OF` edge + new workflow version | Neo4j graph snapshot |
| Skill Swap History | `workflow_update_candidate` → `workflow_update` memory + KG metrics | Archival memory + Neo4j |

To replay the scenario, run the Planner with debug logging, follow the conversation scripts, and verify that each artifact above is produced. Subsequent runs should demonstrate semantic reuse, adaptive planning, and automated healing of degraded capabilities.

---

## 6. Further Extensions

- **Concurrent Batch Runs:** Launch multiple Worker agents to process different recordings simultaneously; confirm leases prevent conflicts.
- **Cross-Agent Collaboration:** Introduce a Compliance Specialist agent that reviews borderline cases before final approval.
- **Human-in-the-Loop Overrides:** Allow reviewers to reject automated scores, triggering workflow branches captured in the knowledge graph.
- **Automated Skill Packaging:** When planners detect repeated CoT reasoning, promote it into reusable skills, closing the Dynamic Capability Framework loop.
- **Reliability Dashboards:** Feed knowledge-graph metrics into BI tools to monitor success rates, latency, and failure trends across skills.

This worked example demonstrates how Selina Finance’s hybrid-memory, workflow-driven agent ecosystem can plan, execute, learn, and evolve Advice Call Analysis capabilities autonomously.