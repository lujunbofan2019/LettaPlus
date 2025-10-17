# Advice Call Analysis End-to-End Worked Example

## 1. Introduction

This document provides a **worked example** that demonstrates how the Letta-based Planner and Worker agents deliver Selina Finance's *Advice Call Analysis* quality-assurance workflow. It narrates the full lifecycle across planning, capability discovery, skill orchestration, hybrid memory usage, and iterative improvement. Each phase is illustrated with representative artifacts—conversation turns, chain-of-thought (CoT) excerpts, workflow JSON, tool calls, memory updates, and knowledge-graph mutations.

### 1.1. The Business Use Case: Advice Call Analysis

As a financial services provider regulated by the Financial Conduct Authority (FCA), Selina Finance has a critical duty to ensure all customer interactions meet rigorous compliance and quality standards. Our advisors and case managers handle numerous phone calls daily, which are recorded for quality assurance (QA) and training purposes.

The traditional process involves line managers or compliance staff manually listening to hours of call recordings (`.mp3` files) to:
- Assess the performance of newly onboarded advisors.
- Verify that new financial products are being explained correctly and consistently.
- Ensure adherence to FCA regulations like Consumer Duty.

This manual approach is incredibly time-consuming, difficult to scale, and prone to human inconsistency. The goal is to automate this entire process using an autonomous AI agent that can understand a user's analytical goal and execute the necessary steps to achieve it.

### 1.2. The AI-Powered Solution

Our system addresses this challenge with a **Planner Agent** that can leverage a rich ecosystem of version-controlled **Skills**. These skills provide the agent with the capabilities needed to perform the analysis, including:

- **Salesforce Integration:** To query customer, application, and staff data.
- **Recording Management:** To retrieve specific call recordings from cloud storage.
- **Transcription:** To convert audio files to text (with alternative backends like Whisper and AssemblyAI).
- **Diarization:** To identify and separate speakers in a conversation.
- **Labelling & Segmentation:** To categorize parts of a conversation (e.g., "Introduction," "Product Detail").
- **Sentiment Analysis:** To detect a customer's emotional state.
- **Compliance Analysis:** To evaluate a transcript against a set of rules from a vector store.
- **Scoring:** To calculate an overall quality score based on a dynamic formula.

[TODO: description of architectural diagram]

### 1.3. Scenarios to be Demonstrated

This document will walk through three key scenarios to illustrate the system's core features:

1.  **Initial Capability Creation.** We will show how the Planner agent interacts with a user to understand a new request, identifies a "capability gap" (the lack of a pre-existing workflow), collaboratively designs a new workflow, and executes a test run.
2.  **Capability Refinement and Reuse.** We will demonstrate how the agent can retrieve the previously saved workflow, adapt it to a new, more specific user request, and save the modified version as a new, reusable asset.
3.  **Dynamic Failure Handling and Self-Healing.** We will simulate a runtime tool failure and show how a worker agent can dynamically swap to an alternative skill. We will also show how the system records these failures in its knowledge graph, allowing the Planner to proactively "heal" the master workflow for future runs, demonstrating true self-evolution.

Through these scenarios, we will provide concrete examples of the agent's chain of thought, the artifacts it produces (workflow JSON, skill manifests), the tool calls it makes, and the updates it performs on its hybrid memory system (memory blocks, knowledge graph, and vector store).

### 1.4. Prerequisites

[TODO: improve the list below]

- Letta server + Redis (for archival memory) running locally.
- Vector store (e.g., Chroma) seeded with:
    - Regulatory rulebook chunks (`compliance_rules_v2024Q4.jsonl`).
    - Scoring formula document (`qa_scoring_formula_v3.md`).
    - Saved workflows (after step 1).
- Knowledge graph initialized with entities: `SelinaFinance`, `L&C Department`, `Advisor:<name>`, `Workflow:AdviceCallAnalysis`.
- Skill manifests (examples shown later) stored in `skills/` with registry metadata in `skills_src/registry.json`.
- MCP endpoints accessible via Docker Compose (for Recording Management, etc.).
- Planner and Worker prompts configured with tools:
    - **Planner**: `get_skillset`, `validate_skill_manifest`, `validate_workflow`, `create_workflow_control_plane`,
      `create_worker_agents`, `read_workflow_control_plane`, `notify_next_worker_agent`, `notify_if_ready`,
      `finalize_workflow`, `store_memory`, `append_graph_episode`.
    - **Worker**: `read_workflow_control_plane`, `acquire_state_lease`, `update_workflow_control_plane`,
      `load_skill`, `unload_skill`, `invoke_skill_tool`, `store_memory`, `append_graph_episode`,
      `notify_next_worker_agent`, `notify_if_ready`.
- Logging capture enabled for:
    - Planner/Worker conversations.
    - Tool inputs/outputs (JSON payloads).
    - Memory block writes (working, short-term, archival).
    - Knowledge-graph mutations (episodes, relationships, attributes).

---

## 2. Scenario 1: Initial Workflow Creation

This scenario demonstrates the system's behavior when faced with a novel task for which no pre-defined workflow exists.

**Goal:** A compliance manager wants to review the performance of a newly hired advisor, John Doe, for calls made in the last week.

### 2.1. The Conversation: Defining the Need

**[USER]:** "Hi, I need to check the quality of advice calls made by John Doe last week. Can you help me analyze them?"

**[PLANNER AGENT]:** "Of course. To ensure I get this right, could you clarify what 'analyzing them' involves? For example, are you interested in compliance with specific rules, customer sentiment, or something else?"

**[USER]:** "Good question. I need to know if he's following the standard script, so compliance is key. I'm also interested in the customer's sentiment during the calls. Finally, I'd like an overall quality score for each call."

**[PLANNER AGENT]:** "Thank you. That's very clear. Based on your request, here is the workflow I propose:
1.  Find all loan application IDs assigned to 'John Doe' in Salesforce from last week.
2.  For those applications, retrieve the associated call recordings.
3.  For each recording, transcribe it from audio to text.
4.  Once transcribed, I will run two analyses in parallel:
    *   One for customer sentiment.
    *   One for compliance against our standard rules.
5.  Finally, I will calculate an overall quality score based on the results of the sentiment and compliance checks.

Does this plan meet your needs?"

**[USER]:** "Yes, that looks perfect."

### 2.2. The Agent's Internal Monologue (Chain of Thought)

1.  **Intent Analysis:** The user wants to perform "Advice Call Analysis" for a specific advisor and date range. The key success metrics are **compliance**, **sentiment**, and a final **score**.

2.  **Memory & Capability Check (Identifying the Gap):**
    *   **Vector Store Query:** Search for existing workflows with keywords: `advice call`, `quality assurance`, `compliance analysis`.
    *   **Result:** No existing workflow found. **This is a capability gap.** I need to construct a new Standard Operating Procedure (SOP). Planner records a **capability gap** memory block:

    ```json
    {
      "type": "capability_gap", 
      "summary": "Advice Call Analysis workflow missing; need to orchestrate Salesforce lookup, recording fetch, transcription, sentiment, compliance, scoring.",
      "tags": ["qa", "advisor_quality", "workflow:new"]
    }
    ```
        
    *   **Knowledge Graph Query:** What is the historical performance of skills tagged with `compliance`, `sentiment`, `transcription`?
    *   **Result:** The graph shows `skill://whisper-transcribe@1.0.0` has a 98% success rate, and `skill://assemblyai-transcribe@1.2.0` has a 95% success rate. I'll select the Whisper-based skill as the primary for now. The `compliance-analyzer` and `sentiment-analyzer` skills show high reliability.

3.  **SOP & Workflow Construction:**
    *   The user's request maps to a sequence of steps. I'll need skills for each step.
    *   **Step 1 (Get Apps):** The `salesforce-integration` skill can find applications by advisor name.
    *   **Step 2 (Get Recordings):** The `recording-management` skill can retrieve audio files.
    *   **Step 3 (Transcribe):** The `whisper-transcribe` skill is the best choice.
    *   **Step 4 (Analyze):** The problem splits here. I can run sentiment and compliance analysis in parallel to be more efficient. This requires a `Parallel` state in my ASL workflow. I will use the `sentiment-analysis` and `compliance-analysis` skills.
    *   **Step 5 (Score):** The `scoring` skill can take the outputs from the parallel branches and compute a final score.
    *   I will now compile this logic into a `letta-asl-workflow` JSON structure.

### 2.3. The Generated Workflow Artifact

The Planner Agent generates the following `workflow_advice_call_analysis_v1.json` file.

```json
{
  "workflow_id": "c4b1a2e8-5d6f-4c7a-8b1e-3f9c0d7a6b21",
  "workflow_name": "Standard Advice Call Analysis",
  "version": "1.0.0",
  "description": "A standard workflow to analyze an advisor's call recordings for compliance, sentiment, and a final quality score.",
  "asl": {
    "StartAt": "GetApplicationIDs",
    "States": {
      "GetApplicationIDs": {
        "Type": "Task",
        "Comment": "Find loan application IDs from Salesforce given an advisor's name and date range.",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://salesforce-integration@2.1.0"]
        },
        "Next": "GetCallRecordings"
      },
      "GetCallRecordings": {
        "Type": "Task",
        "Comment": "Retrieve call recordings for the given application IDs.",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://recording-management@1.5.0"]
        },
        "Next": "TranscribeRecording"
      },
      "TranscribeRecording": {
        "Type": "Task",
        "Comment": "Transcribe the audio file to text using the Whisper-based skill.",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://whisper-transcribe@1.0.0"]
        },
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
                "AgentBinding": { "skills": ["skill://sentiment-analysis@1.0.0"] },
                "End": true
              }
            }
          },
          {
            "StartAt": "ComplianceAnalysis",
            "States": {
              "ComplianceAnalysis": {
                "Type": "Task",
                "AgentBinding": { "skills": ["skill://compliance-analysis@1.3.0"] },
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
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://scoring@1.1.0"]
        },
        "End": true
      }
    }
  }
}
```

### 2.4. Simulated Run & Memory Updates

The Planner Agent now executes this workflow for a single call recording.

- **Tool Calls:** The system executes the tools defined in the skills, passing inputs and receiving outputs at each step.
- **Control Plane:** A Redis key `cp:wf:c4b1...:meta` is created, along with state keys for each task. The `status` of each state transitions from `pending` -> `running` -> `done`.
  
  [TODO: review the object below]

  Control plane (`create_workflow_control_plane`) with initial state:
  ```json
  {
    "workflowId": "advice_call_analysis.v1",
    "state": "initialized",
    "currentStep": null,
    "artifacts": []
  }
  ```

[TODO: review the table below]
- Worker lifecycle snapshot:
  | Phase | Action |
  |-------|--------|
  | Lease | Worker acquires lease via `acquire_state_lease(control_plane_id)`.
  | Skill Load | `load_skill(manifest_id="salesforce_integration.v3")` (uses registry to attach MCP endpoint).
  | Tool Call | `invoke_skill_tool` with payload `{advisor_name: "Alex Wong", start_date: ..., end_date: ...}` → returns `{"data": {"ids": ["APP-49201"]}}`.
  | Memory | Worker appends working-memory block summarizing Salesforce lookup.
  | Knowledge Graph | Adds episode `CallAnalysisTrial` with relation `(Advisor:AlexWong) -[handled]-> (Application:APP-49201)`.
  | Control Plane | Updates step `fetch_applications` to `completed` with artifact reference.

[TODO: review the steps below]
- Repeat for each step:
  1. **Retrieve Recordings**
      - Tool output sample:
        ```json
        {
          "data": [
            {
              "application_id": "APP-49201",
              "uri": "s3://selina-calls/2024/07/03/AlexWong_APP-49201.mp3",
              "duration_sec": 1220,
              "metadata": {
                "advisor": "Alex Wong",
                "customer": "Jamie Carter",
                "call_type": "advice"
              }
            }
          ]
        }
        ```
      - Knowledge graph adds entity `Call:APP-49201_20240703` and relation `(Advisor:AlexWong) -[conducted]-> (Call:...)`.

  2. **Transcription**
      - Whisper skill output stored in working memory.
      - Letta archival memory receives chunked transcript (split into 2k token blocks).
      - Control plane artifact references `artifact://transcripts/APP-49201.txt`.

  3. **Sentiment Analysis**
      - Tool result: `{ "report": { "overall": "Neutral", "flags": ["Customer confusion at minute 8"] } }`.
      - Memory block type `analysis_result` created.

  4. **Compliance Analysis**
      - Planner preloaded compliance rules by calling `vector_store.fetch("compliance_rules_v2024Q4")` → Worker receives pointer.
      - Tool result: `{"verdicts": [{"rule": "MandatoryDisclosure", "compliant": true}, {"rule": "ProductClarity", "compliant": false, "evidence": "Customer confusion"}]}`.
      - Knowledge graph relation `(Call:...) -[non_compliant_in]-> (Rule:ProductClarity)`.

  5. **Scoring**
      - Score tool combines sentiment/compliance with formula.
      - Output: `{ "score": 72, "rationale": "Compliance failure on ProductClarity" }`.
      - Control plane artifact appended `artifact://qa_scores/APP-49201.json`.

- **Letta Context Management:** Before each task, the ephemeral worker agent loads the required skill. The `DCF Runtime` ensures the correct tool definitions and directives are added to the agent's context. After the task, the skill is unloaded ("cognitive garbage collection").
- **Hybrid Memory Updates (Post-Run):**
    - **Vector Store:** The newly created `workflow_advice_call_analysis_v1.json` is indexed and stored in the vector store with metadata tags `["advice call", "compliance", "sentiment", "scoring"]`.
    - **Knowledge Graph:**
        - A new `WorkflowExecution` node is created, linked to the `Workflow` node for `c4b1a2e8...`.
        - This execution node is linked via `USED_SKILL` edges to the specific versions of all skills that were part of the run.
        - The `p_success` and `p95_latency` properties on the edges connecting to the skill nodes are updated to reflect the successful and timely execution.
    - **Memory Blocks:** A new entry is added to the Planner's archival memory: "Successfully created and executed `workflow_advice_call_analysis_v1.json` for user [Compliance Manager's ID]. The workflow involved Salesforce integration, transcription, parallel analysis for sentiment and compliance, and scoring. The user confirmed the plan was correct."

---

## 3. Scenario 2: Workflow Refinement and Reuse

This scenario demonstrates how the system reuses and adapts existing workflows to solve similar, but distinct, problems.

**Goal:** A training manager wants to verify that all advisors are correctly explaining a new loan product, "HELOC 2.0," following a recent training course.

### 3.1. The Conversation: A More Specific Need

**[USER]:** "I need to check if our advisors are explaining the new 'FlexiLoan 2.5' product correctly in their calls since the start of the month."

**[PLANNER AGENT]:** "I can help with that. I have an existing workflow for general advice call analysis. To ensure I tailor it correctly for your needs, could you confirm if you need a full compliance and sentiment analysis, or something more specific to the product explanation?"

**[USER]:** "I don't need sentiment or a general score. I only care about the parts of the conversation where the advisor is actually describing the product and its terms. I need to know if that specific part of the script is compliant."

**[PLANNER AGENT]:** "Understood. So, the focus is on compliance within specific segments of the conversation. Here is the refined workflow I propose:
1.  Find all loan application IDs since the start of the month.
2.  Retrieve all associated call recordings.
3.  Transcribe the recordings to text.
4.  **New Step:** Identify the different speakers in the transcript (diarization) to isolate the advisor's speech.
5.  **New Step:** Label the transcript to identify and extract only the 'product detail' and 'offer explanation' segments.
6.  Run a compliance analysis *only* on those extracted segments.
7.  Report the result as a simple pass or fail.

How does this sound?"

**[USER]:** "That is exactly what I need. Perfect."

### 3.2. The Agent's Internal Monologue (Chain of Thought)

1.  **Intent Analysis:** The user wants to check for compliance on a *specific topic* ("FlexiLoan 2.5" explanation) across all advisors. This is different from the previous general quality check.

2.  **Memory & Capability Check (Reusing an Asset):**
    *   **Vector Store Query:** Search for workflows with keywords: `advice call`, `product explanation`, `compliance`.
    *   **Result:** The search returns `workflow_advice_call_analysis_v1.json` as a strong candidate. **This is a capability match.** I can adapt this existing SOP.
    *   **Analysis of User Need vs. Existing Workflow:** The user's request requires more granular processing. The existing workflow transcribes the whole call, but the user only wants specific parts. I will need to add diarization and segmentation steps. The sentiment and scoring steps are not needed.

3.  **SOP & Workflow Refinement:**
    *   I will use the `workflow_advice_call_analysis_v1.json` as a template.
    *   **Modify Step 1 (Get Apps):** Remove the 'advisor name' filter to get all applications.
    *   **Keep Steps 2 & 3:** `GetCallRecordings` and `TranscribeRecording` are still needed.
    *   **Insert New Step 4 (Diarize):** I need to add a diarization step to separate speakers. The `gpt4o-diarize` skill is available and has a high success rate according to the Knowledge Graph.
    *   **Insert New Step 5 (Segment):** I need to add a `labelling-segmentation` skill to extract the relevant conversation parts.
    *   **Modify Final Step:** Replace the `ParallelAnalysis` and `CalculateScore` states with a single `ComplianceAnalysis` task that operates on the output of the new segmentation step.
    *   I will now compile this new logic into a new, versioned workflow JSON file.

### 3.3. The Generated Workflow Artifact

The Planner Agent generates `workflow_product_explanation_compliance_v1.json`.

```json
{
  "workflow_id": "a8d3b1c9-9e8a-4f2b-9e3d-7c1b0d8a4b21",
  "workflow_name": "Product Explanation Compliance Check",
  "version": "1.0.0",
  "description": "A specialized workflow to analyze if a new product is being explained correctly by advisors.",
  "asl": {
    "StartAt": "GetApplicationIDs",
    "States": {
      "GetApplicationIDs": {
        "Type": "Task",
        "AgentBinding": { "skills": ["skill://salesforce-integration@2.1.0"] },
        "Next": "GetCallRecordings"
      },
      "GetCallRecordings": {
        "Type": "Task",
        "AgentBinding": { "skills": ["skill://recording-management@1.5.0"] },
        "Next": "TranscribeRecording"
      },
      "TranscribeRecording": {
        "Type": "Task",
        "AgentBinding": { "skills": ["skill://whisper-transcribe@1.0.0"] },
        "Next": "DiarizeTranscript"
      },
      "DiarizeTranscript": {
        "Type": "Task",
        "Comment": "Identify speakers in the transcript.",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://gpt4o-diarize@1.0.0"]
        },
        "Next": "SegmentAndLabel"
      },
      "SegmentAndLabel": {
        "Type": "Task",
        "Comment": "Extract only the 'product detail' and 'offer explanation' segments.",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://labelling-segmentation@1.2.0"]
        },
        "Next": "TargetedComplianceAnalysis"
      },
      "TargetedComplianceAnalysis": {
        "Type": "Task",
        "Comment": "Run compliance check only on the extracted segments.",
        "AgentBinding": {
          "agent_template_ref": "agent_template_worker@1.0.0",
          "skills": ["skill://compliance-analysis@1.3.0"]
        },
        "End": true
      }
    }
  }
}
```

### 3.4. Memory Updates

- **Vector Store:** The new workflow `workflow_product_explanation_compliance_v1.json` is indexed and stored with tags `["product explanation", "compliance", "diarization", "segmentation"]`.
- **Knowledge Graph:**
    - A new `Workflow` node is created for `a8d3b1c9...`.
    - An edge `REFINEMENT_OF` is created, linking this new workflow node back to the `workflow_advice_call_analysis_v1.json` node, explicitly recording its origin.
- **Memory Blocks:** A new entry is added to the Planner's archival memory: "Adapted the 'Standard Advice Call Analysis' workflow to create a new, more specific 'Product Explanation Compliance Check' workflow for user [Training Manager's ID]. This involved adding diarization and segmentation steps and removing sentiment/scoring."

---

## 4. Scenario 3: Dynamic Failure Handling and Self-Healing

This scenario showcases the system's resilience and ability to learn from operational failures.

**Goal:** During the execution of the "Standard Advice Call Analysis" workflow, the primary transcription skill fails. The system must recover, complete the task, and learn from the failure to improve future runs.

### 4.1. Runtime Failure: A Skill Times Out

During a run of `workflow_advice_call_analysis_v1.json`, the worker agent responsible for the `TranscribeRecording` state attempts to use the `skill://whisper-transcribe@1.0.0`. However, the underlying service is unresponsive, and the tool call times out, returning an error.

- **Worker Agent's State:** The worker agent has acquired the lease for the `TranscribeRecording` state. Its current loaded skill has failed.
- **Control Plane Update:** The worker agent immediately updates the Redis state document for `TranscribeRecording`, incrementing the `attempts` counter and logging the timeout error in the `errors` array.

### 4.2. The Worker's Recovery Monologue (Chain of Thought)

1.  **Error Detected:** The `whisper-transcribe` skill failed with a `TimeoutError`. This is a recoverable network/service issue, not a fatal data error. My primary objective is to complete the task.

2.  **Identify Alternatives (Dynamic Capability Re-evaluation):**
    *   I need a skill that can fulfill the `transcription` capability.
    *   I will query the **Skill Repository** for skills with the tag `transcription` that are *not* the one that just failed.
    *   **Result:** The repository returns `skill://assemblyai-transcribe@1.2.0`.

3.  **Attempt Recovery (Skill Swapping):**
    *   **Unload the failed skill:** I will call `unload_skill("skill://whisper-transcribe@1.0.0", ...)` to remove it from my context. This prevents any further attempts with the failing tool.
    *   **Load the alternative skill:** I will call `load_skill("skill://assemblyai-transcribe@1.2.0", ...)` to dynamically acquire the new capability.
    *   **Retry the task:** I will re-run the transcription logic using the newly loaded AssemblyAI skill.

4.  **Successful Recovery:** The AssemblyAI skill succeeds. The worker proceeds to write the output to the data plane, release its lease, and notify the downstream workers, allowing the workflow to continue.

### 4.3. Post-Run Learning: The Planner's Self-Healing Process

The workflow completes successfully, but the failure was logged permanently in the Knowledge Graph.

[TODO: review the block below]
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

- **Updates Knowledge Graph:** When the Whisper skill failed, the `WorkflowExecution` node was updated. The `USED_SKILL` edge pointing to `skill://whisper-transcribe@1.0.0` was updated with `n_failures: +1`. When the AssemblyAI skill was used, a new `USED_SKILL` edge was created for it, marked with `n_success: +1`.

A week later, after several more runs have experienced similar timeouts, the Planner Agent is tasked with another "Standard Advice Call Analysis."

- **Planner Agent's Monologue (Proactive Healing):**
    1.  **Pre-flight Check:** Before executing `workflow_advice_call_analysis_v1.json`, I will validate its components against the Knowledge Graph for reliability.
    2.  **Knowledge Graph Query:** `MATCH (s:Skill {name: 'whisper-transcribe'}) RETURN s.n_success, s.n_failures`.
    3.  **Result:** The query shows that the failure rate for the Whisper skill (`n_failures / (n_success + n_failures)`) has now crossed a predefined threshold of 5%. The alternative, `assemblyai-transcribe`, has a failure rate below 1%.
    4.  **Proactive Healing:** The primary transcription skill in the stored workflow is no longer reliable. I must update the SOP. I will recommend a new version of the workflow to the user.
    5.  **Generate New Version:** I will programmatically create `workflow_advice_call_analysis_v1.0.1.json`, which is identical to the original except that the `TranscribeRecording` state's `AgentBinding` now lists `skill://assemblyai-transcribe@1.2.0` instead of the Whisper skill.

**[PLANNER AGENT]:** "I am ready to start the Advice Call Analysis. I've noticed that a tool I normally use for transcription has become less reliable recently. I have updated the workflow to use a more stable alternative to ensure a smooth execution. I will proceed with this improved version."

### 4.4. The Evolved Workflow

The system doesn't just recover from failure; it learns from it. By persistently recording performance data in the knowledge graph, the Planner can identify degrading tools and proactively "heal" its own workflows, ensuring the system becomes more robust and reliable over time. This closes the loop on self-evolution.