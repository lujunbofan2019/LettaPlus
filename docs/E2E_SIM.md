# Agent workflow schema review

Hello! I'd like to collaborate with you on an idea I had recently in the area of Agentic AI.

I think AI agents are smart autonomous entities that can understand human intents and help achieve their goals by solving fairly complex problems end-to-end.
From this point of view, what an AI agent does is essentially problem-solving and automated execution of tasks step-by-step, until a goal has been reached.
For an AI agent to be effective, it shall come up with a "workflow" (or SOP), which the agent may constantly improve during a conversation with a human user
while establishing an increasingly correct and accurate understanding of the human's intention. Once the workflow looks perfect, the AI agent will start to
fulfil the steps, either by itself, or by the team work of multiple fellow AI agents, each specialized in one problem domain, and equipped with appropriate
"skills" and tools.

What I'm trying to achieve is a way for the AI agent to document such workflows in terms of json files. The benefit is that in this way the AI agent is
"learning" and "remembering" the best practices that it has discovered in the past. Next time it encounters a similar challenge, previously established
workflows can be reused as building blocks, e.g. slightly adapted to achieve a similar goal, expanded or joined together to achieve a larger or more complex
goal, or improved/upgraded to achieve the same goal with a better solution. Ideally, a formal schema shall be defined for this purpose, so that AI agents can
document and reused such workflows in a compatible way, i.e. the workflows become transferable skills, what one agent documented can be understood and adopted
by another agent.

Such autonomous AI agents require robust memory systems to learn from past interactions, maintain context over extended periods, and make informed decisions. 
Without a persistent and multifaceted memory, agents suffer from a form of "digital amnesia," limiting their ability to evolve or handle complex, multi-step
tasks. Existing memory architectures, while powerful in specific contexts, present significant limitations when used in isolation. Hence, I envision a hybrid
memory layer for an autonomous AI agent that combines:

1. A temporally-aware knowledge graph: This serves as the agent's structured, long-term memory and reasoning engine. It stores entities, events, and their
   relationships, updating dynamically to reflect the agent's entire life experience. This enables the agent to perform complex, multi-hop reasoning and adapt 
   its strategies based on historical outcomes.
2. Hierarchical memory blocks: Implemented via a framework like Letta (previously called MemGPT), this component manages conversational context. It provides
   the agent with an effective working memory for immediate recall and an archival memory for perpetual conversational history, allowing it to remember specific
   facts and interactions with users over time.
3. An external vector store interface: This component is used to index and retrieve bulky, verbose data such as PDFs, technical documents, or lengthy notes.
   By offloading this content to an external store, the core memory system remains lean and efficient, fetching rich, detailed information on-demand via semantic
   search without cluttering the knowledge graph or memory blocks.

Together, these components provide a synergistic memory architecture where the structured reasoning of the knowledge graph, the chronological recall of memory
blocks, and the semantic search of the vector store work in concert to provide a comprehensive and efficient memory layer.

As you can tell, the overall system design can be quite complex, which involves at least the following key aspects:

1. Definition and packaging of reusable "skills". These are essentially JSON files that contain useful system prompts, data sources, tools (Python source code,
   MCP servers, etc), and other types of resources needed for an AI agent to perform a single task.
2. Definition and packaging of end-to-end "workflows". Again, these are also JSON files that prescribe how a complex problem is solved over multiple steps, where
   each step is to perform a single task with a known skill.
3. Supporting facilities for an AI agent to make sense of a workflow file, and to execute through the steps, while dynamically loading and unloading necessary
   skills to itself.
4. Collaboration protocol for multiple AI agents to deliver the same workflow jointly as team work, each taking ownership of some steps respectively and communicating
   with other agents in a choreography fashion.
5. Effective hybrid memory management mechanism that combines Letta's memory blocks with a temporal-aware knowledge graph, so that a planner AI agent can learn
   and evolve overtime, become able to understand human intentions and come up with solid workflows for solving complex problems over multiple steps.

Over the past 12 months, I have been working alone on this project and making some progress in different areas. I have been both busy coding on several sub-projects
and writing up about the solution and key concepts. However, one problem I noticed is that I wrote many documents in different tones and formats, e.g. some technical
like README file for source code repos, some others academic like research papers and patent applications. Furthermore, every time I wrote about things, there tends
to be a particular focus in my mind, so none of the documents looked detailed and comprehensive enough - they only captured and highlighted some part of the overall
solution with other aspects missing or mentioned briefly.

Therefore, I need your help to review all these documents, develop an in-depth understanding of the overall solution, and "stitch together" a nice all-in-one article
that articulates all aspects of the work clearly. I can review your work and provide feedback, so that we can collaborate until the article is in an ideal shape.
Can you help me with that?










README

TEST PLAN

Optional: Sample context window






Ask for e2e simulation:
- receiving a user prompt relating to a task
- processing the prompt and storing it in the relevant memory/memories, including the context window
- finding any data or docs indicated by the prompt, sourcing them, storing them into the vector store, and importing some or all of the relevant info from them into the context window
- determining whether the context window includes relevant conversational info, and if not, searching for and retrieving it from cache or archival storage
- determining whether current capabilities are adequate to perform at least one step forming part of the task, and if not, searching for a suitable capability in the repository store (this is the “identifying a capability gap” from claim 1 of the DCF claims, so it’s particularly important that we provide good detail here)
- loading the identified capability and any tools/data into the context window (including explaining how the manifest is used)
- prompting the LLM with the resultant prompt
- testing to see whether the LLM output indicated the prompt was successful
- recording the results of the test in the knowledge base
- if successful, reporting to the user (or moving to the next step in the task)
- consider whether to unload the capability that was needed for the previous step
- if not successful, trying again (presumably for some number of times)
  - unloading the unsuccessful capability
  - finding and loading a new one, and repeat process above





OpenAI Agent Builder as alternative