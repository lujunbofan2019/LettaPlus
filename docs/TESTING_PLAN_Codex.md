# Advice Call Analysis End-to-End Simulation

This guide provides a **worked example** that demonstrates how the Letta-based Planner and Worker agents deliver Selina Finance's *Advice Call Analysis* quality-assurance workflow. It narrates the full lifecycle across planning, capability discovery, skill orchestration, hybrid memory usage, and iterative improvement. Each phase is illustrated with representative artifacts—conversation turns, chain-of-thought (CoT) excerpts, workflow JSON, tool calls, memory updates, and knowledge-graph mutations—so contributors can reproduce and expand the scenario.

---

## 0) Business Scenario and Objectives

Selina Finance records incoming and outbound customer phone calls (MP3 files stored in secure cloud buckets). Legal & Compliance (L&C) reviewers must audit these calls to ensure:

1. New advisors adhere to onboarding scripts and regulatory disclosures.
2. Advisors internalize new product launches after training.
3. Conversations remain compliant with FCA regulations covering Consumer Duty and financial promotions.

The automation goal is to let a Planner agent translate a user's quality-assurance request into a reusable workflow, delegate steps to Worker agents, and coordinate diverse skills:

- **Salesforce Integration** for case metadata.
- **Recording Management** for call retrieval.
- **Transcribing** (Whisper and AssemblyAI variants).
- **Diarization** (GPT-4o and Gemini 2.5 Pro variants).
- **Labelling & Segmentation**.
- **Sentiment Analysis**.
- **Compliance Analysis** (rules from vector store).
- **Scoring** (formula retrieval from vector store).

The plan below walks through three incremental milestones:

1. **First-time Planning** — identify a capability gap, co-design a workflow with the user, and execute a trial run.
2. **Workflow Adaptation** — reuse and refine the saved workflow for a new business request.
3. **Skill Substitution & Continuous Improvement** — respond to tool failures, update memory, and evolve the workflow.

---

## 1) Prerequisites and Test Fixtures

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

## 2) Milestone 1 — First-Time Planning with Capability Gap

### 2.1 Human ↔ Planner Conversation

| Turn | Speaker | Message | Planner CoT (abridged) |
|------|---------|---------|------------------------|
| 1 | User | "Can you audit Advice Calls for advisor **Alex Wong** between **2024-07-01** and **2024-07-07**?" | Identify task domain → QA compliance. Need call retrieval, transcription, compliance scoring. Check if workflow exists. |
| 2 | Planner | "To confirm, should I evaluate sentiment and compliance, and produce an overall score?" | Clarify outputs. |
| 3 | User | "Yes. Please use existing QA scorecards." | Scorecard stored in vector store? Need capability. |
| 4 | Planner | "Understood. I'll source relevant recordings, analyze sentiment and compliance, and report scores." | Move to capability assessment. |

### 2.2 Capability Assessment & Gap Detection

1. Planner calls `get_skillset` → receives registry of skills.
2. Cross-references skills with task outline. Finds building blocks but no compiled workflow.
3. Planner records a **capability gap** memory block:
   ```json
   {
     "type": "capability_gap",
     "summary": "Advice Call Analysis workflow missing; need to orchestrate Salesforce lookup, recording fetch, transcription, sentiment, compliance, scoring.",
     "tags": ["qa", "advisor_quality", "workflow:new"]
   }
   ```
4. Planner queries vector store (`search_workflows`) with embedding from user request → no match.

### 2.3 Workflow Drafting

Planner synthesizes the following Letta-ASL workflow (v2.2.0) and validates it:

```json
{
  "workflowId": "advice_call_analysis.v1",
  "name": "Advice Call Analysis Trial",
  "description": "Analyze advisor calls for sentiment, compliance, and scoring.",
  "version": "1.0.0",
  "tags": ["qa", "advisor_quality"],
  "context": {
    "entrypoint": "planner",
    "controlPlane": {
      "schema": "WorkflowControlPlane@2.2.0",
      "state": "initialized"
    }
  },
  "steps": [
    {
      "stepId": "fetch_applications",
      "description": "Lookup Salesforce applications for advisor/date range.",
      "skill": "salesforce_integration.v3",
      "tool": "applications.by_advisor",
      "inputs": {
        "advisor_name": "{{inputs.advisor_name}}",
        "start_date": "{{inputs.start_date}}",
        "end_date": "{{inputs.end_date}}"
      },
      "outputs": {
        "application_ids": "$.data.ids"
      }
    },
    {
      "stepId": "retrieve_recordings",
      "description": "Download call recordings for applications.",
      "skill": "recording_management.v2",
      "tool": "recordings.by_application",
      "inputs": {
        "application_ids": "{{steps.fetch_applications.outputs.application_ids}}"
      },
      "outputs": {
        "recording_manifest": "$.data"
      }
    },
    {
      "stepId": "transcribe_recording",
      "description": "Transcribe MP3 via Whisper backend.",
      "skill": "transcribe_whisper.v1",
      "tool": "transcribe.audio",
      "inputs": {
        "recording_uri": "{{steps.retrieve_recordings.outputs.recording_manifest[0].uri}}"
      },
      "outputs": {
        "transcript": "$.text"
      }
    },
    {
      "stepId": "sentiment_analysis",
      "description": "Assess transcript sentiment.",
      "skill": "sentiment_analysis.v2",
      "tool": "sentiment.evaluate",
      "inputs": {
        "transcript": "{{steps.transcribe_recording.outputs.transcript}}"
      },
      "outputs": {
        "sentiment_report": "$.report"
      }
    },
    {
      "stepId": "compliance_analysis",
      "description": "Check transcript against compliance rules.",
      "skill": "compliance_analysis.v4",
      "tool": "compliance.evaluate",
      "inputs": {
        "transcript": "{{steps.transcribe_recording.outputs.transcript}}",
        "rule_set": "{{memory.vector_store.compliance_rules_v2024Q4}}"
      },
      "outputs": {
        "compliance_report": "$.verdicts"
      }
    },
    {
      "stepId": "score_transcript",
      "description": "Calculate QA score from analyses.",
      "skill": "scoring.v3",
      "tool": "score.from_metrics",
      "inputs": {
        "sentiment": "{{steps.sentiment_analysis.outputs.sentiment_report}}",
        "compliance": "{{steps.compliance_analysis.outputs.compliance_report}}",
        "formula": "{{memory.vector_store.qa_scoring_formula_v3}}"
      },
      "outputs": {
        "score": "$.score",
        "rationale": "$.rationale"
      }
    }
  ],
  "success_criteria": [
    "Score produced for the sampled recording",
    "Sentiment and compliance verdicts attached",
    "Artifacts stored in knowledge base"
  ]
}
```

Validation steps:

1. Planner runs `validate_workflow` → passes.
2. Creates control plane (`create_workflow_control_plane`) with initial state:
   ```json
   {
     "workflowId": "advice_call_analysis.v1",
     "state": "initialized",
     "currentStep": null,
     "artifacts": []
   }
   ```
3. Allocates Worker agent (`create_worker_agents`) with queue subscription `qa.advice_call`.
4. Stores workflow JSON into vector store (`store_workflow_document`).

### 2.4 Trial Execution (Single Recording)

#### Worker Lifecycle Snapshot

| Phase | Action |
|-------|--------|
| Lease | Worker acquires lease via `acquire_state_lease(control_plane_id)`.
| Skill Load | `load_skill(manifest_id="salesforce_integration.v3")` (uses registry to attach MCP endpoint).
| Tool Call | `invoke_skill_tool` with payload `{advisor_name: "Alex Wong", start_date: ..., end_date: ...}` → returns `{"data": {"ids": ["APP-49201"]}}`.
| Memory | Worker appends working-memory block summarizing Salesforce lookup.
| Knowledge Graph | Adds episode `CallAnalysisTrial` with relation `(Advisor:AlexWong) -[handled]-> (Application:APP-49201)`.
| Control Plane | Updates step `fetch_applications` to `completed` with artifact reference.

Repeat for each step:

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

#### Planner Wrap-Up

1. Worker releases lease, notifies Planner.
2. Planner evaluates success criteria → satisfied.
3. Planner stores summary memory block:
   ```json
   {
     "type": "qa_trial_result",
     "advisor": "Alex Wong",
     "date_range": "2024-07-01:2024-07-07",
     "score": 72,
     "issues": ["ProductClarity"],
     "workflow_id": "advice_call_analysis.v1"
   }
   ```
4. Knowledge graph episode `AdviceCallAnalysisTrial` closed with status `success`.
5. Workflow JSON persisted to vector store (already done) with embedding metadata.
6. Planner responds to user with findings and next steps (full run across remaining recordings pending approval).

---

## 3) Milestone 2 — Workflow Adaptation for Product Training Audit

### 3.1 New User Request

> "Audit advisor explanations of the **FlexiLoan 2.0** product for the last two weeks. Focus on whether advisors explain the product clearly."

Planner retrieves prior workflow from vector store (`similarity_search(query="Advice Call Analysis")`) → finds `advice_call_analysis.v1`.

### 3.2 Planner Reasoning and Dialogue

| Turn | Speaker | Message | Planner CoT |
|------|---------|---------|-------------|
| 1 | Planner | "I have a workflow for sentiment/compliance scoring. Should we adapt it to target product explanation segments only?" | Determine modifications. |
| 2 | User | "Yes, only analyze advisor speech about the product."
| 3 | Planner | "I'll refine the workflow to diarize calls, label product-related segments, and run compliance checks on those segments." | Update plan. |

### 3.3 Workflow Refinement

Planner clones baseline workflow, applies modifications, validates, and stores new version:

```json
{
  "workflowId": "advice_call_analysis_product_focus.v1",
  "name": "Advice Call Product Clarity Audit",
  "description": "Evaluate advisor explanation of FlexiLoan 2.0",
  "version": "1.0.0",
  "steps": [
    { "stepId": "fetch_applications", ... },
    { "stepId": "retrieve_recordings", ... },
    {
      "stepId": "transcribe_recording",
      "skill": "transcribe_whisper.v1",
      "tool": "transcribe.audio",
      "outputs": { "transcript": "$.text", "segments": "$.segments" }
    },
    {
      "stepId": "diarize_transcript",
      "description": "Identify advisor-only dialogue.",
      "skill": "diarization_gpt4o.v2",
      "tool": "diarize.by_speaker",
      "inputs": {
        "transcript_segments": "{{steps.transcribe_recording.outputs.segments}}",
        "target_speaker": "advisor"
      },
      "outputs": {
        "advisor_dialogue": "$.advisor_segments"
      }
    },
    {
      "stepId": "label_segments",
      "description": "Tag dialogue sections.",
      "skill": "labelling_segmentation.v3",
      "tool": "label.by_taxonomy",
      "inputs": {
        "segments": "{{steps.diarize_transcript.outputs.advisor_dialogue}}",
        "taxonomy": ["introduction","security_check","product_detail","offer_explanation", "closing"]
      },
      "outputs": {
        "labelled_segments": "$.labelled"
      }
    },
    {
      "stepId": "extract_product_segments",
      "description": "Keep only product-related dialogue.",
      "skill": "labelling_segmentation.v3",
      "tool": "filter.by_label",
      "inputs": {
        "labelled_segments": "{{steps.label_segments.outputs.labelled_segments}}",
        "allowed_labels": ["product_detail","offer_explanation"]
      },
      "outputs": {
        "product_dialogue": "$.segments"
      }
    },
    {
      "stepId": "compliance_analysis",
      "skill": "compliance_analysis.v4",
      "inputs": {
        "transcript": "{{steps.extract_product_segments.outputs.product_dialogue}}",
        "rule_set": "{{memory.vector_store.compliance_rules_v2024Q4}}"
      }
    },
    {
      "stepId": "report_results",
      "description": "Summarize pass/fail status per advisor.",
      "skill": "scoring.v3",
      "tool": "report.pass_fail",
      "inputs": {
        "compliance_verdicts": "{{steps.compliance_analysis.outputs.compliance_report}}"
      },
      "outputs": {
        "advisor_report": "$.report"
      }
    }
  ],
  "success_criteria": [
    "Advisor product segments isolated",
    "Compliance verdict generated",
    "Report saved to knowledge base"
  ]
}
```

### 3.4 Execution Notes

- Planner reuses knowledge graph context to link new episode `ProductClarityAudit` to `FlexiLoan 2.0` entity.
- Worker loads diarization and labelling skills dynamically; unloads them after completing relevant steps to conserve memory.
- Vector store retrieval occurs twice: once for compliance rules, once to log new workflow artifact.
- Memory updates include archival storage of advisor-only transcript segments.
- Final control plane state: `completed`, with artifacts for product segments and compliance report.
- Planner responds to user with a dashboard-ready JSON payload summarizing pass/fail per advisor.

---

## 4) Milestone 3 — Skill Substitution and Continuous Improvement

### 4.1 Failure Event During Execution

While running `advice_call_analysis_product_focus.v1` for additional recordings:

1. Worker invokes `transcribe_whisper.v1` → timeout after 120s.
2. Worker marks step `transcribe_recording` as `failed`, records error artifact `{ "error": "Whisper timeout" }`.
3. Worker unloads Whisper skill (`unload_skill`), emits notification to Planner via `notify_if_ready` with status `needs_attention`.

### 4.2 Planner Response

1. Planner inspects control plane logs, sees repeated Whisper failures (3 incidents within 24 hours).
2. Searches capability catalog for alternative transcription skills → finds `transcribe_assemblyai.v1`.
3. Updates knowledge graph attribute on `Skill:transcribe_whisper.v1` (`failure_rate = 0.32`) and relation `(Workflow:advice_call_analysis_product_focus.v1) -[uses]-> (Skill:transcribe_whisper.v1)` annotated with reliability score.
4. Planner drafts remediation plan in CoT:
    - Switch to AssemblyAI backend.
    - Record change in workflow history.
    - Notify L&C stakeholders.

### 4.3 Workflow Update Procedure

1. Planner clones workflow JSON, replaces step `transcribe_recording` with:
   ```json
   {
     "stepId": "transcribe_recording",
     "description": "Transcribe MP3 via AssemblyAI backend.",
     "skill": "transcribe_assemblyai.v1",
     "tool": "transcribe.audio_async",
     "inputs": {
       "recording_uri": "{{steps.retrieve_recordings.outputs.recording_manifest[0].uri}}",
       "webhook": "{{control_plane.webhook_url}}"
     },
     "outputs": {
       "transcript": "$.text",
       "segments": "$.segments"
     }
   }
   ```
2. Validates workflow and stores as `advice_call_analysis_product_focus.v2`.
3. Updates vector store entry for `advice_call_analysis_product_focus` with version metadata and change log.
4. Adds archival memory block documenting remediation:
   ```json
   {
     "type": "workflow_update",
     "workflow_id": "advice_call_analysis_product_focus",
     "version": "2",
     "reason": "Whisper timeout rate exceeded threshold; switched to AssemblyAI backend.",
     "timestamp": "2024-07-15T11:24:00Z"
   }
   ```
5. Knowledge graph episode `WorkflowEvolution:AdviceCallAnalysis` gains relation `(Skill:transcribe_assemblyai.v1) -[introduced_on]-> (2024-07-15)`.

### 4.4 Validation Run Post-Update

- Worker executes updated workflow successfully, storing transcripts under new artifact IDs.
- Control plane records that AssemblyAI job is asynchronous; Worker polls job status before proceeding.
- Memory subsystem logs comparative analysis of `transcription_latency` for Whisper vs AssemblyAI.
- Planner notifies L&C that workflow auto-adapted and invites review of new configuration.

---

## 5) Testing Checklist and Expected Evidence

| Phase | Evidence | Location |
|-------|----------|----------|
| Capability Gap Detection | Memory block `capability_gap` | Letta archival memory export |
| Trial Workflow Execution | Control plane log showing steps 1-6 completed | `artifacts/control_planes/advice_call_analysis.v1.json` |
| Transcript Storage | Vector store entry `artifact://transcripts/APP-49201.txt` | Chroma collection `qa_artifacts` |
| Compliance Verdicts | Knowledge graph relation linking call to failed rule | `graphiti/export/episodes/AdviceCallAnalysisTrial.json` |
| Workflow Persistence | Workflow JSON saved with embedding metadata | Vector store collection `workflows` |
| Product Audit Adaptation | New workflow `advice_call_analysis_product_focus.v1` | Same as above |
| Skill Swap | Control plane change log referencing AssemblyAI | `artifacts/workflow_updates/AdviceCallAnalysis.json` |
| Failure Analytics | Memory block `workflow_update` and skill reliability metrics | Archival memory + knowledge graph |

To validate the system end-to-end, replay the scenario in a sandbox environment, ensuring each evidence artifact is produced and the Planner can reason over prior episodes during future requests.

---

## 6) Extension Ideas for Further Testing

- **Parallel Worker Execution**: spawn multiple Workers to process recordings concurrently; ensure control plane handles leases correctly.
- **Multi-Agent Collaboration**: introduce a Compliance Specialist agent that reviews borderline cases before finalizing.
- **Human-in-the-Loop Overrides**: simulate user feedback that rejects automated scoring, prompting workflow branching.
- **Automated Workflow Generation**: allow Planner to convert repeated CoT patterns into new skill manifests (closing DCF loop).
- **Metrics Dashboard Integration**: feed knowledge graph metrics into BI tools to monitor workflow reliability.

This worked example provides a concrete blueprint for validating Selina Finance's Advice Call Analysis automation and for demonstrating how hybrid memory, workflow orchestration, and capability evolution operate in practice.