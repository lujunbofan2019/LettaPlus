#!/usr/bin/env python3
"""
Graphiti MCP Server - Exposes Graphiti functionality through the Model Context Protocol (MCP)
"""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict, cast, List, Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
# from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP
from openai import AsyncAzureOpenAI
from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.azure_openai import AzureOpenAIEmbedderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMClient
from graphiti_core.llm_client.azure_openai_client import AzureOpenAILLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.search.search_config_recipes import (
    NODE_HYBRID_SEARCH_NODE_DISTANCE,
    NODE_HYBRID_SEARCH_RRF,
)
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from urllib.parse import urlparse
from graphiti_core.driver.falkordb_driver import FalkorDriver

load_dotenv()


DEFAULT_LLM_MODEL = 'gpt-4.1-mini'
SMALL_LLM_MODEL = 'gpt-4.1-nano'
DEFAULT_EMBEDDER_MODEL = 'text-embedding-3-small'

# Semaphore limit for concurrent Graphiti operations.
# Decrease this if you're experiencing 429 rate limit errors from your LLM provider.
# Increase if you have high rate limits.
SEMAPHORE_LIMIT = int(os.getenv('SEMAPHORE_LIMIT', 10))


class Requirement(BaseModel):
    """A Requirement represents a specific need, feature, or functionality that a product or service must fulfill.

    Always ensure an edge is created between the requirement and the project it belongs to, and clearly indicate on the
    edge that the requirement is a requirement.

    Instructions for identifying and extracting requirements:
    1. Look for explicit statements of needs or necessities ("We need X", "X is required", "X must have Y")
    2. Identify functional specifications that describe what the system should do
    3. Pay attention to non-functional requirements like performance, security, or usability criteria
    4. Extract constraints or limitations that must be adhered to
    5. Focus on clear, specific, and measurable requirements rather than vague wishes
    6. Capture the priority or importance if mentioned ("critical", "high priority", etc.)
    7. Include any dependencies between requirements when explicitly stated
    8. Preserve the original intent and scope of the requirement
    9. Categorize requirements appropriately based on their domain or function
    """

    project_name: str = Field(
        ...,
        description='The name of the project to which the requirement belongs.',
    )
    description: str = Field(
        ...,
        description='Description of the requirement. Only use information mentioned in the context to write this description.',
    )


class Preference(BaseModel):
    """A Preference represents a user's expressed like, dislike, or preference for something.

    Instructions for identifying and extracting preferences:
    1. Look for explicit statements of preference such as "I like/love/enjoy/prefer X" or "I don't like/hate/dislike X"
    2. Pay attention to comparative statements ("I prefer X over Y")
    3. Consider the emotional tone when users mention certain topics
    4. Extract only preferences that are clearly expressed, not assumptions
    5. Categorize the preference appropriately based on its domain (food, music, brands, etc.)
    6. Include relevant qualifiers (e.g., "likes spicy food" rather than just "likes food")
    7. Only extract preferences directly stated by the user, not preferences of others they mention
    8. Provide a concise but specific description that captures the nature of the preference
    """

    category: str = Field(
        ...,
        description="The category of the preference. (e.g., 'Brands', 'Food', 'Music')",
    )
    description: str = Field(
        ...,
        description='Brief description of the preference. Only use information mentioned in the context to write this description.',
    )


class Procedure(BaseModel):
    """A Procedure informing the agent what actions to take or how to perform in certain scenarios. Procedures are typically composed of several steps.

    Instructions for identifying and extracting procedures:
    1. Look for sequential instructions or steps ("First do X, then do Y")
    2. Identify explicit directives or commands ("Always do X when Y happens")
    3. Pay attention to conditional statements ("If X occurs, then do Y")
    4. Extract procedures that have clear beginning and end points
    5. Focus on actionable instructions rather than general information
    6. Preserve the original sequence and dependencies between steps
    7. Include any specified conditions or triggers for the procedure
    8. Capture any stated purpose or goal of the procedure
    9. Summarize complex procedures while maintaining critical details
    """

    description: str = Field(
        ...,
        description='Brief description of the procedure. Only use information mentioned in the context to write this description.',
    )


class Location(BaseModel):
    """A Location represents a physical or virtual place where activities occur.

    Instructions for identifying and extracting locations:
    1. Look for mentions of physical places (offices, cities, buildings, rooms)
    2. Identify virtual locations (URLs, servers, cloud regions, repositories)
    3. Extract location-specific details like addresses or coordinates if mentioned
    4. Link locations to events or activities that happen there
    5. Capture the purpose or context of the location
    """

    location_name: str = Field(
        ...,
        description="Name of the location (e.g., 'Seattle Office', 'AWS us-east-1')."
    )
    location_type: str | None = Field(
        None,
        description="Type of location (physical, virtual, hybrid)."
    )
    address: str | None = Field(
        None,
        description="Physical address or URL if applicable."
    )
    context: str | None = Field(
        None,
        description="Why this location is relevant (e.g., 'primary office', 'production server')."
    )


class Event(BaseModel):
    """An Event represents a time-bound activity, occurrence, or experience.

    Instructions for identifying and extracting events:
    1. Look for scheduled activities (meetings, launches, deadlines, milestones)
    2. Identify past occurrences worth remembering (incidents, releases, changes)
    3. Extract temporal information (dates, times, durations)
    4. Note participants or stakeholders involved
    5. Capture outcomes or significance of the event
    """

    event_name: str = Field(
        ...,
        description="Name or title of the event (e.g., 'Sprint Planning', 'Product Launch')."
    )
    event_type: str | None = Field(
        None,
        description="Type of event (meeting, deadline, milestone, incident, release)."
    )
    date: str | None = Field(
        None,
        description="When the event occurred or will occur (ISO format preferred)."
    )
    participants: str | None = Field(
        None,
        description="Who was or will be involved (comma-separated names or roles)."
    )
    outcome: str | None = Field(
        None,
        description="Result or significance of the event if known."
    )


class Organization(BaseModel):
    """An Organization represents a company, institution, group, or formal entity.

    Instructions for identifying and extracting organizations:
    1. Look for company names, institutions, or formal groups
    2. Identify departments, teams, or organizational units
    3. Extract relationship context (client, vendor, partner, competitor)
    4. Note industry, size, or other relevant characteristics
    5. Capture the organization's role or significance in the context
    """

    org_name: str = Field(
        ...,
        description="Name of the organization (e.g., 'Acme Corp', 'Engineering Team')."
    )
    org_type: str | None = Field(
        None,
        description="Type of organization (company, team, department, institution)."
    )
    relationship: str | None = Field(
        None,
        description="Relationship to the user or project (client, vendor, partner, internal)."
    )
    industry: str | None = Field(
        None,
        description="Industry or domain if mentioned (e.g., 'fintech', 'healthcare')."
    )


class Document(BaseModel):
    """A Document represents information content in various forms.

    Instructions for identifying and extracting documents:
    1. Look for references to specific documents (files, articles, books, videos)
    2. Identify document titles, authors, or unique identifiers
    3. Extract format information (PDF, video, article, code, specification)
    4. Note document location (URL, file path, repository) if mentioned
    5. Capture the document's purpose or relevance
    """

    title: str = Field(
        ...,
        description="Title or name of the document."
    )
    document_type: str | None = Field(
        None,
        description="Type of document (article, book, video, specification, code, report)."
    )
    author: str | None = Field(
        None,
        description="Author or creator if mentioned."
    )
    location: str | None = Field(
        None,
        description="Where the document can be found (URL, file path, repository)."
    )
    summary: str | None = Field(
        None,
        description="Brief summary of the document's content or purpose."
    )


class Topic(BaseModel):
    """A Topic represents a subject of conversation, interest, or knowledge domain.

    This is a FALLBACK entity type - use more specific types when possible.

    Instructions for identifying and extracting topics:
    1. Use this when no more specific entity type applies
    2. Identify subjects, themes, or areas of discussion
    3. Capture conceptual categories or knowledge domains
    4. Extract relationships between topics (subtopics, related topics)
    5. Note why this topic is relevant in the context
    """

    topic_name: str = Field(
        ...,
        description="Name of the topic (e.g., 'Machine Learning', 'API Design')."
    )
    category: str | None = Field(
        None,
        description="Broader category this topic belongs to."
    )
    relevance: str | None = Field(
        None,
        description="Why this topic matters in the current context."
    )


class Object(BaseModel):
    """An Object represents a physical item, tool, device, or possession.

    This is a FALLBACK entity type - use more specific types when possible.

    Instructions for identifying and extracting objects:
    1. Use this when no more specific entity type applies
    2. Look for mentions of physical items (devices, tools, equipment)
    3. Identify possessions or assets being discussed
    4. Extract relevant attributes (model, version, condition)
    5. Note the object's purpose or significance
    """

    object_name: str = Field(
        ...,
        description="Name or identifier of the object."
    )
    object_type: str | None = Field(
        None,
        description="Type or category of object (device, tool, equipment, asset)."
    )
    model: str | None = Field(
        None,
        description="Model or version if applicable."
    )
    owner: str | None = Field(
        None,
        description="Who owns or is responsible for this object."
    )


class Person(BaseModel):
    """A Person represents an individual mentioned in conversations or documents.

    Instructions for identifying and extracting people:
    1. Look for names of individuals (teammates, clients, stakeholders, users)
    2. Capture their role, title, or relationship when mentioned
    3. Extract contact information if provided (email, phone, username)
    4. Link people to projects they work on, requirements they own, or events they attend
    5. Note any preferences, expertise, or responsibilities associated with them
    """

    full_name: str = Field(
        ...,
        description="Full name of the person."
    )
    role: str | None = Field(
        None,
        description="Their role, title, or position (e.g., 'Product Manager', 'Senior Developer')."
    )
    email: str | None = Field(
        None,
        description="Email address if mentioned."
    )
    team: str | None = Field(
        None,
        description="Team, department, or organization they belong to."
    )
    expertise: str | None = Field(
        None,
        description="Areas of expertise or specialization if mentioned."
    )


class Project(BaseModel):
    """A Project represents a software project, product, initiative, or major effort.

    Instructions for identifying and extracting projects:
    1. Look for project names mentioned explicitly (e.g., "working on ProjectX", "CloudSync initiative")
    2. Identify codebases, repositories, products, or services being developed
    3. Extract project metadata like status, timeline, or technology stack
    4. Link projects to requirements, people working on them, and organizations owning them
    5. Capture the project's purpose, goals, or business value when mentioned
    """

    project_name: str = Field(
        ...,
        description="The name of the project."
    )
    description: str = Field(
        ...,
        description="Brief description of what the project does or aims to achieve."
    )
    status: str | None = Field(
        None,
        description="Current status (e.g., 'Active', 'Planning', 'On Hold', 'Completed', 'Cancelled')."
    )
    tech_stack: str | None = Field(
        None,
        description="Primary technologies, frameworks, or platforms used (e.g., 'Python, FastAPI, Neo4j')."
    )
    timeline: str | None = Field(
        None,
        description="Timeline information if mentioned (e.g., 'Q4 2024', '6-month project')."
    )


class Technology(BaseModel):
    """A Technology represents a tool, library, framework, platform, language, or technical system.

    Instructions for identifying and extracting technologies:
    1. Look for mentions of programming languages, frameworks, libraries, or tools
    2. Identify platforms, databases, cloud services, or infrastructure components
    3. Extract version numbers or specifications if mentioned
    4. Note the use case or purpose in the context
    5. Capture relationships with projects or preferences about the technology
    """

    technology_name: str = Field(
        ...,
        description="Name of the technology (e.g., 'Python', 'Neo4j', 'AWS Lambda')."
    )
    category: str | None = Field(
        None,
        description="Category (e.g., 'programming language', 'database', 'framework', 'cloud service')."
    )
    version: str | None = Field(
        None,
        description="Version number or specification if mentioned (e.g., 'Python 3.11', 'Neo4j 5.x')."
    )
    use_case: str | None = Field(
        None,
        description="What it's used for in this context (e.g., 'backend API', 'knowledge graph storage')."
    )


class Bug(BaseModel):
    """A Bug represents a defect, issue, error, or problem in a system or project.

    Instructions for identifying and extracting bugs:
    1. Look for mentions of errors, defects, issues, or problems in systems
    2. Extract bug descriptions including symptoms and error messages
    3. Identify severity or priority when mentioned
    4. Note the current status (open, in progress, fixed, verified, closed)
    5. Link bugs to affected components, projects, or people assigned to fix them
    """

    description: str = Field(
        ...,
        description="Clear description of the bug, including symptoms or error messages."
    )
    severity: str | None = Field(
        None,
        description="Severity level (e.g., 'Critical', 'High', 'Medium', 'Low', 'Blocker')."
    )
    status: str | None = Field(
        None,
        description="Current status (e.g., 'Open', 'In Progress', 'Fixed', 'Verified', 'Closed')."
    )
    affected_component: str | None = Field(
        None,
        description="Which component, feature, or system is affected (e.g., '/api/sync endpoint')."
    )
    assigned_to: str | None = Field(
        None,
        description="Person or team assigned to fix this bug."
    )


class APIEndpoint(BaseModel):
    """An APIEndpoint represents a specific API endpoint or route in a system.

    Instructions for identifying and extracting API endpoints:
    1. Look for URL paths or route definitions (e.g., "/api/users", "GET /projects/{id}")
    2. Extract HTTP methods (GET, POST, PUT, DELETE, PATCH)
    3. Capture authentication or authorization requirements if mentioned
    4. Note rate limits, request/response formats, or special behaviors
    5. Link endpoints to projects, services, or documentation they belong to
    """

    path: str = Field(
        ...,
        description="The URL path of the endpoint (e.g., '/api/v1/users', '/sync/{file_id}')."
    )
    method: str = Field(
        ...,
        description="HTTP method (GET, POST, PUT, DELETE, PATCH, OPTIONS)."
    )
    description: str = Field(
        ...,
        description="What this endpoint does (e.g., 'Retrieves user profile information')."
    )
    auth_required: bool | None = Field(
        None,
        description="Whether authentication is required (true/false)."
    )
    rate_limit: str | None = Field(
        None,
        description="Rate limiting info if mentioned (e.g., '100 requests per minute', '1000/hour')."
    )


class Skill(BaseModel):
    """A Skill represents a transferable, version-controlled capability that can be loaded into agents.

    Instructions for identifying and extracting skills:
    1. Look for mentions of reusable capabilities, tools, or functions agents can use
    2. Extract skill identity (name, version, UUID, manifest ID)
    3. Capture skill metadata (author, tags, risk level, permissions)
    4. Note which tools, directives, or data sources the skill requires
    5. Track skill lifecycle events (discovery, loading, execution, unloading)
    6. Link skills to workflows that use them and agents that load them
    7. Record performance metrics (success rate, latency, error types)
    """

    manifest_id: str = Field(
        ...,
        description="Unique manifest identifier (e.g., 'web.search@1.0.0')."
    )
    skill_name: str = Field(
        ...,
        description="Human-readable skill name (e.g., 'web.search')."
    )
    version: str = Field(
        ...,
        description="Semantic version (e.g., '1.0.0', '2.1.3-beta')."
    )
    skill_id: str | None = Field(
        None,
        description="UUID for this specific skill version."
    )
    description: str = Field(
        ...,
        description="What this skill does and when to use it."
    )
    author: str | None = Field(
        None,
        description="Team or individual who authored this skill."
    )
    risk_level: str | None = Field(
        None,
        description="Risk assessment (low, medium, high, critical)."
    )
    tags: str | None = Field(
        None,
        description="Comma-separated tags for categorization (e.g., 'search, research, web')."
    )


class Workflow(BaseModel):
    """A Workflow represents a state machine that orchestrates multi-step tasks using skills.

    Instructions for identifying and extracting workflows:
    1. Look for mentions of multi-step processes, SOPs, or orchestrated tasks
    2. Extract workflow identity (name, version, starting state)
    3. Identify the states/steps in the workflow and their sequencing
    4. Note which skills each state requires
    5. Track workflow execution history (success/failure, duration, bottlenecks)
    6. Link workflows to the problems they solve and the skills they compose
    7. Capture adaptations (workflow forked, states added/removed, skills swapped)
    """

    workflow_name: str = Field(
        ...,
        description="Workflow name (e.g., 'research-and-summarize', 'invoice-reconciliation')."
    )
    version: str = Field(
        ...,
        description="Semantic version of this workflow (e.g., '1.0.0')."
    )
    description: str = Field(
        ...,
        description="What problem this workflow solves."
    )
    starting_state: str | None = Field(
        None,
        description="The initial state/step where execution begins."
    )
    total_states: int | None = Field(
        None,
        description="Number of states/steps in this workflow."
    )
    complexity: str | None = Field(
        None,
        description="Workflow complexity (simple, moderate, complex, highly-complex)."
    )
    status: str | None = Field(
        None,
        description="Workflow status (draft, approved, deprecated, archived)."
    )


class WorkflowExecution(BaseModel):
    """A WorkflowExecution represents a specific run instance of a workflow.

    Instructions for identifying and extracting workflow executions:
    1. Look for mentions of workflow runs, executions, or instantiations
    2. Extract execution metadata (execution ID, start/end time, duration)
    3. Identify the workflow being executed and its version
    4. Track execution outcomes (success, failure, partial completion)
    5. Note which agents participated and which skills were loaded
    6. Capture performance metrics (latency per state, retries, errors)
    7. Link executions to their parent workflows and resulting knowledge
    """

    execution_id: str = Field(
        ...,
        description="Unique identifier for this execution instance."
    )
    workflow_name: str = Field(
        ...,
        description="Name of the workflow being executed."
    )
    workflow_version: str = Field(
        ...,
        description="Version of the workflow executed."
    )
    status: str = Field(
        ...,
        description="Execution status (pending, running, completed, failed, timeout)."
    )
    start_time: str | None = Field(
        None,
        description="When execution started (ISO timestamp)."
    )
    end_time: str | None = Field(
        None,
        description="When execution completed or failed (ISO timestamp)."
    )
    duration_seconds: float | None = Field(
        None,
        description="Total execution duration in seconds."
    )
    outcome: str | None = Field(
        None,
        description="Summary of execution outcome or result."
    )


class WorkflowState(BaseModel):
    """A WorkflowState represents a single step or state within a workflow.

    Instructions for identifying and extracting workflow states:
    1. Look for mentions of workflow steps, tasks, or states
    2. Extract state identity (name, type: task/choice/parallel/wait)
    3. Note which skills this state requires
    4. Track state dependencies (which states must complete before this one)
    5. Capture state performance (execution time, retry count, failure patterns)
    6. Link states to their parent workflow and the agents that execute them
    """

    state_name: str = Field(
        ...,
        description="Name of this state/step (e.g., 'Research', 'Summarize')."
    )
    state_type: str = Field(
        ...,
        description="State type (task, choice, parallel, map, wait, succeed, fail)."
    )
    workflow_name: str = Field(
        ...,
        description="Parent workflow this state belongs to."
    )
    required_skills: str | None = Field(
        None,
        description="Comma-separated list of skills required (e.g., 'web.search@1.0.0, summarize@2.1.0')."
    )
    next_state: str | None = Field(
        None,
        description="The next state to transition to upon success."
    )
    is_terminal: bool | None = Field(
        None,
        description="Whether this is a terminal state (end of workflow)."
    )


class Agent(BaseModel):
    """An Agent represents a fungible worker that can load skills and execute tasks.

    Instructions for identifying and extracting agents:
    1. Look for mentions of worker agents, agent instances, or agent templates
    2. Extract agent identity (agent ID, template reference)
    3. Note whether the agent is ephemeral or persistent
    4. Track which skills the agent currently has loaded
    5. Capture agent lifecycle events (provisioning, task acquisition, completion)
    6. Link agents to workflow executions they participated in
    7. Record agent performance (tasks completed, success rate, average latency)
    """

    agent_id: str = Field(
        ...,
        description="Unique identifier for this agent instance."
    )
    agent_name: str = Field(
        ...,
        description="Name of this agent instance (e.g., 'Planner', 'Worker', 'Reflector')."
    )
    agent_template: str | None = Field(
        None,
        description="Template this agent was derived from (e.g., 'agent-template@worker@1.0.0')."
    )
    agent_type: str | None = Field(
        None,
        description="Type of agent (planner, worker, reviewer, reflector, curator)."
    )
    lifecycle_status: str | None = Field(
        None,
        description="Current lifecycle status (provisioning, idle, executing, completed, terminated)."
    )
    loaded_skills: str | None = Field(
        None,
        description="Comma-separated list of currently loaded skills."
    )
    is_ephemeral: bool | None = Field(
        None,
        description="Whether this agent is ephemeral (created for one workflow) or persistent."
    )


class ProblemDecomposition(BaseModel):
    """A ProblemDecomposition represents breaking a complex problem into subtasks.

    Instructions for identifying and extracting problem decompositions:
    1. Look for discussions of complex problems being analyzed
    2. Extract the high-level problem statement
    3. Identify the subtasks or components identified
    4. Note the decomposition strategy used (sequential, parallel, hierarchical)
    5. Track which skills or workflows address each subtask
    6. Link decompositions to the resulting workflows they inspired
    7. Capture learning (what decomposition patterns work for which problem types)
    """

    problem_statement: str = Field(
        ...,
        description="The original complex problem being decomposed."
    )
    decomposition_strategy: str | None = Field(
        None,
        description="Strategy used (divide-and-conquer, pipeline, map-reduce, dependency-graph)."
    )
    num_subtasks: int | None = Field(
        None,
        description="Number of subtasks identified."
    )
    subtasks: str | None = Field(
        None,
        description="List or description of subtasks identified."
    )
    complexity_estimate: str | None = Field(
        None,
        description="Estimated complexity (low, medium, high)."
    )
    resulting_workflow: str | None = Field(
        None,
        description="Name of workflow created to solve this decomposed problem."
    )


class SkillPerformanceMetric(BaseModel):
    """Performance metrics and telemetry for a specific skill usage.

    Instructions for identifying and extracting skill performance metrics:
    1. Look for execution outcomes linked to specific skills
    2. Extract quantitative metrics (success rate, latency, error count)
    3. Note the context (which workflow, which problem type)
    4. Track trends over time (improving, degrading, stable)
    5. Link metrics to skill versions for comparison
    6. Identify failure patterns or common error types
    """

    skill_manifest_id: str = Field(
        ...,
        description="The skill being measured (e.g., 'web.search@1.0.0')."
    )
    metric_type: str = Field(
        ...,
        description="Type of metric (success_rate, avg_latency, error_rate, retry_count)."
    )
    value: float = Field(
        ...,
        description="The metric value (e.g., 0.95 for 95% success rate, 2.5 for 2.5s latency)."
    )
    context: str | None = Field(
        None,
        description="Context where measured (e.g., 'invoice-reconciliation workflow')."
    )
    measurement_period: str | None = Field(
        None,
        description="Time period for this measurement (e.g., 'last 30 days', 'Q4 2024')."
    )
    sample_size: int | None = Field(
        None,
        description="Number of executions measured."
    )


class CapabilityGap(BaseModel):
    """A CapabilityGap represents an identified need for a skill the system doesn't have.

    Instructions for identifying and extracting capability gaps:
    1. Look for situations where agents couldn't complete tasks
    2. Extract what capability was missing (skill name, function needed)
    3. Note the context (which problem, which workflow step)
    4. Track resolution status (identified, skill-discovered, skill-acquired, gap-closed)
    5. Link gaps to newly acquired skills that filled them
    6. Capture the trigger event (failure, manual identification, planning analysis)
    """

    missing_capability: str = Field(
        ...,
        description="Description of the missing capability (e.g., 'PDF parsing', 'SQL query generation')."
    )
    context: str = Field(
        ...,
        description="Where this gap was identified (workflow name, problem type)."
    )
    status: str = Field(
        ...,
        description="Gap status (identified, searching, skill-found, skill-acquired, closed)."
    )
    trigger_event: str | None = Field(
        None,
        description="What triggered identification (task-failure, planning-analysis, manual-report)."
    )
    proposed_skill: str | None = Field(
        None,
        description="Skill that could fill this gap if identified."
    )
    priority: str | None = Field(
        None,
        description="Priority level (critical, high, medium, low)."
    )


class WorkflowAdaptation(BaseModel):
    """A WorkflowAdaptation represents modifying an existing workflow for a new use case.

    Instructions for identifying and extracting workflow adaptations:
    1. Look for situations where existing workflows are being reused or modified
    2. Extract source workflow (what was adapted) and target workflow (result)
    3. Identify what changed (skills swapped, states added/removed, sequencing altered)
    4. Note the reason for adaptation (new problem type, skill upgrade, performance issue)
    5. Track adaptation success (did it work better, worse, or equivalently)
    6. Link adaptations to learning about workflow patterns
    """

    source_workflow: str = Field(
        ...,
        description="Original workflow that was adapted (name@version)."
    )
    target_workflow: str = Field(
        ...,
        description="New workflow created through adaptation (name@version)."
    )
    adaptation_type: str = Field(
        ...,
        description="Type of adaptation (skill-swap, state-addition, state-removal, resequencing, parallelization)."
    )
    changes_description: str = Field(
        ...,
        description="What specifically changed in the adaptation."
    )
    reason: str | None = Field(
        None,
        description="Why this adaptation was needed (new-problem-type, performance-issue, skill-upgrade)."
    )
    outcome: str | None = Field(
        None,
        description="Result of adaptation (successful, failed, improved-performance, degraded-performance)."
    )


class LearningInsight(BaseModel):
    """A LearningInsight represents accumulated knowledge about what works and why.

    Instructions for identifying and extracting learning insights:
    1. Look for reflections, post-mortems, or analysis of past executions
    2. Extract the insight (a pattern, best practice, or lesson learned)
    3. Note the evidence supporting this insight (execution data, metrics)
    4. Track confidence level (how certain are we this is correct)
    5. Link insights to the workflows/skills they inform
    6. Capture applicability (when does this insight apply)
    """

    insight_statement: str = Field(
        ...,
        description="The insight or lesson learned (e.g., 'Skill X works better than Y for problem type Z')."
    )
    insight_type: str = Field(
        ...,
        description="Type of insight (best-practice, failure-pattern, optimization-opportunity, skill-comparison)."
    )
    confidence: str | None = Field(
        None,
        description="Confidence level (low, medium, high, validated)."
    )
    supporting_evidence: str | None = Field(
        None,
        description="Evidence supporting this insight (execution IDs, metric summaries)."
    )
    applicability: str | None = Field(
        None,
        description="When/where this insight applies (problem types, workflows, contexts)."
    )
    source: str | None = Field(
        None,
        description="How this insight was derived (human-observation, automated-analysis, reflector-agent)."
    )


ENTITY_TYPES: dict[str, BaseModel] = {
    # User-centric
    "Preference": Preference,         # type: ignore
    "Person": Person,                 # type: ignore

    # Work-related
    "Requirement": Requirement,       # type: ignore
    "Procedure": Procedure,           # type: ignore
    "Project": Project,               # type: ignore
    "Organization": Organization,     # type: ignore

    # Technical
    "Technology": Technology,         # type: ignore
    "APIEndpoint": APIEndpoint,       # type: ignore
    "Bug": Bug,                       # type: ignore
    "Document": Document,             # type: ignore

    # Contextual
    "Location": Location,             # type: ignore
    "Event": Event,                   # type: ignore

    # Fallbacks
    "Topic": Topic,                   # type: ignore
    "Object": Object,                 # type: ignore

    # DCF
    "Skill": Skill,                                     # type: ignore
    "SkillPerformanceMetric": SkillPerformanceMetric,   # type: ignore
    "CapabilityGap": CapabilityGap,                     # type: ignore
    "Workflow": Workflow,                               # type: ignore
    "WorkflowExecution": WorkflowExecution,             # type: ignore
    "WorkflowState": WorkflowState,                     # type: ignore
    "WorkflowAdaptation": WorkflowAdaptation,           # type: ignore
    "Agent": Agent,                                     # type: ignore
    "ProblemDecomposition": ProblemDecomposition,       # type: ignore
    "LearningInsight": LearningInsight,                 # type: ignore
}


'''
1. Skill relationships:

Workflow --USES_SKILL--> Skill
WorkflowState --REQUIRES_SKILL--> Skill
Agent --HAS_LOADED--> Skill
Skill --HAS_PERFORMANCE_METRIC--> SkillPerformanceMetric
CapabilityGap --FILLED_BY--> Skill

2. Workflow relationships:

Workflow --HAS_STATE--> WorkflowState
WorkflowExecution --INSTANTIATES--> Workflow
Agent --EXECUTED--> WorkflowExecution
Workflow --ADAPTED_FROM--> Workflow (via WorkflowAdaptation)
ProblemDecomposition --RESULTED_IN--> Workflow

3. Learning relationships:

LearningInsight --APPLIES_TO--> Workflow
LearningInsight --INFORMS--> Skill
SkillPerformanceMetric --SUPPORTS--> LearningInsight
WorkflowExecution --GENERATED--> LearningInsight

4. Problem-solving relationships:

ProblemDecomposition --USES_SKILL--> Skill (for each subtask)
CapabilityGap --IDENTIFIED_IN--> WorkflowExecution
WorkflowAdaptation --ADDRESSES--> CapabilityGap
'''


# Type definitions for API responses
class ErrorResponse(TypedDict):
    error: str


class SuccessResponse(TypedDict):
    message: str


class NodeResult(TypedDict):
    uuid: str
    name: str
    summary: str
    labels: list[str]
    group_id: str
    created_at: str
    attributes: dict[str, Any]


class NodeSearchResponse(TypedDict):
    message: str
    nodes: list[NodeResult]


class FactSearchResponse(TypedDict):
    message: str
    facts: list[dict[str, Any]]


class EpisodeSearchResponse(TypedDict):
    message: str
    episodes: list[dict[str, Any]]


class StatusResponse(TypedDict):
    status: str
    message: str


def create_azure_credential_token_provider() -> Callable[[], str]:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, 'https://cognitiveservices.azure.com/.default'
    )
    return token_provider


# Server configuration classes
# The configuration system has a hierarchy:
# - GraphitiConfig is the top-level configuration
#   - LLMConfig handles all OpenAI/LLM related settings
#   - EmbedderConfig manages embedding settings
#   - Neo4jConfig manages database connection details
#   - Various other settings like group_id and feature flags
# Configuration values are loaded from:
# 1. Default values in the class definitions
# 2. Environment variables (loaded via load_dotenv())
# 3. Command line arguments (which override environment variables)
class GraphitiLLMConfig(BaseModel):
    """Configuration for the LLM client.

    Centralizes all LLM-specific configuration parameters including API keys and model selection.
    """

    api_key: str | None = None
    model: str = DEFAULT_LLM_MODEL
    small_model: str = SMALL_LLM_MODEL
    temperature: float = 0.0
    azure_openai_endpoint: str | None = None
    azure_openai_deployment_name: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_use_managed_identity: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiLLMConfig':
        """Create LLM configuration from environment variables."""
        # Get model from environment, or use default if not set or empty
        model_env = os.environ.get('MODEL_NAME', '')
        model = model_env if model_env.strip() else DEFAULT_LLM_MODEL

        # Get small_model from environment, or use default if not set or empty
        small_model_env = os.environ.get('SMALL_MODEL_NAME', '')
        small_model = small_model_env if small_model_env.strip() else SMALL_LLM_MODEL

        azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT', None)
        azure_openai_api_version = os.environ.get('AZURE_OPENAI_API_VERSION', None)
        azure_openai_deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME', None)
        azure_openai_use_managed_identity = (
            os.environ.get('AZURE_OPENAI_USE_MANAGED_IDENTITY', 'false').lower() == 'true'
        )

        if azure_openai_endpoint is None:
            # Setup for OpenAI API
            # Log if empty model was provided
            if model_env == '':
                logger.debug(
                    f'MODEL_NAME environment variable not set, using default: {DEFAULT_LLM_MODEL}'
                )
            elif not model_env.strip():
                logger.warning(
                    f'Empty MODEL_NAME environment variable, using default: {DEFAULT_LLM_MODEL}'
                )

            return cls(
                api_key=os.environ.get('OPENAI_API_KEY'),
                model=model,
                small_model=small_model,
                temperature=float(os.environ.get('LLM_TEMPERATURE', '0.0')),
            )
        else:
            # Setup for Azure OpenAI API
            # Log if empty deployment name was provided
            if azure_openai_deployment_name is None:
                logger.error('AZURE_OPENAI_DEPLOYMENT_NAME environment variable not set')

                raise ValueError('AZURE_OPENAI_DEPLOYMENT_NAME environment variable not set')
            if not azure_openai_use_managed_identity:
                # api key
                api_key = os.environ.get('OPENAI_API_KEY', None)
            else:
                # Managed identity
                api_key = None

            return cls(
                azure_openai_use_managed_identity=azure_openai_use_managed_identity,
                azure_openai_endpoint=azure_openai_endpoint,
                api_key=api_key,
                azure_openai_api_version=azure_openai_api_version,
                azure_openai_deployment_name=azure_openai_deployment_name,
                model=model,
                small_model=small_model,
                temperature=float(os.environ.get('LLM_TEMPERATURE', '0.0')),
            )

    @classmethod
    def from_cli_and_env(cls, args: argparse.Namespace) -> 'GraphitiLLMConfig':
        """Create LLM configuration from CLI arguments, falling back to environment variables."""
        # Start with environment-based config
        config = cls.from_env()

        # CLI arguments override environment variables when provided
        if hasattr(args, 'model') and args.model:
            # Only use CLI model if it's not empty
            if args.model.strip():
                config.model = args.model
            else:
                # Log that empty model was provided and default is used
                logger.warning(f'Empty model name provided, using default: {DEFAULT_LLM_MODEL}')

        if hasattr(args, 'small_model') and args.small_model:
            if args.small_model.strip():
                config.small_model = args.small_model
            else:
                logger.warning(f'Empty small_model name provided, using default: {SMALL_LLM_MODEL}')

        if hasattr(args, 'temperature') and args.temperature is not None:
            config.temperature = args.temperature

        return config

    def create_client(self) -> LLMClient:
        """Create an LLM client based on this configuration.

        Returns:
            LLMClient instance
        """

        if self.azure_openai_endpoint is not None:
            # Azure OpenAI API setup
            if self.azure_openai_use_managed_identity:
                # Use managed identity for authentication
                token_provider = create_azure_credential_token_provider()
                return AzureOpenAILLMClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        azure_ad_token_provider=token_provider,
                    ),
                    config=LLMConfig(
                        api_key=self.api_key,
                        model=self.model,
                        small_model=self.small_model,
                        temperature=self.temperature,
                    ),
                )
            elif self.api_key:
                # Use API key for authentication
                return AzureOpenAILLMClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        api_key=self.api_key,
                    ),
                    config=LLMConfig(
                        api_key=self.api_key,
                        model=self.model,
                        small_model=self.small_model,
                        temperature=self.temperature,
                    ),
                )
            else:
                raise ValueError('OPENAI_API_KEY must be set when using Azure OpenAI API')

        if not self.api_key:
            raise ValueError('OPENAI_API_KEY must be set when using OpenAI API')

        llm_client_config = LLMConfig(
            api_key=self.api_key, model=self.model, small_model=self.small_model
        )

        # Set temperature
        llm_client_config.temperature = self.temperature

        return OpenAIClient(config=llm_client_config)


class GraphitiEmbedderConfig(BaseModel):
    """Configuration for the embedder client.

    Centralizes all embedding-related configuration parameters.
    """

    model: str = DEFAULT_EMBEDDER_MODEL
    api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment_name: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_use_managed_identity: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiEmbedderConfig':
        """Create embedder configuration from environment variables."""

        # Get model from environment, or use default if not set or empty
        model_env = os.environ.get('EMBEDDER_MODEL_NAME', '')
        model = model_env if model_env.strip() else DEFAULT_EMBEDDER_MODEL

        azure_openai_endpoint = os.environ.get('AZURE_OPENAI_EMBEDDING_ENDPOINT', None)
        azure_openai_api_version = os.environ.get('AZURE_OPENAI_EMBEDDING_API_VERSION', None)
        azure_openai_deployment_name = os.environ.get(
            'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME', None
        )
        azure_openai_use_managed_identity = (
            os.environ.get('AZURE_OPENAI_USE_MANAGED_IDENTITY', 'false').lower() == 'true'
        )
        if azure_openai_endpoint is not None:
            # Setup for Azure OpenAI API
            # Log if empty deployment name was provided
            azure_openai_deployment_name = os.environ.get(
                'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME', None
            )
            if azure_openai_deployment_name is None:
                logger.error('AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME environment variable not set')

                raise ValueError(
                    'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME environment variable not set'
                )

            if not azure_openai_use_managed_identity:
                # api key
                api_key = os.environ.get('AZURE_OPENAI_EMBEDDING_API_KEY', None) or os.environ.get(
                    'OPENAI_API_KEY', None
                )
            else:
                # Managed identity
                api_key = None

            return cls(
                azure_openai_use_managed_identity=azure_openai_use_managed_identity,
                azure_openai_endpoint=azure_openai_endpoint,
                api_key=api_key,
                azure_openai_api_version=azure_openai_api_version,
                azure_openai_deployment_name=azure_openai_deployment_name,
            )
        else:
            return cls(
                model=model,
                api_key=os.environ.get('OPENAI_API_KEY'),
            )

    def create_client(self) -> EmbedderClient | None:
        if self.azure_openai_endpoint is not None:
            # Azure OpenAI API setup
            if self.azure_openai_use_managed_identity:
                # Use managed identity for authentication
                token_provider = create_azure_credential_token_provider()
                return AzureOpenAIEmbedderClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        azure_ad_token_provider=token_provider,
                    ),
                    model=self.model,
                )
            elif self.api_key:
                # Use API key for authentication
                return AzureOpenAIEmbedderClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        api_key=self.api_key,
                    ),
                    model=self.model,
                )
            else:
                logger.error('OPENAI_API_KEY must be set when using Azure OpenAI API')
                return None
        else:
            # OpenAI API setup
            if not self.api_key:
                return None

            embedder_config = OpenAIEmbedderConfig(api_key=self.api_key, embedding_model=self.model)

            return OpenAIEmbedder(config=embedder_config)


class Neo4jConfig(BaseModel):
    """Configuration for Neo4j database connection."""

    uri: str = 'bolt://localhost:7687'
    user: str = 'neo4j'
    password: str = 'password'

    @classmethod
    def from_env(cls) -> 'Neo4jConfig':
        """Create Neo4j configuration from environment variables."""
        return cls(
            uri=os.environ.get('NEO4J_URI', 'bolt://localhost:7687'),
            user=os.environ.get('NEO4J_USER', 'neo4j'),
            password=os.environ.get('NEO4J_PASSWORD', 'password'),
        )



uri = os.environ.get("FALKORDB_URI", "redis://falkordb:6379")
parsed = urlparse(uri)
password = os.environ.get("FALKORDB_PASSWORD")
if password in (None, "", "null"):
    password = None

username = os.environ.get("FALKORDB_USERNAME", "default")  # Redis default user is "default"

print("Connecting to FalkorDB with", parsed.hostname, parsed.port, repr(username), repr(password), os.environ.get("FALKORDB_DATABASE"))

falkor_driver = FalkorDriver(
    host=parsed.hostname or "falkordb",
    port=parsed.port or 6379,
    username=username,
    password=password,
    database=os.environ.get("FALKORDB_DATABASE", "lettaplus"),
)


class GraphitiConfig(BaseModel):
    """Configuration for Graphiti client.

    Centralizes all configuration parameters for the Graphiti client.
    """

    llm: GraphitiLLMConfig = Field(default_factory=GraphitiLLMConfig)
    embedder: GraphitiEmbedderConfig = Field(default_factory=GraphitiEmbedderConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    group_id: str | None = None
    use_custom_entities: bool = False
    destroy_graph: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiConfig':
        """Create a configuration instance from environment variables."""
        return cls(
            llm=GraphitiLLMConfig.from_env(),
            embedder=GraphitiEmbedderConfig.from_env(),
            neo4j=Neo4jConfig.from_env(),
        )

    @classmethod
    def from_cli_and_env(cls, args: argparse.Namespace) -> 'GraphitiConfig':
        """Create configuration from CLI arguments, falling back to environment variables."""
        # Start with environment configuration
        config = cls.from_env()

        # Apply CLI overrides
        if args.group_id:
            config.group_id = args.group_id
        else:
            config.group_id = 'default'

        config.use_custom_entities = args.use_custom_entities
        config.destroy_graph = args.destroy_graph

        # Update LLM config using CLI args
        config.llm = GraphitiLLMConfig.from_cli_and_env(args)

        return config


class MCPConfig(BaseModel):
    """Configuration for MCP server."""

    transport: str = 'sse'

    @classmethod
    def from_cli(cls, args: argparse.Namespace) -> 'MCPConfig':
        """Create MCP configuration from CLI arguments."""
        return cls(transport=args.transport)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Create global config instance - will be properly initialized later
config = GraphitiConfig()

# MCP server instructions
GRAPHITI_MCP_INSTRUCTIONS = """
Graphiti is a memory service for AI agents built on a knowledge graph. Graphiti performs well
with dynamic data such as user interactions, changing enterprise data, and external information.

Graphiti transforms information into a richly connected knowledge network, allowing you to 
capture relationships between concepts, entities, and information. The system organizes data as episodes 
(content snippets), nodes (entities), and facts (relationships between entities), creating a dynamic, 
queryable memory store that evolves with new information. Graphiti supports multiple data formats, including 
structured JSON data, enabling seamless integration with existing data pipelines and systems.

Facts contain temporal metadata, allowing you to track the time of creation and whether a fact is invalid 
(superseded by new information).

Key capabilities:
1. Add episodes (text, messages, or JSON) to the knowledge graph with the add_memory tool
2. Search for nodes (entities) in the graph using natural language queries with search_nodes
3. Find relevant facts (relationships between entities) with search_facts
4. Retrieve specific entity edges or episodes by UUID
5. Manage the knowledge graph with tools like delete_episode, delete_entity_edge, and clear_graph

The server connects to a database for persistent storage and uses language models for certain operations. 
Each piece of information is organized by group_id, allowing you to maintain separate knowledge domains.

When adding information, provide descriptive names and detailed content to improve search quality. 
When searching, use specific queries and consider filtering by group_id for more relevant results.

For optimal performance, ensure the database is properly configured and accessible, and valid 
API keys are provided for any language model operations.
"""

# MCP server instance
mcp = FastMCP('Graphiti Agent Memory', instructions=GRAPHITI_MCP_INSTRUCTIONS)

# Initialize Graphiti client
graphiti_client: Graphiti | None = None


async def initialize_graphiti():
    """Initialize the Graphiti client with the configured settings."""
    global graphiti_client, config

    try:
        # Create LLM client if possible
        llm_client = config.llm.create_client()
        if not llm_client and config.use_custom_entities:
            # If custom entities are enabled, we must have an LLM client
            raise ValueError('OPENAI_API_KEY must be set when custom entities are enabled')

        # Validate Neo4j configuration
        if not config.neo4j.uri or not config.neo4j.user or not config.neo4j.password:
            raise ValueError('NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set')

        embedder_client = config.embedder.create_client()

        # Initialize Graphiti client
        graphiti_client = Graphiti(
            # replace neo4j with fldb
            # uri=config.neo4j.uri,
            # user=config.neo4j.user,
            # password=config.neo4j.password,
            graph_driver = falkor_driver,

            llm_client=llm_client,
            embedder=embedder_client,
            max_coroutines=SEMAPHORE_LIMIT,
        )

        # Destroy graph if requested
        if config.destroy_graph:
            logger.info('Destroying graph...')
            await clear_data(graphiti_client.driver)

        # Initialize the graph database with Graphiti's indices
        await graphiti_client.build_indices_and_constraints()
        logger.info('Graphiti client initialized successfully')

        # Log configuration details for transparency
        if llm_client:
            logger.info(f'Using OpenAI model: {config.llm.model}')
            logger.info(f'Using temperature: {config.llm.temperature}')
        else:
            logger.info('No LLM client configured - entity extraction will be limited')

        logger.info(f'Using group_id: {config.group_id}')
        logger.info(
            f'Custom entity extraction: {"enabled" if config.use_custom_entities else "disabled"}'
        )
        logger.info(f'Using concurrency limit: {SEMAPHORE_LIMIT}')

    except Exception as e:
        logger.error(f'Failed to initialize Graphiti: {str(e)}')
        raise


def format_fact_result(edge: EntityEdge) -> dict[str, Any]:
    """Format an entity edge into a readable result.

    Since EntityEdge is a Pydantic BaseModel, we can use its built-in serialization capabilities.

    Args:
        edge: The EntityEdge to format

    Returns:
        A dictionary representation of the edge with serialized dates and excluded embeddings
    """
    result = edge.model_dump(
        mode='json',
        exclude={
            'fact_embedding',
        },
    )
    result.get('attributes', {}).pop('fact_embedding', None)
    return result


# Dictionary to store queues for each group_id
# Each queue is a list of tasks to be processed sequentially
episode_queues: dict[str, asyncio.Queue] = {}
# Dictionary to track if a worker is running for each group_id
queue_workers: dict[str, bool] = {}


async def process_episode_queue(group_id: str):
    """Process episodes for a specific group_id sequentially.

    This function runs as a long-lived task that processes episodes
    from the queue one at a time.
    """
    global queue_workers

    logger.info(f'Starting episode queue worker for group_id: {group_id}')
    queue_workers[group_id] = True

    try:
        while True:
            # Get the next episode processing function from the queue
            # This will wait if the queue is empty
            process_func = await episode_queues[group_id].get()

            try:
                # Process the episode
                await process_func()
            except Exception as e:
                logger.error(f'Error processing queued episode for group_id {group_id}: {str(e)}')
            finally:
                # Mark the task as done regardless of success/failure
                episode_queues[group_id].task_done()
    except asyncio.CancelledError:
        logger.info(f'Episode queue worker for group_id {group_id} was cancelled')
    except Exception as e:
        logger.error(f'Unexpected error in queue worker for group_id {group_id}: {str(e)}')
    finally:
        queue_workers[group_id] = False
        logger.info(f'Stopped episode queue worker for group_id: {group_id}')


@mcp.tool()
async def add_episode_to_graph_memory(
    name: Annotated[str, Field(description='Name of the episode')],
    episode_body: Annotated[str, Field(description='The content of the episode...')],
    group_id: Annotated[str, Field(description='A unique ID for this graph (use empty string for default)')] = "",
    source: Annotated[str, Field(description="Source type...")] = "text",
    source_description: Annotated[str, Field(description='Description of the source')] = "",
    uuid: Annotated[str, Field(description='Optional UUID for the episode (use empty string for none)')] = "",
) -> SuccessResponse | ErrorResponse:
    """Add an episode to graph memory. This is the primary way to add information to the knowledge graph.

    This function returns immediately and processes the episode addition in the background.
    Episodes for the same group_id are processed sequentially to avoid race conditions.

    Args:
        name (str): Name of the episode
        episode_body (str): The content of the episode to persist to memory. When source='json', this must be a
                           properly escaped JSON string, not a raw Python dictionary. The JSON data will be
                           automatically processed to extract entities and relationships.
        group_id (str, optional): A unique ID for this graph. If not provided, uses the default group_id from CLI
                                 or a generated one.
        source (str, optional): Source type, must be one of:
                               - 'text': For plain text content (default)
                               - 'json': For structured data
                               - 'message': For conversation-style content
        source_description (str, optional): Description of the source
        uuid (str, optional): Optional UUID for the episode

    Examples:
        # Adding plain text content
        add_memory(
            name="Company News",
            episode_body="Acme Corp announced a new product line today.",
            source="text",
            source_description="news article",
            group_id="some_arbitrary_string"
        )

        # Adding structured JSON data
        # NOTE: episode_body must be a properly escaped JSON string. Note the triple backslashes
        add_memory(
            name="Customer Profile",
            episode_body="{\\\"company\\\": {\\\"name\\\": \\\"Acme Technologies\\\"}, \\\"products\\\": [{\\\"id\\\": \\\"P001\\\", \\\"name\\\": \\\"CloudSync\\\"}, {\\\"id\\\": \\\"P002\\\", \\\"name\\\": \\\"DataMiner\\\"}]}",
            source="json",
            source_description="CRM data"
        )

        # Adding message-style content
        add_memory(
            name="Customer Conversation",
            episode_body="user: What's your return policy?\nassistant: You can return items within 30 days.",
            source="message",
            source_description="chat transcript",
            group_id="some_arbitrary_string"
        )

    Notes:
        When using source='json':
        - The JSON must be a properly escaped string, not a raw Python dictionary
        - The JSON will be automatically processed to extract entities and relationships
        - Complex nested structures are supported (arrays, nested objects, mixed data types), but keep nesting to a minimum
        - Entities will be created from appropriate JSON properties
        - Relationships between entities will be established based on the JSON structure
    """
    global graphiti_client, episode_queues, queue_workers

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        # Map string source to EpisodeType enum
        source_type = EpisodeType.text
        if source.lower() == 'message':
            source_type = EpisodeType.message
        elif source.lower() == 'json':
            source_type = EpisodeType.json

        group_id_val = group_id or None
        uuid_val = uuid or None

        # Use the provided group_id or fall back to the default from config
        effective_group_id = group_id_val if group_id_val is not None else config.group_id

        # Cast group_id to str to satisfy type checker
        # The Graphiti client expects a str for group_id, not Optional[str]
        group_id_str = str(effective_group_id) if effective_group_id is not None else ""

        # We've already checked that graphiti_client is not None above
        # This assert statement helps type checkers understand that graphiti_client is defined
        assert graphiti_client is not None, 'graphiti_client should not be None here'

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # Define the episode processing function
        async def process_episode():
            try:
                logger.info(f"Processing queued episode '{name}' for group_id: {group_id_str}")
                # Use all entity types if use_custom_entities is enabled, otherwise use empty dict
                entity_types = ENTITY_TYPES if config.use_custom_entities else {}

                await client.add_episode(
                    name=name,
                    episode_body=episode_body,
                    source=source_type,
                    source_description=source_description,
                    group_id=group_id_str,
                    uuid=uuid_val,
                    reference_time=datetime.now(timezone.utc),
                    entity_types=entity_types,
                )
                logger.info(f"Episode '{name}' added successfully")

                logger.info(f"Episode '{name}' processed successfully")
            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"Error processing episode '{name}' for group_id {group_id_str}: {error_msg}"
                )

        # Initialize queue for this group_id if it doesn't exist
        if group_id_str not in episode_queues:
            episode_queues[group_id_str] = asyncio.Queue()

        # Add the episode processing function to the queue
        await episode_queues[group_id_str].put(process_episode)

        # Start a worker for this queue if one isn't already running
        if not queue_workers.get(group_id_str, False):
            asyncio.create_task(process_episode_queue(group_id_str))

        # Return immediately with a success message
        return SuccessResponse(
            message=f"Episode '{name}' queued for processing (position: {episode_queues[group_id_str].qsize()})"
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error queuing episode task: {error_msg}')
        return ErrorResponse(error=f'Error queuing episode task: {error_msg}')


@mcp.tool()
async def search_graph_memory_nodes(
    query: Annotated[str, Field(description='The search query')],
    group_ids: Annotated[List[str], Field(description='Optional list of group IDs (empty to use default)')] = [],
    max_nodes: Annotated[int, Field(description='Maximum number of nodes to return')] = 10,
    center_node_uuid: Annotated[str, Field(description='Optional UUID (empty string to ignore)')] = "",
    entity: Annotated[str, Field(description='Optional single entity type ("" for none)')] = "",
) -> NodeSearchResponse | ErrorResponse:
    """Search the graph memory for relevant node summaries. These contain a summary of all of a node's relationships with other nodes.

    Note: entity is a single entity type to filter results (permitted: "Preference", "Procedure").

    Args:
        query: The search query
        group_ids: Optional list of group IDs to filter results
        max_nodes: Maximum number of nodes to return (default: 10)
        center_node_uuid: Optional UUID of a node to center the search around
        entity: Optional single entity type to filter results (permitted: "Preference", "Procedure")
    """
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        group_ids_val = group_ids or [config.group_id] if config.group_id else []
        center_uuid_val = center_node_uuid or None

        # Configure the search
        if center_uuid_val is not None:
            search_config = NODE_HYBRID_SEARCH_NODE_DISTANCE.model_copy(deep=True)
        else:
            search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
        search_config.limit = max_nodes

        filters = SearchFilters()
        if entity != '':
            filters.node_labels = [entity]

        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # Perform the search using the _search method
        search_results = await client._search(
            query=query,
            config=search_config,
            group_ids=group_ids_val,
            center_node_uuid=center_uuid_val,
            search_filter=filters,
        )

        if not search_results.nodes:
            return NodeSearchResponse(message='No relevant nodes found', nodes=[])

        # Format the node results
        formatted_nodes: list[NodeResult] = [
            {
                'uuid': node.uuid,
                'name': node.name,
                'summary': node.summary if hasattr(node, 'summary') else '',
                'labels': node.labels if hasattr(node, 'labels') else [],
                'group_id': node.group_id,
                'created_at': node.created_at.isoformat(),
                'attributes': node.attributes if hasattr(node, 'attributes') else {},
            }
            for node in search_results.nodes
        ]

        return NodeSearchResponse(message='Nodes retrieved successfully', nodes=formatted_nodes)
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error searching nodes: {error_msg}')
        return ErrorResponse(error=f'Error searching nodes: {error_msg}')


@mcp.tool()
async def search_graph_memory_facts(
    query: Annotated[str, Field(description='The search query')],
    group_ids: Annotated[List[str], Field(description='Optional list of group IDs (empty to use default)')] = [],
    max_facts: Annotated[int, Field(description='Maximum number of facts to return')] = 10,
    center_node_uuid: Annotated[str, Field(description='Optional UUID (empty string to ignore)')] = "",
) -> FactSearchResponse | ErrorResponse:
    """Search the graph memory for relevant facts.

    Args:
        query: The search query
        group_ids: Optional list of group IDs to filter results
        max_facts: Maximum number of facts to return (default: 10)
        center_node_uuid: Optional UUID of a node to center the search around
    """
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        # Validate max_facts parameter
        if max_facts <= 0:
            return ErrorResponse(error='max_facts must be a positive integer')

        group_ids_val = group_ids or [config.group_id] if config.group_id else []
        center_uuid_val = center_node_uuid or None

        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        relevant_edges = await client.search(
            group_ids=group_ids_val,
            query=query,
            num_results=max_facts,
            center_node_uuid=center_uuid_val,
        )

        if not relevant_edges:
            return FactSearchResponse(message='No relevant facts found', facts=[])

        facts = [format_fact_result(edge) for edge in relevant_edges]
        return FactSearchResponse(message='Facts retrieved successfully', facts=facts)
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error searching facts: {error_msg}')
        return ErrorResponse(error=f'Error searching facts: {error_msg}')


@mcp.tool()
async def delete_entity_edge(
    uuid: Annotated[str, Field(description='UUID of the entity edge to delete')]
) -> SuccessResponse | ErrorResponse:
    """Delete an entity edge from the graph memory.

    Args:
        uuid: UUID of the entity edge to delete
    """
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # Get the entity edge by UUID
        entity_edge = await EntityEdge.get_by_uuid(client.driver, uuid)
        # Delete the edge using its delete method
        await entity_edge.delete(client.driver)
        return SuccessResponse(message=f'Entity edge with UUID {uuid} deleted successfully')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error deleting entity edge: {error_msg}')
        return ErrorResponse(error=f'Error deleting entity edge: {error_msg}')


@mcp.tool()
async def delete_episode(
    uuid: Annotated[str, Field(description='UUID of the episode to delete')]
) -> SuccessResponse | ErrorResponse:
    """Delete an episode from the graph memory.

    Args:
        uuid: UUID of the episode to delete
    """
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # Get the episodic node by UUID - EpisodicNode is already imported at the top
        episodic_node = await EpisodicNode.get_by_uuid(client.driver, uuid)
        # Delete the node using its delete method
        await episodic_node.delete(client.driver)
        return SuccessResponse(message=f'Episode with UUID {uuid} deleted successfully')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error deleting episode: {error_msg}')
        return ErrorResponse(error=f'Error deleting episode: {error_msg}')


@mcp.tool()
async def get_entity_edge(
    uuid: Annotated[str, Field(description='UUID of the entity edge to retrieve')]
) -> dict[str, Any] | ErrorResponse:
    """Get an entity edge from the graph memory by its UUID.

    Args:
        uuid: UUID of the entity edge to retrieve
    """
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # Get the entity edge directly using the EntityEdge class method
        entity_edge = await EntityEdge.get_by_uuid(client.driver, uuid)

        # Use the format_fact_result function to serialize the edge
        # Return the Python dict directly - MCP will handle serialization
        return format_fact_result(entity_edge)
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error getting entity edge: {error_msg}')
        return ErrorResponse(error=f'Error getting entity edge: {error_msg}')


@mcp.tool()
async def get_episodes(
    group_id: Annotated[str, Field(description='ID of the group (use empty string for default)')] = "",
    last_n: Annotated[int, Field(description='Number of most recent episodes')] = 10,
) -> list[dict[str, Any]] | EpisodeSearchResponse | ErrorResponse:
    """Get the most recent memory episodes for a specific group.

    Args:
        group_id: ID of the group to retrieve episodes from. If not provided, uses the default group_id.
        last_n: Number of most recent episodes to retrieve (default: 10)
    """
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    group_id_val = group_id or config.group_id
    if not isinstance(group_id_val, str):
        return ErrorResponse(error='Group ID must be a string')

    try:
        if not isinstance(effective_group_id, str):
            return ErrorResponse(error='Group ID must be a string')

        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        episodes = await client.retrieve_episodes(
            group_ids=[group_id_val],
            last_n=last_n,
            reference_time=datetime.now(timezone.utc)
        )

        if not episodes:
            return EpisodeSearchResponse(
                message=f'No episodes found for group {group_id_val}', episodes=[]
            )

        # Use Pydantic's model_dump method for EpisodicNode serialization
        formatted_episodes = [
            # Use mode='json' to handle datetime serialization
            episode.model_dump(mode='json')
            for episode in episodes
        ]

        # Return the Python list directly - MCP will handle serialization
        return formatted_episodes
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error getting episodes: {error_msg}')
        return ErrorResponse(error=f'Error getting episodes: {error_msg}')


@mcp.tool()
async def clear_graph() -> SuccessResponse | ErrorResponse:
    """Clear all data from the graph memory and rebuild indices."""
    global graphiti_client

    if graphiti_client is None:
        return ErrorResponse(error='Graphiti client not initialized')

    try:
        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # clear_data is already imported at the top
        await clear_data(client.driver)
        await client.build_indices_and_constraints()
        return SuccessResponse(message='Graph cleared successfully and indices rebuilt')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error clearing graph: {error_msg}')
        return ErrorResponse(error=f'Error clearing graph: {error_msg}')


@mcp.resource('http://graphiti/status')
async def get_status() -> StatusResponse:
    """Get the status of the Graphiti MCP server and Neo4j connection."""
    global graphiti_client

    if graphiti_client is None:
        return StatusResponse(status='error', message='Graphiti client not initialized')

    try:
        # We've already checked that graphiti_client is not None above
        assert graphiti_client is not None

        # Use cast to help the type checker understand that graphiti_client is not None
        client = cast(Graphiti, graphiti_client)

        # Test database connection
        await client.driver.client.verify_connectivity()  # type: ignore

        return StatusResponse(
            status='ok', message='Graphiti MCP server is running and connected to Neo4j'
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error checking Neo4j connection: {error_msg}')
        return StatusResponse(
            status='error',
            message=f'Graphiti MCP server is running but Neo4j connection failed: {error_msg}',
        )


async def initialize_server() -> MCPConfig:
    """Parse CLI arguments and initialize the Graphiti server configuration."""
    global config

    parser = argparse.ArgumentParser(
        description='Run the Graphiti MCP server with optional LLM client'
    )
    parser.add_argument(
        '--group-id',
        help='Namespace for the graph. This is an arbitrary string used to organize related data. '
        'If not provided, a random UUID will be generated.',
    )
    parser.add_argument(
        '--transport',
        choices=['sse', 'stdio'],
        default='sse',
        help='Transport to use for communication with the client. (default: sse)',
    )
    parser.add_argument(
        '--model', help=f'Model name to use with the LLM client. (default: {DEFAULT_LLM_MODEL})'
    )
    parser.add_argument(
        '--small-model',
        help=f'Small model name to use with the LLM client. (default: {SMALL_LLM_MODEL})',
    )
    parser.add_argument(
        '--temperature',
        type=float,
        help='Temperature setting for the LLM (0.0-2.0). Lower values make output more deterministic. (default: 0.7)',
    )
    parser.add_argument('--destroy-graph', action='store_true', help='Destroy all Graphiti graphs')
    parser.add_argument(
        '--use-custom-entities',
        action='store_true',
        help='Enable entity extraction using the predefined ENTITY_TYPES',
    )
    parser.add_argument(
        '--host',
        default=os.environ.get('MCP_SERVER_HOST'),
        help='Host to bind the MCP server to (default: MCP_SERVER_HOST environment variable)',
    )

    args = parser.parse_args()

    # Build configuration from CLI arguments and environment variables
    config = GraphitiConfig.from_cli_and_env(args)

    # Log the group ID configuration
    if args.group_id:
        logger.info(f'Using provided group_id: {config.group_id}')
    else:
        logger.info(f'Generated random group_id: {config.group_id}')

    # Log entity extraction configuration
    if config.use_custom_entities:
        logger.info('Entity extraction enabled using predefined ENTITY_TYPES')
    else:
        logger.info('Entity extraction disabled (no custom entities will be used)')

    # Initialize Graphiti
    await initialize_graphiti()

    if args.host:
        logger.info(f'Setting MCP server host to: {args.host}')
        # Set MCP server host from CLI or env
        mcp.settings.host = args.host

    # Return MCP configuration
    return MCPConfig.from_cli(args)


async def run_mcp_server():
    mcp_config = await initialize_server()
    logger.info(f'Starting MCP server with transport: {mcp_config.transport}')
    await mcp.run_async(
        transport='http', # use streamable http rather than sse
        host=mcp.settings.host or '0.0.0.0',
        port=mcp.settings.port or 8000
    )


if __name__ == '__main__':
    asyncio.run(run_mcp_server())
