Hello! I'd like to collaborate with you on an idea I had recently in the area of Agentic AI.

I think AI agents are smart autonomous entities that can understand human intents and help achieve their goals by solving fairly complex problems end-to-end. From this point of view, what an AI agent does is essentially problem-solving and automated execution of tasks step-by-step, until a goal has been reached. For an AI agent to be effective, it shall come up with a "workflow" (or SOP), which the agent may constantly improve during a conversation with a human user
while establishing an increasingly correct and accurate understanding of the human's intention. Once the workflow looks perfect, the AI agent will start to fulfil the steps, either by itself, or by the team work of multiple fellow AI agents, each specialized in one problem domain, and equipped with appropriate "skills" and tools.

What I'm trying to achieve is a way for the AI agent to document such workflows in terms of json files. The benefit is that in this way the AI agent is "learning" and "remembering" the best practices that it has discovered in the past. Next time it encounters a similar challenge, previously established workflows can be reused as building blocks, e.g. slightly adapted to achieve a similar goal, expanded or joined together to achieve a larger or more complex goal, or improved/upgraded to achieve the same goal with a better solution. Ideally, a formal schema shall be defined for this purpose, so that AI agents can document and reused such workflows in a compatible way, i.e. the workflows become transferable skills, what one agent documented can be understood and adopted by another agent.

Such autonomous AI agents require robust memory systems to learn from past interactions, maintain context over extended periods, and make informed decisions. Without a persistent and multifaceted memory, agents suffer from a form of "digital amnesia," limiting their ability to evolve or handle complex, multi-step tasks. Existing memory architectures, while powerful in specific contexts, present significant limitations when used in isolation. Hence, I envision a hybrid
memory layer for an autonomous AI agent that combines:

1. A temporally-aware knowledge graph: This serves as the agent's structured, long-term memory and reasoning engine. It stores entities, events, and their relationships, updating dynamically to reflect the agent's entire life experience. This enables the agent to perform complex, multi-hop reasoning and adapt its strategies based on historical outcomes.
2. Hierarchical memory blocks: Implemented via a framework like Letta (previously called MemGPT), this component manages conversational context. It provides the agent with an effective working memory for immediate recall and an archival memory for perpetual conversational history, allowing it to remember specific facts and interactions with users over time.
3. An external vector store interface: This component is used to index and retrieve bulky, verbose data such as PDFs, technical documents, or lengthy notes. By offloading this content to an external store, the core memory system remains lean and efficient, fetching rich, detailed information on-demand via semantic search without cluttering the knowledge graph or memory blocks.

Together, these components provide a synergistic memory architecture where the structured reasoning of the knowledge graph, the chronological recall of memory blocks, and the semantic search of the vector store work in concert to provide a comprehensive and efficient memory layer.

As you can tell, the overall system design can be quite complex, which involves at least the following key aspects:

1. Definition and packaging of reusable "skills". These are essentially JSON files that contain useful system prompts, data sources, tools (Python source code, MCP servers, etc), and other types of resources needed for an AI agent to perform a single task.
2. Definition and packaging of end-to-end "workflows". Again, these are also JSON files that prescribe how a complex problem is solved over multiple steps, where each step is to perform a single task with a known skill.
3. Supporting facilities for an AI agent to make sense of a workflow file, and to execute through the steps, while dynamically loading and unloading necessary skills to itself.
4. Collaboration protocol for multiple AI agents to deliver the same workflow jointly as team work, each taking ownership of some steps respectively and communicating with other agents in a choreography fashion.
5. Effective hybrid memory management mechanism that combines Letta's memory blocks with a temporal-aware knowledge graph, so that a planner AI agent can learn and evolve overtime, become able to understand human intentions and come up with solid workflows for solving complex problems over multiple steps.

Over the past 12 months, I have been working alone on this project and making some progress in different areas. I have been both busy coding and writing up about the solution and key concepts. However, one problem I noticed is that I wrote many documents in different tones and formats, e.g.

- README.md is a technical readme file that explains the contents of this repo;
- docs/DCF-Patent-Proposal.md is an early stage document about the Dynamic Capability Framework, written in the format of a patent proposal;
- docs/Hybrid-Memory-Patent-Proposal.md is an additional document that provides complementary information to the previous DCF proposal;
- docs/Self-Evolving-Agent-Architecture.md is a more recent document that attempted to combine DCF and Hybrid Memory together.
- docs/Self-Evolving-Agent-Whitepaper.md and docs/Self-Evolving-Agent-Academic.md are brief descriptions of the overall system design in slightly different tones.

Therefore, I need your help to review all these documents, develop an in-depth understanding of the overall solution, and "stitch together" a nice all-in-one article that articulates all aspects of the work clearly. I can review your work and provide feedback, so that we can iterate until the article is in an ideal shape. Can you help me with that?

PS. Probably you would need to review the files under the schemas and tools/dcf folders, in order to grasp an in-depth understanding of the implementation details.






docs/TESTING_PLAN.md provides a lightweight use case scenario, which may be used to test the correctness of the system implementation progressively. However, I got the following feedback from a colleague:

- receiving a user prompt relating to a complex task;
- processing the prompt and storing it in the relevant memory/memories, including the context window;
- finding any data or docs indicated by the prompt, sourcing them, storing them into the vector store, and importing some or all of the relevant info from them into the context window;
- determining whether the context window includes relevant conversational info, and if not, searching for and retrieving it from cache or archival storage;
- determining whether current capabilities are adequate to perform at least one-step forming part of the task, and if not, searching for a suitable capability in the repository store (this is the “identifying a capability gap” from DCF, so it’s particularly important that we provide good detail here);
- loading the identified capability and any tools/data into the context window (including explaining how the manifest is used);
- prompting the LLM with the resultant prompt;
- testing to see whether the LLM output indicated the prompt was successful;
- recording the results of the test in the knowledge base;
  - if successful, reporting to the user (or moving to the next step in the task);
    - consider whether to unload the capability that was needed for the previous step;
  - if not successful, trying again (presumably for some number of times)
    - unloading the unsuccessful capability;
    - finding and loading a new one, and repeat process above.

So, as you can tell, my colleague is seeking for something like a worked example, to fully illustrate how the system takes actions in practice. I think the existing TESTING_PLAN does not fit to this purpose.

Instead, what we provide to the audience should consist of the following key points:

1. A fairly complex use case scenario that represents a realistic business problem solved at Selina Finance using autonomous AI agents.
2. Vivid simulation of the end-to-end workflow, including:
   - conversation messages between a human user and an AI agent (the Planner);
   - the agent's chain of thought (CoT);
   - the workflow JSON and skill manifests referred;
   - tool calling actions and corresponding input and output;
   - new memory blocks generated;
   - new episodes, entities, and relationships added to the knowledge graph;
   - files and data retrieved from a vector store;
   - new worker agents created and their notifications;
   - new control-plane created and change of its state;
   - Letta's actions for context window management.
3. Articulations of key design features, such as self-learning and self-evolving workflow/capability creation, dynamic loading and unloading of skills, leveraging a hybrid memory layer, all illustrated by actual and concrete actions taken throughout the worked example.

Let me help by providing you a good use case scenario for getting this job done. It is about "Advice Call Analysis", which is a key part of Selina Finance's Quality Assurance process owned by the Legal & Compliance Department.

As an FCA regulated financial service provider, Selina is subject to rigorous customer duties and other regulations. Our case managers, mortgage advisors, and customer service teams constantly speak with customers over phone calls. We use a telephony service to record such phone calls and save the output mp3 files to Cloud buckets.

Quite often, line managers and members of Legal & Compliance need to exam such recordings to ensure:
1. Newly onboarded advisors have been following the rules and keeping up with the company's quality standard.
2. Newly rolled out financial products are well-understood by staff members after training courses.
3. Generally speaking, the company has been sticking to the FCA's regulations for consumer duty, financial promotions, etc.

Without AI automation, it used to take a huge amount of time and human effort to listen to such recordings, make notes, and carry out manual analysis. With AI automation, a human user may simply highlight what they are trying to achieve, and let an AI agent to get the work done.

Our engineering team have developed diversified skills for the AI agent to adopt, including but not limited to:

1) Salesforce Integration skill - to consume Salesforce APIs and run various queries, e.g. to find out details about opportunities, loan applications, and staff members assigned to applications.
2) Recording Management skill - to retrieve mp3 files by a wide range of metadata, such as file name, date and time, opportunity id, application id, customer name, and advisor name.
3) Transcribing skill - to convert a mp3 file into plain texts. Note: there are multiple implementations, such as using Whisper or AssemblyAI as different backends - they can be used alternatively with pros and cons, and they can serve as each other's backup method.
4) Diarization skill - to identify different speakers and their utterances during a conversation, so as to reformat transcripts from a word cloud into a clearer dialogue format with accurate timestamps. Again, there are multiple implementations, such as using GPT-4o or Gemini 2.0 Pro as different backends.
5) Labelling & Segmentation skill - to separate a long transcript into smaller segments and label them with categories, such as introduction, security check, mandatory disclosure, applicant detail, income validation, credit commitment, expenditure, soft search, product detail, offer explanation, etc. Depending on the scope of analysis, sometimes only certain segments of a transcript is needed rather than the whole.
6) Sentiment analysis skill - to identify potential issues in a conversation, such as anxiety, vulnerability, confusion, etc.
7) Compliance analysis skill - to retrieve a set of the latest regulatory rules from a vector store, and then evaluate a transcript against each of the rules to draw a binary conclusion (Y or N) whether the transcript is compliant from that perspective.
8) Scoring skill - to retrieve the latest scoring formula from a vector store, and accordingly, calculate a transcript's overall score given its sentiment and compliance analysis results.

The first time a user asks the Planner AI agent to perform an Advice Call Analysis task, the agent may not be fully aware of the ideal workflow for doing it, i.e. there is a capability gap. So, the agent converses with the human user to fully apprehend their intention and agree to a workflow:

a) Given advisor's name and date range, find loan application ids from Salesforce;
b) Retrieve call recordings done by the advisor for these applications;
c) Transcribe the recordings into plain texts;
d) Run sentiment and compliance analysis in parallel;
e) Score the transcripts based on the sentiment and compliance analysis results.

Then, the Planner agent can go ahead with a test run on a single recording, of which we simulate everything as it happened.

Upon a successful outcome, the Planner agent saves the workflow as a JSON file in the vector store for future reuse.

Later on, a different user asks the Planner AI agent to make sure a recent training course was effective, and all advisors have been able to explain a new loan product clearly. This is a slightly different requirement than the known workflow, so the agent converses with the user and refines the existing workflow by:

a) Given date range, find all loan application ids from Salesforce;
b) Retrieve call recordings for these applications;
c) Transcribe the recordings into plain texts;
d) Diarize and extract only the parts said by the advisor;
e) Label the extracted transcript and export only the "product detail" and "offer explanation" segments;
f) Run compliance analysis on those segments and report the result as pass or fail.

This becomes another workflow JSON file the Planner agent saves in the vector store for future reuse.

Last but not least, sometimes the Whisper based transcribing skill may fail or timeout. The worker agent may unload it and load the alternative AssemblyAI based skill for the same purpose.

The AI agents keep updating the knowledge base and identifies that the failure rate of Whisper based transcribing skill goes beyond a threshold. Hence, the next time the Planner agent applies this workflow, the validation tool would trigger a warning, and the Planner agent would update the workflow JSON file, replacing the Whisper based skill with the AssemblyAI based skill.

Please write a detailed TESTING_PLAN_B.md according to the use case scenarios described above.