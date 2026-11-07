"""Exercise project readiness, input failures and project-boundary handling.

All evidence here is synthetic test-fixture content inside TemporaryDirectory;
these tests do not create research results, AI-use records or persistent logs.

Run: python3 -m unittest discover -s tests -p test_project_tools.py -v
"""

import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    SPEC = importlib.util.spec_from_file_location("upc_audit_under_test", SCRIPTS / "audit_project.py")
    audit_module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(audit_module)
    from _project_schema import TABLES
finally:
    sys.path.pop(0)


class ProjectToolTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.project = self.directory / "study"

    def cli(self, script, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *(str(arg) for arg in args)],
            capture_output=True, text=True, check=False,
        )

    def initialize(self, *extra):
        result = self.cli("init_project.py", self.project, "--title", "Synthetic test study", *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ready"])
        return result

    def write_table(self, table, rows):
        with (self.project / (table + ".csv")).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TABLES[table])
            writer.writeheader()
            writer.writerows(rows)

    def rows(self, table):
        with (self.project / (table + ".csv")).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def set_cell(self, table, column, value, index=0):
        rows = self.rows(table)
        rows[index][column] = value
        self.write_table(table, rows)

    def complete_fixture(self):
        statement = self.directory / "provided.md"
        statement.write_text("Synthetic problem: state and verify y(0) for y(t)=exp(-t).\n", encoding="utf-8")
        self.initialize("--problem", statement)
        artifacts = {
            "data/raw/input.csv": "t\n0\n",
            "data/derived/result.csv": "t,y\n0,1\n",
            "data/derived/derivation.md": "Synthetic fixture: substituting t=0 gives exp(0)=1.\n",
            "data/derived/check.json": '{"expected":1,"actual":1,"residual":0}\n',
            "assumptions.md": "Synthetic fixture: time is measured in seconds.\n",
            "src/evaluate.py": "# Synthetic fixture method; not an executed research run.\n",
            "paper/manuscript.md": "# Synthetic fixture\n\nThe stated model gives y(0)=1 by substitution.\n",
        }
        for name, contents in artifacts.items():
            (self.project / name).write_text(contents, encoding="utf-8")
        (self.project / "project.json").write_text(json.dumps({
            "format_version": 1, "title": "Synthetic test study", "stage": "deliver",
            "paper_path": "paper/manuscript.md",
        }), encoding="utf-8")
        self.write_table("requirements", [{"id": "R1", "question": "What is y(0)?", "status": "answered"}])
        self.write_table("sources", [
            {"id": "S0", "kind": "problem", "locator": "problem.md", "status": "verified"},
            {"id": "S1", "kind": "derivation", "locator": "data/derived/derivation.md#initial-value", "status": "verified"},
            {"id": "S2", "kind": "assumption", "locator": "assumptions.md", "status": "assumed"},
        ])
        self.write_table("parameters", [{"symbol": "tau", "value": "1", "unit": "s", "role": "assumed", "source_ids": "S2"}])
        self.write_table("claims", [{
            "id": "C1", "requirement_ids": "R1", "statement": "For the given exponential model, y(0)=1.",
            "source_ids": "S0;S1", "artifact_paths": "data/derived/derivation.md;data/derived/result.csv",
            "status": "supported",
        }])
        self.write_table("validation", [{
            "id": "V1", "claim_ids": "C1", "method": "Direct substitution in the stated function",
            "criterion": "Absolute initial-value residual is zero", "result": "residual = 0",
            "artifact_paths": "data/derived/check.json", "status": "pass",
        }])
        self.write_table("runs", [{
            "id": "E1", "kind": "analysis", "command": "Synthetic fixture for method: substitute t=0",
            "input_paths": "data/raw/input.csv;data/derived/derivation.md",
            "output_paths": "data/derived/result.csv;data/derived/check.json", "status": "completed",
        }])

    def assert_not_ready(self, fragment=None):
        result = audit_module.audit(self.project)
        self.assertFalse(result["ready"], result)
        self.assertTrue(result["errors"])
        if fragment:
            self.assertTrue(any(fragment in error for error in result["errors"]), result["errors"])
        return result


class InitializationTests(ProjectToolTestCase):
    def test_empty_scaffold_is_not_ready(self):
        self.initialize()
        self.assertIn("Pending", (self.project / "problem.md").read_text())
        self.assertTrue((self.project / "paper/outline.md").is_file())
        for name in TABLES:
            self.assertEqual(self.rows(name), [])
        self.assert_not_ready("at least one record")
        result = self.cli("audit_project.py", self.project)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ready"])

    def test_problem_copy_preserves_contents_without_claiming_readiness(self):
        source = self.directory / "statement.txt"
        source.write_bytes("完整题面\nA: define the output.\n".encode())
        self.initialize("--problem", source)
        self.assertEqual((self.project / "problem.txt").read_bytes(), source.read_bytes())
        self.assertIn("problem.txt", (self.project / "problem.md").read_text())
        self.assertEqual(self.rows("sources")[0]["locator"], "problem.txt")
        self.assert_not_ready()

    def test_existing_directory_is_not_overwritten(self):
        self.project.mkdir()
        sentinel = self.project / "keep.txt"
        sentinel.write_text("User work\n")
        result = self.cli("init_project.py", self.project, "--title", "Replacement")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "User work\n")
        self.assertEqual([item.name for item in self.project.iterdir()], ["keep.txt"])

    def test_existing_file_and_dangling_symlink_are_not_replaced(self):
        self.project.write_text("Keep this file")
        result = self.cli("init_project.py", self.project, "--title", "Replacement")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.project.read_text(), "Keep this file")
        self.project.unlink()
        self.project.symlink_to(self.directory / "nonexistent")
        result = self.cli("init_project.py", self.project, "--title", "Replacement")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.project.is_symlink())
        self.assertFalse((self.directory / "nonexistent").exists())

    def test_missing_source_and_empty_title_leave_no_project(self):
        for extra in [("--problem", self.directory / "missing.md"), ()]:
            title = "Study" if extra else "  "
            result = self.cli("init_project.py", self.project, "--title", title, *extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.project.exists())

    def test_source_symlink_cycle_fails_without_traceback_or_partial_project(self):
        source = self.directory / "cycle.md"
        source.symlink_to(source.name)
        result = self.cli("init_project.py", self.project, "--title", "Study", "--problem", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.project.exists())

    def test_missing_packaged_outline_leaves_no_partial_project(self):
        isolated_scripts = self.directory / "isolated-skill/scripts"
        isolated_scripts.mkdir(parents=True)
        for name in ["init_project.py", "_project_schema.py"]:
            shutil.copyfile(SCRIPTS / name, isolated_scripts / name)
        result = subprocess.run(
            [sys.executable, str(isolated_scripts / "init_project.py"), str(self.project), "--title", "Study"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.project.exists())


class ReadinessTests(ProjectToolTestCase):
    def setUp(self):
        super().setUp()
        self.complete_fixture()

    def test_supported_fixture_is_structurally_ready(self):
        result = audit_module.audit(self.project)
        self.assertTrue(result["ready"], result["errors"])
        self.assertEqual(result["counts"]["claims"], 1)
        self.assertEqual(result["counts"]["validation"], 1)
        self.assertTrue(any("Structural audit only" in warning for warning in result["warnings"]))
        completed = self.cli("audit_project.py", self.project)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ready"])

    def test_conditional_claim_is_allowed_with_warning(self):
        self.set_cell("claims", "status", "conditional")
        result = audit_module.audit(self.project)
        self.assertTrue(result["ready"], result)
        self.assertTrue(any("conditions" in warning for warning in result["warnings"]))

    def test_analytic_project_does_not_require_invented_runs_or_parameters(self):
        self.write_table("runs", [])
        self.write_table("parameters", [])
        result = audit_module.audit(self.project)
        self.assertTrue(result["ready"], result)

    def test_unknown_ids_and_uncovered_requirements_are_rejected(self):
        for table, field in [("claims", "source_ids"), ("parameters", "source_ids"),
                             ("claims", "requirement_ids"), ("validation", "claim_ids")]:
            with self.subTest(table=table, field=field):
                original = self.rows(table)
                self.set_cell(table, field, "UNKNOWN")
                self.assert_not_ready("unknown ID UNKNOWN")
                self.write_table(table, original)
        self.write_table("requirements", self.rows("requirements") + [{"id": "R2", "question": "Another task", "status": "answered"}])
        self.assert_not_ready("requirement R2")

    def test_missing_and_empty_evidence_and_manuscript_are_rejected(self):
        for name in ["data/derived/result.csv", "data/derived/check.json", "paper/manuscript.md"]:
            with self.subTest(path=name):
                path = self.project / name
                original = path.read_bytes()
                path.unlink()
                self.assert_not_ready("missing or empty")
                path.write_bytes(b"")
                self.assert_not_ready("missing or empty")
                path.write_bytes(original)

    def test_linked_pending_source_and_mislabelled_assumption_are_rejected(self):
        self.set_cell("sources", "status", "pending", index=1)
        self.assert_not_ready("unverified")
        self.set_cell("sources", "status", "verified", index=1)
        self.set_cell("sources", "status", "verified", index=2)
        self.assert_not_ready("assumption must be marked assumed")

    def test_open_claim_failed_or_pending_validation_and_run_are_rejected(self):
        for table, status in [("claims", "open"), ("validation", "fail"), ("validation", "pending"),
                              ("runs", "failed"), ("runs", "planned")]:
            with self.subTest(table=table, status=status):
                original = self.rows(table)
                self.set_cell(table, "status", status)
                self.assert_not_ready()
                self.write_table(table, original)
        self.write_table("validation", [])
        self.assert_not_ready("no passed validation")

    def test_nonfinite_parameters_are_rejected_and_explicit_ranges_remain_allowed(self):
        for value in ["NaN", "Infinity", "-inf", "1e999"]:
            with self.subTest(value=value):
                self.set_cell("parameters", "value", value)
                self.assert_not_ready("non-finite")
        self.set_cell("parameters", "value", "1 to 2")
        result = audit_module.audit(self.project)
        self.assertTrue(result["ready"], result)

    def test_duplicate_ids_and_invalid_csv_headers_are_rejected(self):
        rows = self.rows("sources")
        self.write_table("sources", rows + [rows[0]])
        self.assert_not_ready("duplicate")
        self.write_table("sources", rows)
        path = self.project / "parameters.csv"
        path.write_text("symbol,value,unit,role,source_ids,source_ids\nx,1,1,given,S0,S0\n")
        self.assert_not_ready("expected columns")

    def test_malformed_csv_field_counts_are_rejected(self):
        for contents in ["id,question,status\nR1,What?\n", "id,question,status\nR1,What?,answered,extra\n"]:
            with self.subTest(contents=contents):
                (self.project / "requirements.csv").write_text(contents)
                self.assert_not_ready("malformed CSV")

    def test_unclosed_csv_quote_is_not_silently_repaired(self):
        path = self.project / "sources.csv"
        contents = path.read_text().rstrip("\n")
        self.assertTrue(contents.endswith(",assumed"))
        path.write_text(contents[:-len(",assumed")] + ',"assumed')
        self.assert_not_ready()

    def test_invalid_json_and_nonobject_config_are_reported(self):
        for contents in ["{broken", "[]"]:
            with self.subTest(contents=contents):
                (self.project / "project.json").write_text(contents)
                self.assert_not_ready("project.json")

    def test_bad_json_value_types_are_diagnostics_not_tracebacks(self):
        path = self.project / "project.json"
        original = json.loads(path.read_text())
        for field, value in [("stage", []), ("stage", {}), ("paper_path", []), ("title", None), ("format_version", True)]:
            with self.subTest(field=field, value=value):
                path.write_text(json.dumps(dict(original, **{field: value})))
                completed = self.cli("audit_project.py", self.project)
                self.assertEqual(completed.returncode, 1)
                self.assertNotIn("Traceback", completed.stderr)
                self.assertFalse(json.loads(completed.stdout)["ready"])

    def test_nonstandard_json_constants_and_duplicate_keys_are_rejected(self):
        path = self.project / "project.json"
        original = path.read_text()
        for addition in ['"extra": NaN', '"extra": Infinity', '"title": "duplicate"']:
            with self.subTest(addition=addition):
                path.write_text(original.rstrip()[:-1] + "," + addition + "}")
                self.assert_not_ready("project.json")


class BoundaryTests(ProjectToolTestCase):
    def setUp(self):
        super().setUp()
        self.complete_fixture()
        self.outside = self.directory / "outside.txt"
        self.outside.write_text("External content that must not satisfy local evidence requirements.\n")

    def test_relative_and_absolute_escape_in_all_artifact_fields(self):
        fields = [("sources", "locator"), ("claims", "artifact_paths"),
                  ("validation", "artifact_paths"), ("runs", "input_paths"), ("runs", "output_paths")]
        for table, field in fields:
            original = self.rows(table)
            for path in ["../outside.txt", str(self.outside)]:
                with self.subTest(table=table, field=field, path=path):
                    self.set_cell(table, field, path)
                    self.assert_not_ready("path must stay inside")
            self.write_table(table, original)
        config_path = self.project / "project.json"
        config = json.loads(config_path.read_text())
        config["paper_path"] = "../outside.txt"
        config_path.write_text(json.dumps(config))
        self.assert_not_ready("path must stay inside")

    def test_symlink_to_outside_is_rejected(self):
        link = self.project / "data/derived/external.txt"
        link.symlink_to(self.outside)
        self.set_cell("claims", "artifact_paths", "data/derived/external.txt")
        self.assert_not_ready("path must stay inside")

    def test_symlink_to_internal_artifact_is_allowed(self):
        link = self.project / "data/derived/internal.txt"
        link.symlink_to("derivation.md")
        self.set_cell("claims", "artifact_paths", "data/derived/internal.txt")
        result = audit_module.audit(self.project)
        self.assertTrue(result["ready"], result)

    def test_cyclic_and_dangling_symlinks_are_clear_diagnostics(self):
        link = self.project / "data/derived/loop.txt"
        link.symlink_to("loop.txt")
        self.set_cell("claims", "artifact_paths", "data/derived/loop.txt")
        self.assert_not_ready()
        link.unlink()
        link.symlink_to("missing.txt")
        self.assert_not_ready("missing or empty")

    def test_nul_in_a_path_does_not_crash(self):
        self.set_cell("claims", "artifact_paths", "data/derived/invalid\x00.txt")
        self.assert_not_ready()

    def test_metadata_symlinks_cannot_escape_the_project(self):
        for name in ["sources.csv", "project.json"]:
            with self.subTest(name=name):
                path = self.project / name
                original = path.read_bytes()
                outside = self.directory / ("external-" + name)
                outside.write_bytes(original)
                path.unlink()
                path.symlink_to(outside)
                self.assert_not_ready("path must stay inside")
                path.unlink()
                path.write_bytes(original)

    def test_invalid_project_roots_are_diagnostics(self):
        for root in [self.directory / "absent", self.outside]:
            with self.subTest(root=root):
                result = audit_module.audit(root)
                self.assertFalse(result["ready"])
        cycle = self.directory / "root-cycle"
        cycle.symlink_to(cycle.name)
        result = audit_module.audit(cycle)
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main()
