import asyncio
import csv
import io
import json
from pathlib import Path

from backlog_mcp import backlog
from backlog_mcp.backlog import Process

SAMPLE = Process.model_validate_json((Path(__file__).parent.parent / "samples" / "card_dispute.json").read_text())


def test_one_story_per_step_grouped_by_stage_epic():
    stories = backlog.generate_stories(SAMPLE)
    assert len(stories) == sum(len(s.steps) for s in SAMPLE.stages) == 7
    assert stories[0]["epic"] == "EPIC-1: Intake"
    assert stories[0]["story"].startswith("As a Customer, I want to capture dispute details")


def test_automated_step_story_is_written_for_the_owner():
    ack = next(s for s in backlog.generate_stories(SAMPLE) if s["step"] == "Send acknowledgement")
    assert ack["story"].startswith("As Head of Card Operations, I want the system to")


def test_rules_and_slas_become_acceptance_criteria():
    credit = next(s for s in backlog.generate_stories(SAMPLE) if s["step"] == "Decide on provisional credit")
    text = " ".join(credit["acceptance_criteria"])
    assert "EUR 2,500" in text and "10 business days" in text and "send back" in text


def test_gaps_find_the_planted_problems():
    issues = {(g["where"], g["issue"]) for g in backlog.find_gaps(SAMPLE)}
    assert ("Resolution / Submit chargeback", "Integration step without a named system") in issues
    assert ("Intake / Classify fraud or dispute", "No actor for a step a person must do") in issues
    assert ("Resolution", "Stage has no goal") in issues


def test_negative_integration_and_sla_tests_are_generated():
    tests = backlog.generate_test_cases(backlog.generate_stories(SAMPLE))
    types = {t["type"] for t in tests}
    assert {"positive", "negative", "integration-failure", "sla"} <= types


def test_csv_is_importable():
    rows = list(csv.DictReader(io.StringIO(backlog.to_csv(backlog.generate_stories(SAMPLE)))))
    assert len(rows) == 7 and rows[0]["Issue Type"] == "Story" and rows[0]["Epic Link"].startswith("EPIC-1")


def test_mcp_server_exposes_tools_resource_and_prompt():
    from backlog_mcp.server import server

    async def inspect():
        tools = {t.name for t in await server.list_tools()}
        resources = [str(r.uri) for r in await server.list_resources()]
        prompts = [p.name for p in await server.list_prompts()]
        return tools, resources, prompts

    tools, resources, prompts = asyncio.run(inspect())
    assert {"find_process_gaps", "generate_user_stories", "generate_test_cases",
            "export_backlog_csv", "backlog_summary"} <= tools
    assert "process://samples/card-dispute" in resources
    assert "describe_process" in prompts


def test_mcp_tool_call_round_trip():
    from backlog_mcp.server import server

    payload = json.loads((Path(__file__).parent.parent / "samples" / "card_dispute.json").read_text())
    result = asyncio.run(server.call_tool("backlog_summary", {"process": payload}))
    assert "Card Dispute Handling" in str(result)
