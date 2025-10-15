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







Document checklist:
- README.md: a technical readme file that explains the contents of a source code repo and their purposes;
- DCF-Patent-Proposal.md: an early stage document about the Dynamic Capability Framework, written in the format of a patent proposal;
- Hybrid-Memory-Patent-Proposal.md: an additional document that provides complementary information to the previous DCF proposal;
- Self-Evolving-Agent-Architecture.md: a more recent document that attempted to combine DCF and Hybrid Memory together.






Thanks, but I don't like the case study scenario very much. How about I tell you a different scenario that is actually used by Selina Finance? I think it may be more
realistic and interesting. Before we fully agree to the case study scenario, please don't attempt to make assumptions or write any other part of the case study.

OK, the new scenario I'd like to suggest is the Advice Call Analysis, which is a key part of Selina Finance's Service Quality Assurance process that comes from the Legal
and Compliance Department. As an FCA regulated Financial Service Provider, Selina is subject to rigorous customer duties and other related regulations for mortgage or
loan advice. Our customer facing team, such as case managers, mortgage advisors, and post-disbursement loan servicing team, constantly speak with customers over phone
calls. We use a telephony service to record such phone calls automatically, and the output mp3 files are associated to the customer's profile. For various reasons, we
may want to examine the quality of such advisory calls, for example:

1. To make sure newly onboarded advisors have been following the rules and keeping up with the company's quality standard.
2. To make sure newly rolled out financial products are well-understood by staff members after training.
3. To make sure the company has been sticking to the FCA's regulations, such as financial promotions and consumer duty.

Hence, quite often line managers and members of the Legal and Compliance team may need to run examinations on recordings, either randomly selected or specifically
targeted. Without AI automation, it used to take a huge amount of time and human effort to listen to such the recordings, making notes and carrying out analysis
manually. With AI automation, we can create diversified skills, including but not limited to:

1) Salesforce integration - tools for consuming Salesforce APIs and running queries to find pertinent data and files belonging to certain customers and opportunities.
2) Recording management - system instructions and tools for retrieving mp3 files by metadata, such as file name, opportunity id, customer's or advisor's name.
3) Recording transcription - tools for converting mp3 recordings into plain text transcripts, such as Whisper and AssemblyAI.
4) Transcript diarization - tools for identifying different speakers and their utterances, as well as reformatting plain text transcripts from a word cloud into clear
   dialogue captions with timestamps.
5) Transcript segmentation and labelling - system instructions for a LLM to separate a long dialogue into smaller logical segments, as well as label each segment with
   a clear category, such as introduction, security check, mandatory disclosure, applicants' details, income validation, credit commitments, expenditure, soft search,
   product detail, offer explanation, and so on.
6) Sentiment analysis - system instructions for a LLM to identify tone of voice and potential issues in a conversation, such as anxiety, vulnerability, confusion, etc.
7) Compliance analysis - tools for retrieving the latest regulatory guidance and rules from a vector store, and system instructions for a LLM to evaluate a transcript
   against each of the rules and draw a binary conclusion (i.e. Y or N) whether the transcript is compliant.
8) Scoring - tools for retrieving the latest scoring criteria from a vector store, and system instructions for a LLM to calculate a transcript's overall score given its
   sentiment and compliance analysis results.

The Engineering team is responsible for developing the skills above, ensuring their correctness and availability to the AI agent. However, the internal structure of the
system may not be transparent and appreciated by end users, especially business people who are not tech-savvy. In practice, when end users interact with the AI agent,
they would assume (or be told by others) that the agent has the capability of performing Advice Call Analysis. In this case, there are three possible situations:

A. Advice Call Analysis is a pre-defined capability, of which a JSON workflow file has been readily available for an AI agent to grab. A DCF-enabled agent can do a
   semantic search and discover this JSON file from a vector store. So, it would kickstart the workflow according to the JSON prescription, creating a group of worker
   agents, each of which will load the skill manifest for their corresponding task, and complete the workflow collaboratively.

B. Advice Call Analysis is a pre-defined capability, which shall be executed end-to-end without any issues. However, due to a temporary problem, one of the steps/skills
   may keep failing, e.g. AssemblyAI's transcribing API does not respond. In this case, the worker agent would have to fall back to an alternative skill for the same
   purpose that uses Whisper API instead. After this incident, the agent would update the knowledge graph about AssemblyAI's success rate, so that Whisper may become
   the top choice in a future version of the capability definition.

C. Advice Call Analysis is not a pre-defined capability, and thus the AI agent would need to figure out the desirable workflow by conversing with the end user. Here, we
   would need to simulate the conversation between the AI agent and the end user, e.g.:

User: Alice is a new mortgage advisor, and thus I'd like to work out the scores of the customer calls she did last week.

Agent: What do you think about the following workflow: 1) retrieve opportunities from Salesforce that Alice worked on last week -> 2) download call recordings that are
associated with these opportunities -> 3) transcribe the recordings using AssemblyAI -> 4) score the transcripts.

User: There are a couple of issues in this workflow. After step 3, you should refine the transcripts with proper diarization and additional labelling. Then, you should
perform sentiment analysis and compliance analysis. Finally, you can do step 4 and obtain the over score.

Agent: Understood. So, the workflow should look like: 1) retrieve opportunities from Salesforce that Alice worked on last week -> 2) download call recordings that are
associated with these opportunities -> 3) transcribe the recordings using AssemblyAI -> 4) perform diarization -> 5) perform labelling -> 6.1) perform sentiment analysis
-> 6.2) perform compliance analysis -> 7) score the transcripts. I think for each transcript step 6.1 and 6.2 can be executed in parallel. Shall we try to run this
workflow for one call recording and see how it goes?

User: Sure, please go ahead!





E2E simulation:
- receiving a user prompt relating to a complex task;
- processing the prompt and storing it in the relevant memory/memories, including the context window;
- finding any data or docs indicated by the prompt, sourcing them, storing them into the vector store, and importing some or all of the relevant info from them into the context window;
- determining whether the context window includes relevant conversational info, and if not, searching for and retrieving it from cache or archival storage;
- determining whether current capabilities are adequate to perform at least one-step forming part of the task, and if not, searching for a suitable capability in the repository store
  (this is the “identifying a capability gap” from DCF, so it’s particularly important that we provide good detail here);
- loading the identified capability and any tools/data into the context window (including explaining how the manifest is used);
- prompting the LLM with the resultant prompt;
- testing to see whether the LLM output indicated the prompt was successful;
- recording the results of the test in the knowledge base;
- if successful, reporting to the user (or moving to the next step in the task);
- consider whether to unload the capability that was needed for the previous step;
- if not successful, trying again (presumably for some number of times)
  - unloading the unsuccessful capability;
  - finding and loading a new one, and repeat process above.


