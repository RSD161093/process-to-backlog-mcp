"""MCP server that exposes the backlog tools to any MCP client
(Claude Desktop, Claude Code, an OpenAI Agents SDK agent, a LangGraph agent...).

    python -m backlog_mcp.server          # stdio transport
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import backlog
from .backlog import Process

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

server = MCPServer(
    "process-to-backlog",
    instructions=(
        "Tools that turn a structured business process (stages -> steps) into a delivery backlog. "
        "Call find_process_gaps first and ask the user about high-severity gaps before generating stories."
    ),
)


@server.tool(description="List what is missing from a process definition (owner, actors, rules, SLAs, systems).")
def find_process_gaps(process: Process) -> list[dict[str, str]]:
    return backlog.find_gaps(process)


@server.tool(description="Generate user stories (one per step) with acceptance criteria and story points.")
def generate_user_stories(process: Process) -> list[dict[str, Any]]:
    return backlog.generate_stories(process)


@server.tool(description="Generate Given/When/Then test cases, including negative, integration-failure and SLA cases.")
def generate_test_cases(process: Process) -> list[dict[str, str]]:
    return backlog.generate_test_cases(backlog.generate_stories(process))


@server.tool(description="Export the user stories as CSV for Jira or Azure DevOps import.")
def export_backlog_csv(process: Process) -> str:
    return backlog.to_csv(backlog.generate_stories(process))


@server.tool(description="One-line overview: stages, stories, story points, test cases and gaps by severity.")
def backlog_summary(process: Process) -> dict[str, Any]:
    return backlog.summary(process)


@server.resource("process://samples/card-dispute", mime_type="application/json",
                 description="Sample process: card dispute handling (fictional bank).")
def sample_card_dispute() -> str:
    return (SAMPLES / "card_dispute.json").read_text()


@server.prompt(description="Ask the model to describe a process in the JSON shape the tools expect.")
def describe_process(process_name: str) -> str:
    schema = json.dumps(Process.model_json_schema(), indent=2)
    return (f"Describe the '{process_name}' process as JSON matching this schema. "
            f"Use one stage per major phase, one step per piece of work, and name the actor, "
            f"systems, rules and target time for each step. Leave a field empty rather than guessing.\n\n{schema}")


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
