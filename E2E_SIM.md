# Agent workflow schema review

Hello! I'd like to collaborate with you on an idea I had recently in the area of Agentic AI.

I think AI agents are smart autonomous entities that can understand human intents and help achieve their goals by solving fairly complex problems end-to-end.
From this point of view, what an AI agent does is essentially problem-solving and automated execution of tasks step-by-step, until a goal has been reached.
For an AI agent to be effective, it shall come up with a "workflow" (or SOP), which the agent may constantly improve during a conversation with a human user
while establishing an increasingly correct and accurate understanding of the human's intention. Once the workflow looks perfect, the AI agent will start to
fulfil the steps, either by itself, or by the team work of multiple fellow AI agents, each specialized in one problem domain, and equipped with appropriate
skills and tools.

What I'm trying to achieve is a way for the AI agent to document such workflows in terms of json files. The benefit is that in this way the AI agent is
"learning" and "remembering" the best practices that it has discovered in the past. Next time it encounters a similar challenge, previously established
workflows can be reused as building blocks, e.g. slightly adapted to achieve a similar goal, expanded or joined together to achieve a larger or more complex
goal, or improved/upgraded to achieve the same goal with a better solution. Ideally, a formal schema shall be defined for this purpose, so that AI agents can
document and reused such workflows in a compatible way, i.e. the workflows become transferable skills, what one agent documented can be understood and adopted
by another agent.





Brief intro to Letta

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