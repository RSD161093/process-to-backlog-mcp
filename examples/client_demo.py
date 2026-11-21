"""Connect to the server over stdio like Claude Desktop would, list tools and call one.

    python examples/client_demo.py
"""
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = str(Path(__file__).resolve().parent.parent)


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "backlog_mcp.server"], cwd=ROOT)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            proc = json.loads((Path(ROOT) / "samples" / "card_dispute.json").read_text())
            res = await s.call_tool("backlog_summary", {"process": proc})
            print(res.content[0].text[:300])
asyncio.run(main())
