import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client

class MCP_SSE_Client:
    """MCP client connecting over SSE to list tools."""

    def __init__(self, sse_url: str):
        self.sse_url = sse_url
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.streams_ctx = None

    async def connect(self):
        # Open SSE transport
        self.streams_ctx = sse_client(self.sse_url)
        streams = await self.exit_stack.enter_async_context(self.streams_ctx)

        # Create session using the streams
        self.session = await self.exit_stack.enter_async_context(ClientSession(*streams))
        await self.session.initialize()
        print("✅ Connected and initialized via SSE.")

    async def list_tools(self):
        assert self.session is not None, "Not connected!"
        resp = await self.session.list_tools()
        for tool in resp.tools:
            print(f"- {tool.name}: {tool.description}")
            print(f"    Input schema: {tool.inputSchema}")
            if hasattr(tool, "outputSchema"):
                print(f"    Output schema: {tool.outputSchema}")

    async def close(self):
        await self.exit_stack.aclose()
        print("🔌 Connection closed.")

async def main():
    client = MCP_SSE_Client("http://localhost:8000/sse")
    try:
        await client.connect()
        print("\n🛠️ Available tools:")
        await client.list_tools()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
