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

1.  **Initial Capability Creation.** We will show how the Planner agent interacts with a user to understand a new request, identifies a "capability gap" (the lack of a pre-existing workflow), collaboratively designs a new workflow, and executes a test run.
2.  **Capability Refinement and Reuse.** We will demonstrate how the agent can retrieve the previously saved workflow, adapt it to a new, more specific user request, and save the modified version as a new, reusable asset.
3.  **Dynamic Failure Handling and Self-Healing.** We will simulate a runtime tool failure and show how a worker agent can dynamically swap to a substitute skill (by unloading the designated one, and loading an alternative one). We will also show how the system records these failures in its knowledge graph, allowing the Planner to proactively "heal" the master workflow for future runs, demonstrating self-evolution.

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

### 2.1. The Conversation: Defining the Need

| Speaker | Message |
| :--- | :--- |
| **USER** | "Hi, I need to check the quality of advice calls made by Alex Wong last week. Can you help me analyze them?" |
| **PLANNER** | "Of course. To ensure I get this right, could you clarify what 'analyzing them' involves? For example, are you interested in compliance with specific rules, customer sentiment, or something else?" |
| **USER** | "Good question. I need to know if he's following the standard script, so compliance is key. I'm also interested in the customer's sentiment during the calls. Finally, I'd like an overall quality score for each call." |
| **PLANNER** | "Thank you. That's very clear. Based on your request, here is the workflow I propose:<br>1.  Find all loan application IDs assigned to 'Alex Wong' in Salesforce from last week.<br>2.  For those applications, retrieve the associated call recordings.<br>3.  For each recording, transcribe it from audio to text.<br>4.  Once transcribed, I will run two analyses in parallel:<br>    *   One for customer sentiment.<br>    *   One for compliance against our standard rules.<br>5.  Finally, I will calculate an overall quality score based on the results of the sentiment and compliance checks.<br><br>Does this plan meet your needs?" |
| **USER** | "Yes, that looks perfect." |

### 2.2. The Agent's Internal Monologue (CoT)

> 1.  **Intent Analysis:**
      >     - The user wants to perform "Advice Call Analysis" for a specific advisor and date range.
>     - The key success metrics are **compliance**, **sentiment**, and a final **score**.
>
> 2.  **Memory & Capability Check:**
      >     - **Vector Store Query:** Search for existing capabilities with keywords: `advice call`, `quality assurance`, `compliance analysis`.
              *   **Result:** No existing capabilities found. **This is a capability gap.** I need to construct a new workflow JSON file. Planner records a **capability gap** memory block:

    ```json
    {
      "type": "capability_gap",
      "summary": "Advice Call Analysis workflow missing; need to orchestrate Salesforce lookup, recording fetch, transcription, sentiment, compliance, scoring.",
      "tags": ["qa", "advisor_quality", "workflow:new"]
    }
    ```

    *   **Knowledge Graph Query:** What is the historical performance of skills tagged with `compliance`, `sentiment`, `transcription`?
    *   **Result:** The graph shows `skill://whisper-transcribe@1.0.0` has a 99% success rate, and `skill://assemblyai-transcribe@1.2.0` has a 99% success rate. I'll select the Whisper-based skill as the primary for now. The `compliance-analyzer` and `sentiment-analyzer` skills show 100% reliability.

3.  **Workflow Construction:**
    *   The user's request maps to a sequence of steps. I'll need skills for each step.
    *   **Step 1 (Get Apps):** The `salesforce-integration` skill can find applications by advisor name and date range.
    *   **Step 2 (Get Recordings):** The `recording-management` skill can retrieve audio files by IDs.
    *   **Step 3 (Transcribe):** The `whisper-transcribe` skill is selected.
    *   **Step 4 (Analyze):** The problem splits here. I can run sentiment and compliance analysis in parallel to be more efficient. This requires a `Parallel` state in my ASL workflow. I will use the `sentiment-analysis` and `compliance-analysis` skills.
    *   **Step 5 (Score):** The `scoring` skill can take the outputs from the parallel branches and compute a final score.
    *   I will now compile this logic into a `letta-asl-workflow` JSON structure.

### 2.3. The Generated Workflow Artifact

The Planner Agent generates the following `capability_standard_advice_call_analysis_v1.json` file.

```json
{
  "workflow_schema_version": "2.2.0",
  "workflow_id": "c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21",
  "workflow_name": "Standard Advice Call Analysis",
  "description": "A standard workflow to analyze an advisor's call recordings for compliance, sentiment, and a final quality score.",
  "version": "1.0.0",
  "author": "planner-agent-7b",
  "created_at": "2024-07-15T10:00:00Z",
  "tags": ["qa", "compliance", "sentiment", "scoring"],
  "asl": {
    "Comment": "A workflow to analyze an advisor's call recordings for compliance, sentiment, and a final quality score.",
    "StartAt": "GetApplicationIDs",
    "States": {
      "GetApplicationIDs": {
        "Type": "Task",
        "Comment": "Find loan application IDs from Salesforce given an advisor's name and date range.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://salesforce-integration@2.1.0"]
        },
        "Next": "GetCallRecordings"
      },
      "GetCallRecordings": {
        "Type": "Task",
        "Comment": "Retrieve call recordings for the given application IDs.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://recording-management@1.5.0"]
        },
        "Next": "TranscribeRecording"
      },
      "TranscribeRecording": {
        "Type": "Task",
        "Comment": "Transcribe the audio file to text using the Whisper-based skill.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://whisper-transcribe@1.0.0"]
        },
        "Next": "ParallelAnalysis"
      },
      "ParallelAnalysis": {
        "Type": "Parallel",
        "Comment": "Run sentiment and compliance analysis concurrently.",
        "Branches": [
          {
            "StartAt": "SentimentAnalysis",
            "States": {
              "SentimentAnalysis": {
                "Type": "Task",
                "AgentBinding": {
                  "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
                  "skills": ["skill://sentiment-analysis@1.0.0"]
                },
                "End": true
              }
            }
          },
          {
            "StartAt": "ComplianceAnalysis",
            "States": {
              "ComplianceAnalysis": {
                "Type": "Task",
                "AgentBinding": {
                  "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
                  "skills": ["skill://compliance-analysis@1.3.0"]
                },
                "End": true
              }
            }
          }
        ],
        "Next": "CalculateScore"
      },
      "CalculateScore": {
        "Type": "Task",
        "Comment": "Calculate a final score based on the parallel analysis results.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://scoring@1.1.0"]
        },
        "End": true
      }
    }
  }
}
```

### 2.4. Test Drive & Memory Updates

The Planner Agent now executes this workflow as a test drive on a single call recording.

#### 2.4.1. Control Plane Seeding

First, the Planner calls `create_workflow_control_plane` and `create_worker_agents`. This seeds Redis with the necessary objects to manage the workflow's execution.

- **Control Plane Meta Object:** A single meta object is created to define the workflow's structure and dependencies.
  ```json
  // Redis Key: cp:wf:c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21:meta
  {
    "workflow_id": "c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21",
    "start_at": "GetApplicationIDs",
    "states": ["GetApplicationIDs", "GetCallRecordings", "TranscribeRecording", "ParallelAnalysis", "SentimentAnalysis", "ComplianceAnalysis", "CalculateScore"],
    "deps": {
      "GetApplicationIDs": {"upstream": [], "downstream": ["GetCallRecordings"]},
      "GetCallRecordings": {"upstream": ["GetApplicationIDs"], "downstream": ["TranscribeRecording"]},
      "TranscribeRecording": {"upstream": ["GetCallRecordings"], "downstream": ["ParallelAnalysis"]},
      "ParallelAnalysis": {"upstream": ["TranscribeRecording"], "downstream": ["CalculateScore"]},
      "SentimentAnalysis": {"upstream": ["ParallelAnalysis"], "downstream": []},
      "ComplianceAnalysis": {"upstream": ["ParallelAnalysis"], "downstream": []},
      "CalculateScore": {"upstream": ["ParallelAnalysis"], "downstream": []}
    }
  }
  ```
- **Control Plane State Objects:** A separate state object is created for *each* task defined in the ASL. Each starts in `pending` status. For example:
  ```json
  // Redis Key: cp:wf:c4b1...:state:GetApplicationIDs
  {
    "status": "pending",
    "attempts": 0,
    "lease": {"token": null, "owner_agent_id": null, "ts": null, "ttl_s": 300},
    "started_at": null,
    "finished_at": null,
    "last_error": null
  }
  ```

#### 2.4.2. Execution Flow: A Choreography of Workers

The Planner kicks off the workflow by calling `notify_next_worker_agent`. This begins a choreographed sequence of operations, with ephemeral worker agents performing each step.

1.  **GetApplicationIDs:**
    - `Worker-1` receives the notification, acquires the lease for this state, and loads the `salesforce-integration` skill.
    - It calls the tool with `{advisor_name: "Alex Wong", ...}` and receives `{"ids": ["APP-49201"]}`.
    - It writes this output to the data plane, updates its state to `done`, releases the lease, and calls `notify_next_worker_agent` for `GetCallRecordings`.

2.  **GetCallRecordings:**
    - `Worker-2` is activated, acquires the lease for `GetCallRecordings`, and loads the `recording-management` skill.
    - It reads the application ID from the data plane and retrieves the call recording URI.
    - It updates its state, releases the lease, and notifies the `TranscribeRecording` worker.

3.  **TranscribeRecording:**
    - `Worker-3` acquires the lease and loads the `whisper-transcribe` skill.
    - It transcribes the audio, writes the full transcript text to the data plane, updates its state, releases its lease, and notifies the `ParallelAnalysis` state.

4.  **Parallel Analysis:**
    - The `ParallelAnalysis` state acts as a fork. It immediately notifies two *new* workers concurrently: `Worker-4` for `SentimentAnalysis` and `Worker-5` for `ComplianceAnalysis`.
    - **`Worker-4 (Sentiment)`:** Acquires the lease for its state, loads the `sentiment-analysis` skill, reads the transcript from the data plane, performs its analysis, and writes its result (`{ "overall": "Neutral", ...}`). It updates its state to `done` and releases its lease.
    - **`Worker-5 (Compliance)`:** Simultaneously, it acquires the lease for its state, loads the `compliance-analysis` skill, reads the transcript, and writes its result (`{"verdicts": [...]}`). It updates its state to `done` and releases its lease.
    - Both workers, upon completion, call `notify_if_ready` for the downstream `CalculateScore` state.

5.  **CalculateScore:**
    - The `notify_if_ready` call from the last parallel worker to finish triggers the notification for `Worker-6`.
    - `Worker-6` acquires the lease, loads the `scoring` skill, reads the outputs from *both* the sentiment and compliance branches, calculates the final score, and writes it to the data plane.
    - It updates its state to `done` and releases the lease. The workflow is now complete.

#### 2.4.3. Hybrid Memory and Context Management

- **Letta's Virtual Context Management:** Throughout the workflow, the Planner Agent's context window could become cluttered with task details. Letta's virtual context manager works in the background to prevent this. For instance, after the Planner confirms the initial workflow with the user, it might have a large memory block containing the full conversation and the proposed plan. Letta can automatically summarize this:
    - **Original Memory Block:** `(User Interaction) "Hi, I need to check..." + (Agent Response) "Of course... here is the workflow..." + (User Confirmation) "Yes, that looks perfect."`
    - **Summarized Block (moved to working memory):** `User [Compliance Manager] requested QA analysis for Alex Wong. I proposed a 5-step workflow including parallel analysis, which the user approved.`
    - This frees up the main context window for the agent to focus on the next task: initiating and monitoring the workflow execution.

- **Vector Store for Retrieval:** The `capability_standard_advice_call_analysis_v1.json` file is chunked, embedded, and stored in the vector database. The key is that the *description* ("A standard workflow to analyze an advisor's call recordings...") is part of the embedded text. This allows the Planner in Scenario 2 to find this workflow later by performing a **semantic search** with a query like "find a workflow for checking compliance on calls," rather than just indexing by tags.

- **The Sleep-Time Agent:** After the user interaction is complete, the Planner agent might become idle. This is when its companion **sleep-time agent** activates. This specialized agent performs offline optimization tasks without interrupting the main agent. It can:
    1.  Review the Planner's recent working memory.
    2.  Identify valuable, long-term memories (like the creation of a new, successful workflow).
    3.  Generate structured data from these memories.
    4.  Call the `append_graph_episode` tool to update the Knowledge Graph with new nodes and relationships (e.g., creating the `WorkflowExecution` node and linking it to the skills used). This offloads the expensive task of graph updates from the main interactive loop.

---

## 3. Scenario 2: Workflow Refinement and Reuse

This scenario demonstrates how the system reuses and adapts existing workflows to solve similar, but distinct, problems.

**Goal:** A training manager wants to verify that all advisors are correctly explaining a new loan product, "HELOC 2.0," following a recent training course.

### 3.1. The Conversation: A More Specific Need

| Speaker | Message |
| :--- | :--- |
| **USER** | "I need to check if our advisors are explaining the new 'HELOC 2.0' product correctly in their calls since the start of the month." |
| **PLANNER** | "I can help with that. I have an existing capability for general advice call analysis. To ensure I tailor it correctly for your needs, could you confirm if you need a full compliance and sentiment analysis, or something more specific to the product explanation?" |
| **USER** | "I don't need sentiment or a general score. I only care about the parts of the conversation where the advisor is actually describing the product and its terms. I need to know if that specific part of the script is compliant." |
| **PLANNER** | "Understood. So, the focus is on compliance within specific segments of the conversation. Here is the refined workflow I propose:<br>1. Find all loan application IDs since the start of the month.<br>2. Retrieve all associated call recordings.<br>3. Transcribe the recordings to text.<br>4. **New Step:** Identify the different speakers in the transcript (diarization) to isolate the advisor's speech.<br>5. **New Step:** Label the transcript to identify and extract only the 'product detail' and 'offer explanation' segments.<br>6. Run a compliance analysis *only* on those extracted segments.<br>7. Report the result as a simple pass or fail.<br><br>How does this sound?" |
| **USER** | "That is exactly what I need. Perfect." |

### 3.2. The Agent's Internal Monologue (CoT)

> 1.  **Intent Analysis:**
      >     - The user wants to check for compliance on a *specific topic* ("HELOC 2.0" explanation) across all advisors.
>     - This is different from the previous general quality check.

2.  **Memory & Capability Check:**
    *   **Vector Store Query:** Search for capabilities with keywords: `advice call`, `product explanation`, `compliance`.
    *   **Result:** The search returns `workflow_advice_call_analysis_v1.json` as a strong candidate. **This is a capability match.** I can adapt this existing workflow.
    *   **Analysis of User Need vs. Existing Workflow:** The user's request requires more granular processing. The existing workflow transcribes the whole call, but the user only wants specific parts. I will need to add diarization and segmentation steps. The sentiment and scoring steps are not needed.

3.  **Workflow Refinement:**
    *   I will use the `workflow_advice_call_analysis_v1.json` as a template.
    *   **Modify Step 1 (Get Apps):** Remove the 'advisor name' filter to get all applications in the date range.
    *   **Keep Steps 2 & 3:** `GetCallRecordings` and `TranscribeRecording` are still needed.
    *   **Insert New Step 4 (Diarize):** I need to add a diarization step to separate speakers. The `gpt4o-diarize` skill is available and has a high success rate according to the Knowledge Graph.
    *   **Insert New Step 5 (Segment):** I need to add a `labelling-segmentation` skill to extract the relevant conversation parts.
    *   **Modify Final Step:** Replace the `ParallelAnalysis` and `CalculateScore` states with a single `ComplianceAnalysis` task that operates on the output of the new segmentation step.
    *   I will now compile this new logic into a new, versioned workflow JSON file.

### 3.3. The Generated Workflow Artifact

The Planner Agent generates `capability_product_explanation_compliance_v1.json`.

```json
{
  "workflow_schema_version": "2.2.0",
  "workflow_id": "a8d3b1c9-9e8a-4f2b-9e3d-7c1b0d8a4b21",
  "workflow_name": "Product Explanation Compliance Check",
  "description": "A specialized workflow to analyze if a new product is being explained correctly by advisors.",
  "version": "1.0.0",
  "author": "planner-agent-7b",
  "created_at": "2024-07-16T14:00:00Z",
  "tags": ["training", "compliance", "diarization", "segmentation"],
  "asl": {
    "Comment": "A specialized workflow to analyze if a new product is being explained correctly by advisors.",
    "StartAt": "GetApplicationIDs",
    "States": {
      "GetApplicationIDs": {
        "Type": "Task",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://salesforce-integration@2.1.0"]
        },
        "Next": "GetCallRecordings"
      },
      "GetCallRecordings": {
        "Type": "Task",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://recording-management@1.5.0"]
        },
        "Next": "TranscribeRecording"
      },
      "TranscribeRecording": {
        "Type": "Task",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://whisper-transcribe@1.0.0"]
        },
        "Next": "DiarizeTranscript"
      },
      "DiarizeTranscript": {
        "Type": "Task",
        "Comment": "Identify speakers in the transcript.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://gpt4o-diarize@1.0.0"]
        },
        "Next": "SegmentAndLabel"
      },
      "SegmentAndLabel": {
        "Type": "Task",
        "Comment": "Extract only the 'product detail' and 'offer explanation' segments.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://labelling-segmentation@1.2.0"]
        },
        "Next": "TargetedComplianceAnalysis"
      },
      "TargetedComplianceAnalysis": {
        "Type": "Task",
        "Comment": "Run compliance check only on the extracted segments.",
        "AgentBinding": {
          "agent_template_ref": {"name": "worker-agent-template", "version": "1.0"},
          "skills": ["skill://compliance-analysis@1.3.0"]
        },
        "End": true
      }
    }
  }
}
```

### 3.4. Memory Updates

[TODO: AI assistant please note that the Vector store mechanism may be wrong again - it should support semantic search rather than indexing]

- **Vector Store:** The new workflow `workflow_product_explanation_compliance_v1.json` is indexed and stored with tags `["product explanation", "compliance", "diarization", "segmentation"]`.
- **Knowledge Graph:**
    - A new `Workflow` node is created for `a8d3b1c9...`.
    - An edge `REFINEMENT_OF` is created, linking this new workflow node back to the `workflow_advice_call_analysis_v1.json` node, explicitly recording its origin.
- **Memory Blocks:** A new entry is added to the Planner's archival memory: "Adapted the 'Standard Advice Call Analysis' workflow to create a new, more specific 'Product Explanation Compliance Check' workflow for user [Training Manager's ID]. This involved adding diarization and segmentation steps and removing sentiment/scoring."

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
  // Redis Key: cp:wf:c4b1...:state:TranscribeRecording
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
  // Redis Key: cp:wf:c4b1...:state:TranscribeRecording
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

> 1.  **Error Detected:**
      >     - The `whisper-transcribe` skill failed with a `TimeoutError`.
>     - This is a recoverable network/service issue, not a fatal data error. My primary objective is to complete the task.
>
> 2.  **Identify Alternatives (Dynamic Skill Re-evaluation):**
      >     - I need a skill that can fulfill the `transcription` task.
>     - I will query the Vector Store for skill manifests with `transcription` keyword that are *not* the one that just failed.
>     - **Result:** The repository returns `skill://assemblyai-transcribe@1.2.0`.
>
> 3.  **Attempt Recovery (Skill Swapping):**
      >     - **Unload the failed skill:** I will call `unload_skill("skill://whisper-transcribe@1.0.0", ...)` to remove it from my context. This prevents any further attempts with the failing tool.
>     - **Load the alternative skill:** I will call `load_skill("skill://assemblyai-transcribe@1.2.0", ...)` to dynamically acquire the new skill.
>     - **Retry the task:** I will re-run the transcription logic using the newly loaded AssemblyAI skill.

4.  **Successful Recovery:** The AssemblyAI skill succeeds. The worker proceeds to write the output to the data plane, release its lease, and notify the downstream workers, allowing the workflow to continue.

### 4.3. Post-Run Learning: The Planner's Self-Healing Process

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

A week later, after several more runs have experienced similar timeouts, the Planner Agent is tasked with another "Standard Advice Call Analysis."

- **Planner Agent's Monologue (Proactive Healing):**
    1.  **Pre-flight Check:** Before executing `workflow_advice_call_analysis_v1.json`, I will validate its components against the Knowledge Graph for reliability.
    2.  **Knowledge Graph Query:** `MATCH (s:Skill {name: 'whisper-transcribe'}) RETURN s.n_success, s.n_failures`.
    3.  **Result:** The query shows that the failure rate for the Whisper skill (`n_failures / (n_success + n_failures)`) has now crossed a predefined threshold of 5%. The alternative, `assemblyai-transcribe`, has a failure rate below 1%.
    4.  **Proactive Healing:** The primary transcription skill in the stored workflow is no longer reliable. I will recommend a new version of the workflow to the user.
    5.  **Generate New Version:** I will programmatically create `workflow_advice_call_analysis_v1.0.1.json`, which is identical to the original except that the `TranscribeRecording` state's `AgentBinding` now lists `skill://assemblyai-transcribe@1.2.0` instead of the Whisper skill.

**[PLANNER AGENT]:** "I am ready to start the Advice Call Analysis. I've noticed that a tool I normally use for transcription has become less reliable recently. I have updated the workflow to use a more stable alternative to ensure a smooth execution. I will proceed with this improved version."

### 4.4. The Evolved Workflow

The system doesn't just recover from failure; it learns from it. By persistently recording performance data in the knowledge graph, the Planner can identify degrading tools and proactively "heal" its own workflows, ensuring the system becomes more robust and reliable over time. This closes the loop on self-evolution.
