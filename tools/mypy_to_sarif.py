#!/usr/bin/env python3
"""Convert mypy text output to SARIF format for GitHub Checks API."""

import json
import re
import subprocess
import sys
from pathlib import Path


def run_mypy() -> str:
    """Run mypy and return text output."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "."],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def parse_mypy_output(output: str) -> list[dict]:
    """Parse mypy text output into error dicts."""
    errors = []
    # Pattern: file.py:line:column: error: message [code]
    pattern = re.compile(
        r"^([^:]+):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[([^\]]+)\])?$",
        re.MULTILINE,
    )
    for match in pattern.finditer(output):
        file_path, line, col, level, message, code = match.groups()
        errors.append(
            {
                "file": file_path,
                "line": int(line),
                "column": int(col),
                "level": level,
                "code": code or "misc",
                "message": message.strip(),
            }
        )
    return errors


def create_sarif(errors: list[dict]) -> dict:
    """Create a SARIF document from parsed mypy errors."""
    if not errors:
        # Return minimal SARIF with no results
        return {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "mypy", "version": "2.3.0"}},
                    "results": [],
                }
            ],
        }

    results = []
    for err in errors:
        level = "error" if err["level"] == "error" else "warning"
        results.append(
            {
                "level": level,
                "message": {"text": f"[{err['code']}] {err['message']}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": err["file"],
                            },
                            "region": {
                                "startLine": err["line"],
                                "startColumn": err["column"],
                            },
                        },
                    },
                ],
                "ruleId": err["code"],
            }
        )

    rules = list({err["code"]: err["code"] for err in errors}.values())

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "mypy", "version": "2.3.0"}},
                "results": results,
            }
        ],
    }


def main() -> None:
    output = run_mypy()
    errors = parse_mypy_output(output)
    sarif = create_sarif(errors)
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".mypy.sarif.json")
    output_path.write_text(json.dumps(sarif, indent=2), encoding="utf-8")
    print(f"Generated SARIF report: {output_path}")
    if errors:
        print(f"Found {len(errors)} issue(s)")
        sys.exit(1)
    else:
        print("No issues found")


if __name__ == "__main__":
    main()
