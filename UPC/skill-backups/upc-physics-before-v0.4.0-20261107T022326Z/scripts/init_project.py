#!/usr/bin/env python3
"""Create a non-overwriting UPC study or a four-stage team workspace (standard library only)."""

import argparse
import csv
import io
import json
from pathlib import Path
import sys
import tempfile

from _project_schema import TABLES, table_path
from handoff import DOCUMENTS, MATERIAL_FIELDS


SKILL = Path(__file__).resolve().parents[1]


def csv_bytes(fields, rows=()):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def team_files(source, problem_bytes):
    templates = SKILL / "assets/team"
    files = {"README.md": (templates / "README.md").read_bytes(),
             "experiment/README.md": (templates / "experiment/README.md").read_bytes(),
             ".gitignore": (templates / "gitignore").read_bytes(),
             ".gitattributes": (templates / "gitattributes").read_bytes(),
             "tools/LICENSE": (SKILL / "LICENSE").read_bytes()}
    for script in ("audit_project.py", "_project_schema.py", "handoff.py"):
        files[f"tools/{script}"] = (SKILL / "scripts" / script).read_bytes()
    for kind, documents in DOCUMENTS.items():
        for document in documents:
            name = f"{kind}/{document}"
            files[name] = (templates / name).read_bytes()
        files[f"{kind}/materials.csv"] = csv_bytes(MATERIAL_FIELDS)
    problem = "design/problem.md"
    if source:
        attachment = "materials/statement" + (source.suffix.lower() or ".txt")
        problem = f"design/{attachment}"
        files[problem] = problem_bytes
        files["design/problem.md"] += f"\n随附题面文件：[原始题面]({attachment})。\n".encode("utf-8")
        files["design/materials.csv"] = csv_bytes(MATERIAL_FIELDS, [
            {"path": attachment, "role": "source", "description": "团队提供的题面原件"}])
    for folder in ("experiment/src", "experiment/data/raw", "experiment/runs", "experiment/results"):
        files[f"{folder}/.gitkeep"] = b""
    return files, problem


def solo_files(source, problem_bytes):
    problem = "problem" + (source.suffix.lower() or ".txt") if source else "problem.md"
    files = {problem: problem_bytes if source else b"# Problem\n\nPending: provide the complete problem statement.\n"}
    if problem != "problem.md":
        files["problem.md"] = f"# Problem source\n\nSee [{problem}]({problem}).\n".encode("utf-8")
    files["research-state.md"] = (
        "# Research state\n\nStage: problem interpretation.\n\nEstablished results: none.\n\n"
        "Open questions: extract requirements and identify missing evidence.\n\n"
        "Next action: read the full problem and choose the first testable model.\n"
    ).encode("utf-8")
    return files, problem


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--problem", type=Path)
    parser.add_argument("--team", action="store_true", help="create design, experiment, report and paper work areas")
    args = parser.parse_args()
    root = args.project.expanduser().absolute()
    if root.exists() or root.is_symlink():
        parser.error("Target already exists; adapt its files instead of overwriting it.")
    if not args.title.strip():
        parser.error("Title must not be empty.")
    source = args.problem.expanduser().resolve() if args.problem else None
    if source and not source.is_file():
        parser.error("Problem source is not a file.")
    problem_bytes = source.read_bytes() if source else None
    if args.team:
        files, problem = team_files(source, problem_bytes)
    else:
        files, problem = solo_files(source, problem_bytes)
    version = 2 if args.team else 1
    files["project.json"] = (json.dumps({
        "format_version": version, "title": args.title.strip(),
        "stage": "analyze", "paper_path": "paper/manuscript.md",
    }, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    files["paper/outline.md"] = (SKILL / "assets/paper-outline.md").read_bytes()
    for name, fields in TABLES.items():
        rows = []
        if name == "sources" and source:
            rows.append({"id": "S0", "kind": "problem", "locator": problem, "status": "verified"})
        files[table_path(name, version)] = csv_bytes(fields, rows)

    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".upc-init-", dir=root.parent) as staging:
        draft = Path(staging) / "project"
        draft.mkdir()
        if not args.team:
            for folder in ("src", "data/raw", "data/derived", "figures"):
                (draft / folder).mkdir(parents=True)
        for name, content in files.items():
            target = draft / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if root.exists() or root.is_symlink():
            parser.error("Target already exists; a concurrent initialization may have completed.")
        draft.rename(root)
    print(json.dumps({"created": str(root), "problem": problem, "ready": False}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
