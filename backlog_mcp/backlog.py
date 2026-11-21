"""Turn a structured process definition into a delivery backlog.

Input is a process described the way a business analyst captures it in discovery
(stages -> steps, each with an actor, systems, rules and a target time). Output is:

  * gap analysis  - what is still missing before the backlog can be trusted
  * user stories  - one per step, with acceptance criteria and a size estimate
  * test cases    - Given/When/Then, including negative cases for rules and integrations
  * CSV export    - ready to import into Jira or Azure DevOps

The logic is deterministic on purpose: an LLM client (Claude Desktop, an agent)
calls these tools for the structure, then uses its own language skills to polish
wording. That keeps the backlog traceable to the process input.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from pydantic import BaseModel, Field


class Step(BaseModel):
    name: str
    actor: str = ""
    kind: str = Field("manual", description="manual | automated | approval | integration | decision")
    systems: list[str] = []
    rules: list[str] = []
    target_time: str = ""


class Stage(BaseModel):
    name: str
    goal: str = ""
    steps: list[Step]


class Process(BaseModel):
    name: str
    owner: str = ""
    objective: str = ""
    stages: list[Stage]


SYSTEM_KINDS = {"automated", "integration"}   # steps the system does without a person


# ------------------------------------------------------------------ gap analysis

def find_gaps(process: Process) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []

    def add(where: str, issue: str, severity: str = "medium") -> None:
        gaps.append({"where": where, "issue": issue, "severity": severity})

    if not process.owner:
        add(process.name, "No process owner — nobody can sign off the backlog", "high")
    if not process.objective:
        add(process.name, "No objective — stories cannot state the business value")
    for stage in process.stages:
        if not stage.goal:
            add(stage.name, "Stage has no goal", "low")
        for step in stage.steps:
            where = f"{stage.name} / {step.name}"
            if not step.actor and step.kind not in SYSTEM_KINDS:
                add(where, "No actor for a step a person must do", "high")
            if step.kind == "integration" and not step.systems:
                add(where, "Integration step without a named system", "high")
            if step.kind in {"approval", "decision"} and not step.rules:
                add(where, f"{step.kind.title()} step without decision rules")
            if step.kind not in SYSTEM_KINDS and not step.target_time:
                add(where, "No target time (SLA)", "low")
    return gaps


# ------------------------------------------------------------------ stories

def _size(step: Step) -> int:
    """Simple, explainable story-point heuristic (Fibonacci)."""
    points = 1 + len(step.rules) + 2 * len(step.systems)
    points += {"integration": 2, "decision": 2, "approval": 1}.get(step.kind, 0)
    for fib in (1, 2, 3, 5, 8, 13):
        if points <= fib:
            return fib
    return 13


def _verb_phrase(name: str) -> str:
    return name[0].lower() + name[1:] if name else name


def generate_stories(process: Process) -> list[dict[str, Any]]:
    stories = []
    n = 0
    for s_idx, stage in enumerate(process.stages, start=1):
        epic = f"EPIC-{s_idx}: {stage.name}"
        for step in stage.steps:
            n += 1
            actor = step.actor or "[ACTOR TO CONFIRM]"
            value = stage.goal or process.objective or "the case moves forward"
            if step.kind in SYSTEM_KINDS:
                story = f"As {process.owner or 'the process owner'}, I want the system to {_verb_phrase(step.name)} automatically so that {value[0].lower() + value[1:]}"
            else:
                story = f"As a {actor}, I want to {_verb_phrase(step.name)} so that {value[0].lower() + value[1:]}"
            criteria = []
            for rule in step.rules:
                criteria.append(f"Rule applied: {rule}")
            for system in step.systems:
                criteria.append(f"Data is read from / written to {system}; a failed call is retried and then raised to an operator")
            if step.kind == "approval":
                criteria.append("The approver can approve, reject or send back with a mandatory comment")
            if step.target_time:
                criteria.append(f"Step is completed within {step.target_time}; otherwise it is escalated")
            criteria.append("Every action is recorded in the case audit history")
            stories.append({
                "id": f"US-{n:03d}",
                "epic": epic,
                "stage": stage.name,
                "step": step.name,
                "type": step.kind,
                "story": story,
                "acceptance_criteria": criteria,
                "story_points": _size(step),
            })
    return stories


# ------------------------------------------------------------------ tests

def generate_test_cases(stories: list[dict[str, Any]]) -> list[dict[str, str]]:
    tests = []
    for story in stories:
        base = story["id"].replace("US", "TC")
        tests.append({
            "id": f"{base}-01", "story": story["id"], "type": "positive",
            "given": f"a case is at step '{story['step']}' with valid data",
            "when": "the step is completed",
            "then": "the case moves to the next step and the action is in the audit history",
        })
        k = 2
        for criterion in story["acceptance_criteria"]:
            if criterion.startswith("Rule applied:"):
                rule = criterion.removeprefix("Rule applied: ")
                tests.append({"id": f"{base}-{k:02d}", "story": story["id"], "type": "negative",
                              "given": f"a case that breaks the rule '{rule}'",
                              "when": "the step is attempted",
                              "then": "the case is stopped or routed as the rule requires"})
                k += 1
            elif criterion.startswith("Data is read from"):
                system = re.search(r"to (.+?);", criterion).group(1)
                tests.append({"id": f"{base}-{k:02d}", "story": story["id"], "type": "integration-failure",
                              "given": f"{system} is unavailable",
                              "when": "the step calls it",
                              "then": "the call is retried, then raised to an operator without losing case data"})
                k += 1
            elif criterion.startswith("Step is completed within"):
                tests.append({"id": f"{base}-{k:02d}", "story": story["id"], "type": "sla",
                              "given": "the target time passes with the step still open",
                              "when": "the SLA check runs",
                              "then": "the case is escalated"})
                k += 1
    return tests


# ------------------------------------------------------------------ export

def to_csv(stories: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Issue Type", "Summary", "Description", "Epic Link", "Story Points"])
    for s in stories:
        description = s["story"] + "\n\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in s["acceptance_criteria"])
        writer.writerow(["Story", f"{s['id']} {s['step']}", description, s["epic"], s["story_points"]])
    return out.getvalue()


def summary(process: Process) -> dict[str, Any]:
    stories = generate_stories(process)
    tests = generate_test_cases(stories)
    gaps = find_gaps(process)
    return {
        "process": process.name,
        "stages": len(process.stages),
        "stories": len(stories),
        "story_points": sum(s["story_points"] for s in stories),
        "test_cases": len(tests),
        "gaps": {sev: sum(1 for g in gaps if g["severity"] == sev) for sev in ("high", "medium", "low")},
    }
