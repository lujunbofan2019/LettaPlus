import json
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Set

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dcf_mcp.tools.dcf.load_skill import load_skill  # noqa: E402


@dataclass
class _FakeBlock:
    block_id: str
    label: str
    value: str = ""

    @property
    def id(self) -> str:  # mimic SDK which exposes ``id``
        return self.block_id


@dataclass
class _FakeTool:
    tool_id: str
    name: str

    @property
    def id(self) -> str:
        return self.tool_id


@dataclass
class _FakeToolAttachment:
    tool_id: str

    @property
    def id(self) -> str:
        return self.tool_id


@dataclass
class _FakeBlockAttachment:
    block: _FakeBlock

    @property
    def block_id(self) -> str:
        return self.block.block_id

    @property
    def id(self) -> str:
        return self.block.block_id

    @property
    def label(self) -> str:
        return self.block.label


class _FakeStream:
    def __init__(self, events: Iterable[SimpleNamespace]):
        self._events = list(events)

    def __iter__(self):
        return iter(self._events)

    def close(self):
        return None


class _FakeAgentsBlocks:
    def __init__(self, store: "_FakeState"):
        self._store = store

    def list(self, agent_id: str) -> List[_FakeBlockAttachment]:
        ids = self._store.agent_blocks.get(agent_id, [])
        return [_FakeBlockAttachment(self._store.blocks[bid]) for bid in ids]

    def attach(self, agent_id: str, block_id: str):
        self._store.agent_blocks.setdefault(agent_id, []).append(block_id)
        return nullcontext()


class _FakeAgentsTools:
    def __init__(self, store: "_FakeState"):
        self._store = store

    def list(self, agent_id: str) -> List[_FakeToolAttachment]:
        ids = sorted(self._store.agent_tools.get(agent_id, set()))
        return [_FakeToolAttachment(tool_id=i) for i in ids]

    def attach(self, agent_id: str, tool_id: str):
        self._store.agent_tools.setdefault(agent_id, set()).add(tool_id)
        return nullcontext()


class _FakeAgents:
    def __init__(self, store: "_FakeState"):
        self._store = store
        self.blocks = _FakeAgentsBlocks(store)
        self.tools = _FakeAgentsTools(store)

    def retrieve(self, agent_id: str):
        if agent_id not in self._store.agents:
            raise ValueError("missing agent")
        return SimpleNamespace(id=agent_id)


class _FakeBlocks:
    def __init__(self, store: "_FakeState"):
        self._store = store

    def create(self, label: str, value: str):
        self._store.block_counter += 1
        block_id = f"block-{self._store.block_counter}"
        block = _FakeBlock(block_id=block_id, label=label, value=value)
        self._store.blocks[block_id] = block
        return block

    def retrieve(self, block_id: str) -> _FakeBlock:
        return self._store.blocks[block_id]

    def modify(self, block_id: str, value: str):
        self._store.blocks[block_id].value = value
        return self._store.blocks[block_id]


class _FakeTools:
    def __init__(self, store: "_FakeState"):
        self._store = store

    def list_mcp_servers(self) -> Dict[str, Dict[str, str]]:
        return {name: {"endpoint": "http://stub"} for name in self._store.mcp_servers}

    def add_mcp_server(self, *, request):
        self._store.mcp_servers.add(request.server_name)
        return SimpleNamespace()

    def connect_mcp_server(self, *, request):
        discovered = self._store.server_tools.get(request.server_name, set())
        events = [SimpleNamespace(tools=SimpleNamespace(name=name)) for name in discovered]
        events.append(SimpleNamespace(event="success"))
        return _FakeStream(events)

    def list_mcp_tools_by_server(self, mcp_server_name: str):
        tools = self._store.server_tools.get(mcp_server_name, set())
        return [SimpleNamespace(name=name) for name in tools]

    def add_mcp_tool(self, mcp_server_name: str, mcp_tool_name: str, *, request_options=None):
        self._store.tool_counter += 1
        tool_id = f"tool-{self._store.tool_counter}"
        tool = _FakeTool(tool_id=tool_id, name=mcp_tool_name)
        self._store.tools[tool_id] = tool
        self._store.server_tools.setdefault(mcp_server_name, set()).add(mcp_tool_name)
        return tool


class _FakeState:
    def __init__(self, server_tools: Optional[Dict[str, Set[str]]] = None):
        self.agents: Set[str] = {"agent-123"}
        self.blocks: Dict[str, _FakeBlock] = {}
        self.tools: Dict[str, _FakeTool] = {}
        self.agent_blocks: Dict[str, List[str]] = {"agent-123": []}
        self.agent_tools: Dict[str, Set[str]] = {"agent-123": set()}
        self.mcp_servers: Set[str] = set()
        self.server_tools: Dict[str, Set[str]] = server_tools or {}
        self.block_counter = 0
        self.tool_counter = 0

        self.agents_client = _FakeAgents(self)
        self.blocks_client = _FakeBlocks(self)
        self.tools_client = _FakeTools(self)


class _FakeLetta:
    def __init__(self, *, state: _FakeState, base_url: str):
        self._state = state
        self.base_url = base_url
        self.agents = state.agents_client
        self.blocks = state.blocks_client
        self.tools = state.tools_client


@dataclass
class _StreamableHttpServerConfig:
    server_name: str
    type: str
    server_url: str
    custom_headers: Optional[Dict[str, str]] = None


@dataclass
class _StdioServerConfig:
    server_name: str
    command: str
    args: List[str]


@dataclass
class _SseServerConfig:
    server_name: str
    type: str
    server_url: str


@pytest.fixture
def fake_state():
    return _FakeState(server_tools={
        "search": {"search_query"},
        "web": {"web_fetch"},
    })


@pytest.fixture
def fake_letta(monkeypatch, fake_state):
    monkeypatch.setenv("LETTA_BASE_URL", "http://letta-test")
    monkeypatch.setenv("SKILL_REGISTRY_PATH", "skills_src/registry.json")
    monkeypatch.setenv("SKILL_STATE_BLOCK_LABEL", "dcf_active_skills")
    monkeypatch.setenv("SKILL_MAX_TEXT_CHARS", "1000")
    monkeypatch.setenv("ALLOW_MCP_SKILLS", "1")
    monkeypatch.setenv("ALLOW_PYTHON_SOURCE_SKILLS", "0")
    monkeypatch.setenv("SKILL_REGISTRY_PATH", "skills_src/registry.json")

    import letta_client

    def _letta_factory(*args, **kwargs):
        base_url = kwargs.get("base_url")
        if base_url is None and args:
            base_url = args[0]
        if base_url is None:
            raise TypeError("base_url is required")
        return _FakeLetta(state=fake_state, base_url=base_url)

    monkeypatch.setattr(letta_client, "Letta", _letta_factory, raising=False)
    monkeypatch.setattr(letta_client, "StreamableHttpServerConfig", _StreamableHttpServerConfig, raising=False)
    monkeypatch.setattr(letta_client, "StdioServerConfig", _StdioServerConfig, raising=False)
    monkeypatch.setattr(letta_client, "SseServerConfig", _SseServerConfig, raising=False)

    return fake_state


def test_load_skill_records_blocks_and_tools(tmp_path, fake_letta):
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "manifestId": "skill.research.web@0.1.0",
        "skillName": "research.web",
        "skillVersion": "0.1.0",
        "skillDirectives": "Collect relevant facts",
        "requiredTools": [
            {
                "toolName": "search_query",
                "definition": {"type": "mcp_server", "serverId": "search", "toolName": "search_query"},
            },
            {
                "toolName": "web_fetch",
                "definition": {"type": "mcp_server", "serverId": "web", "toolName": "web_fetch"},
            },
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = load_skill(str(manifest_path), agent_id="agent-123")

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert sorted(result["added"]["tool_ids"]) == ["tool-1", "tool-2"]
    # Expect both directives block and the bookkeeping state block
    assert len(result["added"]["memory_block_ids"]) == 2
    directive_block, state_block = sorted(result["added"]["memory_block_ids"])
    assert directive_block.startswith("block-")
    assert state_block.startswith("block-")

    # Ensure state block content references added ids
    state = json.loads(fake_letta.blocks[state_block].value)
    entry = state["skill.research.web@0.1.0"]
    assert set(entry["toolIds"]) == {"tool-1", "tool-2"}
    assert set(entry["memoryBlockIds"]) == set(result["added"]["memory_block_ids"])
