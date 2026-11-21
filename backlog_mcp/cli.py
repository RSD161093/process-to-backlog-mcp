"""Try the tools without an MCP client.

    python -m backlog_mcp.cli samples/card_dispute.json
    python -m backlog_mcp.cli samples/card_dispute.json --csv backlog.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import backlog
from .backlog import Process


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("process_file")
    parser.add_argument("--csv", help="write the Jira CSV to this file")
    args = parser.parse_args()

    process = Process.model_validate_json(Path(args.process_file).read_text())
    print(json.dumps(backlog.summary(process), indent=2))

    print("\nGAPS")
    for gap in backlog.find_gaps(process):
        print(f"  [{gap['severity']:<6}] {gap['where']}: {gap['issue']}")

    stories = backlog.generate_stories(process)
    print("\nSTORIES")
    for s in stories:
        print(f"  {s['id']} ({s['story_points']} pts) {s['story']}")
        for c in s["acceptance_criteria"]:
            print(f"      - {c}")

    print("\nTEST CASES (first 6)")
    for t in backlog.generate_test_cases(stories)[:6]:
        print(f"  {t['id']} [{t['type']}] Given {t['given']}, when {t['when']}, then {t['then']}")

    if args.csv:
        Path(args.csv).write_text(backlog.to_csv(stories))
        print(f"\nCSV written to {args.csv}")


if __name__ == "__main__":
    main()
