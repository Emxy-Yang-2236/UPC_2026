#!/usr/bin/env python3
"""Check research artifact links and completeness; never certify scientific truth."""

import argparse
import csv
import json
import math
from pathlib import Path
import sys

from _project_schema import TABLES, split_items, table_path
from handoff import DOCUMENTS, check_folder


LIMITATION = "Structural audit only: independently check physics, citations, manuscript content and contest rules."


def reject_json_constant(value):
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def audit(project):
    errors, warnings = [], []
    status_findings = []
    tables = {}

    def status_issue(message, table, ident, status):
        # Keep strict readiness and its existing errors/exit code unchanged.
        # Separately identify evidence states, so preserved failed attempts are
        # not confused with missing files or broken metadata.
        errors.append(message)
        status_findings.append({"table": table, "id": ident, "status": status, "message": message})

    try:
        root = Path(project).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("project must be an existing directory")
    except (OSError, ValueError, RuntimeError) as exc:
        failure = f"project: {exc}"
        return {"ready": False, "integrity_ok": False, "integrity_errors": [failure],
                "status_findings": [], "errors": [failure],
                "warnings": [LIMITATION], "counts": {name: 0 for name in TABLES}}

    def local_file(value, where):
        if not value.strip():
            errors.append(f"{where}: missing file path")
            return
        try:
            candidate = Path(value.split("#", 1)[0])
            resolved = (root / candidate).resolve()
            if candidate.is_absolute() or root not in resolved.parents:
                errors.append(f"{where}: path must stay inside project: {value}")
            elif not resolved.is_file() or resolved.stat().st_size == 0:
                errors.append(f"{where}: missing or empty artifact: {value}")
            else:
                return resolved
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{where}: cannot resolve/read artifact {value!r}: {exc}")

    def files(value, where, required=True):
        entries = split_items(value)
        if required and not entries:
            errors.append(f"{where}: no artifact paths")
        for entry in entries:
            local_file(entry, where)

    def allowed(row, field, choices, where):
        if not isinstance(row.get(field), str) or row.get(field) not in choices:
            errors.append(f"{where}: invalid {field}={row.get(field)!r}; expected {sorted(choices)}")

    def refs(value, known, where, required=True):
        ids = split_items(value)
        if required and not ids:
            errors.append(f"{where}: missing reference IDs")
        for item in ids:
            if item not in known:
                errors.append(f"{where}: unknown ID {item}")
        return ids

    version = 1
    config_path = local_file("project.json", "project.json")
    if config_path is not None:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"),
                                parse_constant=reject_json_constant, object_pairs_hook=unique_json_object)
            if not isinstance(config, dict):
                raise ValueError("must be a JSON object")
            candidate_version = config.get("format_version")
            if type(candidate_version) is int and candidate_version in (1, 2):
                version = candidate_version
            else:
                errors.append("project.json: format_version must be the integer 1 or 2")
            if not isinstance(config.get("title"), str) or not config["title"].strip():
                errors.append("project.json: missing title")
            allowed(config, "stage", {"analyze", "research", "model", "compute", "validate", "write", "deliver"}, "project.json")
            paper = config.get("paper_path", "")
            if isinstance(paper, str):
                local_file(paper, "project.json paper_path")
            else:
                errors.append("project.json: paper_path must be a string")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"project.json: {exc}")

    for name, fields in TABLES.items():
        rows = []
        try:
            relative = table_path(name, version)
            table_file = local_file(relative, relative)
            if table_file is not None:
                with table_file.open(encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle, strict=True)
                    if reader.fieldnames is None or set(reader.fieldnames) != set(fields) or len(reader.fieldnames) != len(fields):
                        errors.append(f"{name}.csv: expected columns {list(fields)}")
                    else:
                        for number, raw in enumerate(reader, 2):
                            if None in raw or any(value is None for value in raw.values()):
                                errors.append(f"{name}.csv:{number}: malformed CSV row")
                                continue
                            row = {key: value.strip() for key, value in raw.items()}
                            if not any(row.values()):
                                continue
                            rows.append(row)
        except (OSError, UnicodeError, csv.Error) as exc:
            errors.append(f"{name}.csv: {exc}")
        tables[name] = rows
        if name in {"requirements", "sources", "claims", "validation"} and not rows:
            errors.append(f"{name}.csv: at least one record required for delivery")
        key = "symbol" if name == "parameters" else "id"
        seen = set()
        for index, row in enumerate(rows, 2):
            ident = row[key]
            if not ident or ident in seen or ";" in ident:
                errors.append(f"{name}.csv:{index}: missing, duplicate, or invalid {key}: {ident!r}")
            seen.add(ident)

    indexed = {name: {row["id"]: row for row in rows} for name, rows in tables.items() if name != "parameters"}
    sources = indexed["sources"]
    for row in tables["sources"]:
        where = f"source {row['id']}"
        allowed(row, "kind", {"problem", "literature", "data", "assumption", "derivation"}, where)
        allowed(row, "status", {"verified", "assumed", "pending"}, where)
        if row["kind"] == "assumption" and row["status"] != "assumed":
            errors.append(f"{where}: an assumption must be marked assumed")
        if row["status"] == "assumed" and row["kind"] != "assumption":
            errors.append(f"{where}: assumed is reserved for assumption sources")
        if not row["locator"]:
            errors.append(f"{where}: missing locator")
        elif row["kind"] != "literature":
            local_file(row["locator"], where)
    def source_refs(value, where):
        for ident in refs(value, sources, where):
            if ident in sources and sources[ident]["status"] == "pending":
                status_issue(f"{where}: source {ident} is unverified", "sources", ident, "pending")

    for row in tables["parameters"]:
        where = f"parameter {row['symbol']}"
        allowed(row, "role", {"given", "literature", "measured", "assumed", "fitted", "derived"}, where)
        for field in ("value", "unit"):
            if not row[field]:
                errors.append(f"{where}: missing {field}")
        try:
            number = float(row["value"])
        except ValueError:
            pass  # Ranges and symbolic values are valid; semantic checking is separate.
        else:
            if not math.isfinite(number):
                errors.append(f"{where}: non-finite numeric value")
        source_refs(row["source_ids"], where)

    covered, supported = set(), set()
    for row in tables["claims"]:
        where = f"claim {row['id']}"
        allowed(row, "status", {"supported", "conditional", "open"}, where)
        requirement_ids = refs(row["requirement_ids"], indexed["requirements"], where)
        if not row["statement"]:
            errors.append(f"{where}: empty statement")
        source_refs(row["source_ids"], where)
        files(row["artifact_paths"], where)
        if row["status"] == "open":
            status_issue(f"{where}: unresolved", "claims", row["id"], "open")
        elif row["status"] in {"supported", "conditional"}:
            covered.update(requirement_ids)
            supported.add(row["id"])
        if row["status"] == "conditional":
            warnings.append(f"{where}: preserve its conditions in the paper")
    for row in tables["requirements"]:
        where = f"requirement {row['id']}"
        allowed(row, "status", {"open", "answered"}, where)
        if not row["question"]:
            errors.append(f"{where}: empty question")
        if row["status"] != "answered" or row["id"] not in covered:
            status_issue(f"{where}: unanswered or has no supported/conditional claim",
                         "requirements", row["id"], row["status"])

    validated = set()
    for row in tables["validation"]:
        where = f"validation {row['id']}"
        claim_ids = refs(row["claim_ids"], indexed["claims"], where)
        allowed(row, "status", {"pass", "fail", "pending"}, where)
        for field in ("method", "criterion", "result"):
            if not row[field]:
                errors.append(f"{where}: missing {field}")
        files(row["artifact_paths"], where)
        if row["status"] != "pass":
            status_issue(f"{where}: not passed", "validation", row["id"], row["status"])
        else:
            validated.update(claim_ids)
    for ident in sorted(supported - validated):
        status_issue(f"claim {ident}: no passed validation linked", "claims", ident, "no_passed_validation")
    for row in tables["runs"]:
        where = f"run {row['id']}"
        allowed(row, "kind", {"simulation", "measurement", "analysis"}, where)
        allowed(row, "status", {"completed", "failed", "planned"}, where)
        if not row["command"]:
            errors.append(f"{where}: missing reproducible method/command")
        files(row["input_paths"], where, required=False)
        files(row["output_paths"], where)
        if row["status"] != "completed":
            status_issue(f"{where}: not completed", "runs", row["id"], row["status"])

    handoffs = {}
    if version == 2:
        for kind in DOCUMENTS:
            _, broken, pending = check_folder(kind, root / kind)
            handoffs[kind] = {"package_ok": not (broken or pending), "errors": broken + pending}
            errors.extend(f"{kind}: {message}" for message in broken)
            for message in pending:
                status_issue(f"{kind}: {message}", "handoffs", kind, "pending")
    warnings.append(LIMITATION)
    state_messages = {finding["message"] for finding in status_findings}
    integrity_errors = [error for error in errors if error not in state_messages]
    result = {"ready": not errors, "integrity_ok": not integrity_errors,
            "integrity_errors": integrity_errors, "status_findings": status_findings,
            "errors": errors, "warnings": warnings,
            "counts": {name: len(rows) for name, rows in tables.items()}}
    if version == 2:
        result["handoffs"] = handoffs
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    result = audit(args.project)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
