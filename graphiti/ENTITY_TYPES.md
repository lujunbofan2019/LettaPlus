# Entity types in the Graphiti MCP server

This repository uses the upstream Graphiti MCP server as the runtime, which ships with a set of built-in entity types. These built-ins live in [`graphiti/src/models/entity_types.py`](src/models/entity_types.py) and are always loaded by default.

Custom entity types are **not** implemented as static Python classes. Instead, any items listed under `graphiti.entity_types` in a configuration file (for example [`config/config-docker-falkordb.yaml`](config/config-docker-falkordb.yaml)) are converted at startup into lightweight Pydantic models whose name and description come directly from the YAML entry. This conversion happens in [`GraphitiService.initialize`](src/graphiti_mcp_server.py) and only adds a docstring; there are no predefined fields beyond what the built-ins already provide.

Because of that, a custom entity type is just an additional category name with guidance text. If you need structured fields for a new type, you would add a concrete Pydantic model to `graphiti/src/models/entity_types.py` and include it in `ENTITY_TYPES` instead of (or in addition to) the dynamic YAML entry.

The server also skips any custom entities whose names overlap the built-in set to avoid redundancy. You can see the final entity set and any skipped duplicates in the server logs when it starts.
