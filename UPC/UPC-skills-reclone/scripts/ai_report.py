#!/usr/bin/env python3
"""Preserve supplied AI interactions and render a verbatim disclosure (stdlib)."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_exact(path):
    text = Path(path).read_bytes().decode("utf-8")
    if not text.strip():
        raise ValueError("Prompt and response must contain actual, nonempty text")
    return text


def add(records, system, purpose, prompt_file, response_file):
    if not system.strip() or not purpose.strip():
        raise ValueError("Actual system and purpose are required")
    prompt, response = read_exact(prompt_file), read_exact(response_file)
    record = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "system": system.strip(), "purpose": purpose.strip(),
        "prompt": prompt, "response": response,
        "sha256": {"prompt": digest(prompt), "response": digest(response)},
    }
    records = Path(records)
    records.mkdir(parents=True, exist_ok=True)
    destination = records / (uuid.uuid4().hex + ".json")
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return destination


def load_records(records):
    folder = Path(records)
    if not folder.is_dir():
        raise ValueError("Records directory does not exist")
    loaded = []
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("schema_version") != 1:
            raise ValueError(f"Unsupported record: {path.name}")
        for field in ("system", "purpose", "recorded_at", "prompt", "response"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"Invalid {field}: {path.name}")
        if not isinstance(record.get("sha256"), dict):
            raise ValueError(f"Missing integrity values: {path.name}")
        for field in ("prompt", "response"):
            if record["sha256"].get(field) != digest(record[field]):
                raise ValueError(f"Changed {field} content: {path.name}")
        loaded.append((record["recorded_at"], path.name, record))
    if not loaded:
        raise ValueError("No interaction records; cannot generate a disclosure")
    return [record for _, _, record in sorted(loaded)]


def fenced(text):
    # A response containing Markdown fences must remain inside its own block.
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return fence + "text\n" + text + ("" if text.endswith("\n") else "\n") + fence


def render(records, output):
    entries = load_records(records)
    parts = ["# Report on the Use of AI", "",
             "The following supplied records are reproduced in full. Record coverage "
             "must be checked against actual use; this file does not certify completeness.", ""]
    for index, record in enumerate(entries, 1):
        parts.extend([f"## Interaction {index}", "", "System:", fenced(record["system"]),
                      "", "Purpose:", fenced(record["purpose"]), "",
                      "Recorded at: " + record["recorded_at"], "",
                      "### Exact input", "", fenced(record["prompt"]), "",
                      "### Complete supplied output", "", fenced(record["response"]), ""])
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Report output already exists; use a new versioned path")
    if output.suffix.lower() != ".md":
        raise ValueError("Report output must be a Markdown .md file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(parts))
    return {"records": len(entries), "output": str(output), "coverage_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    collect = commands.add_parser("add", help="Store one actual supplied interaction")
    collect.add_argument("--records", required=True, type=Path)
    collect.add_argument("--system", required=True)
    collect.add_argument("--purpose", required=True)
    collect.add_argument("--prompt-file", required=True, type=Path)
    collect.add_argument("--response-file", required=True, type=Path)
    export = commands.add_parser("render", help="Render supplied records, without a coverage claim")
    export.add_argument("--records", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "add":
        result = {"record": str(add(args.records, args.system, args.purpose,
                                    args.prompt_file, args.response_file))}
    else:
        result = render(args.records, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"AI disclosure error: {exc}", file=sys.stderr)
        sys.exit(1)
