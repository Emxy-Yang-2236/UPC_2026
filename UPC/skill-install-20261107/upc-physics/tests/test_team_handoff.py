"""Exercise the two transfers in isolated folders and the versioned research layout."""

import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from _platform_support import make_symlink
import zipfile

from test_project_tools import ProjectToolTestCase, audit_module


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run_script(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(script), *map(str, args)],
                          cwd=cwd, capture_output=True, text=True)


class TeamLayoutTests(ProjectToolTestCase):
    def test_team_audit_reads_nested_records_and_preserves_strict_status(self):
        self.complete_fixture()
        records = self.project / "experiment/records"
        records.mkdir(parents=True)
        for table in self.project.glob("*.csv"):
            table.rename(records / table.name)
        config = self.project / "project.json"
        config.write_text(json.dumps(dict(json.loads(config.read_text()), format_version=2)))
        first = audit_module.audit(self.project)
        self.assertEqual(first["counts"]["runs"], 1)
        self.assertFalse(first["ready"])
        self.assertFalse(first["handoffs"]["report"]["package_ok"])
        self.assertTrue(all(e.startswith(("design: ", "report: ")) for e in first["errors"]))
        (records / "runs.csv").rename(self.project / "runs.csv")
        self.assert_not_ready("experiment/records/runs.csv")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="UPC 交接 ")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.project = self.base / "研究工作区"
        original = self.base / "original.txt"
        original.write_text("Synthetic test. Find distance after 3 s at constant speed 2 m/s.")
        run = run_script(SCRIPTS / "init_project.py", self.project, "--team",
                         "--problem", original, "--title", "Synthetic portability fixture")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.tool = self.project / "tools/handoff.py"

    def check(self, kind, *options):
        return run_script(self.tool, kind, self.project / kind, *options)

    def set_docs(self, kind, pages):
        for name, content in pages.items():
            (self.project / kind / name).write_text(content + "\n", encoding="utf-8")

    def add_material(self, kind, name, role, purpose, contents):
        folder = self.project / kind
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        with (folder / "materials.csv").open("a", encoding="utf-8", newline="") as index:
            csv.writer(index).writerow([name, role, purpose])

    def fill_design(self):
        self.set_docs("design", {
            "README.md": "# Handoff\n交接状态：可执行\n[Task](problem.md) [Model](model.md) [Run](protocol.md)",
            "problem.md": "[Statement](materials/statement.txt). R1 asks for distance at 3 s.",
            "model.md": "At constant v=2 m/s, x(0)=0 m and x(t)=vt. Assume straight motion.",
            "protocol.md": "From this folder execute: python motion.py\nInput columns [v_m_s,t_s](in.csv). "
                           "First case 2,3. Expect 6 m in out.txt; absolute tolerance 0.001 m.",
        })
        self.add_material("design", "in.csv", "input", "First test case", "v_m_s,t_s\n2,3\n")
        self.add_material("design", "motion.py", "code", "First experiment",
                          "import csv\nfrom pathlib import Path\n"
                          "with open('in.csv') as f:\n    row = next(csv.DictReader(f))\n"
                          "Path('out.txt').write_text(str(float(row['v_m_s']) * float(row['t_s'])))\n")

    def test_empty_scaffold_cannot_be_delivered_as_either_handoff(self):
        for kind in ("design", "report"):
            result = self.check(kind, "--zip", self.base / "draft.zip")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads(result.stdout)["package_ok"])
            self.assertFalse((self.base / "draft.zip").exists())
        audit = run_script(self.project / "tools/audit_project.py", self.project)
        self.assertEqual(audit.returncode, 1)
        self.assertEqual(json.loads(audit.stdout)["counts"]["sources"], 1)
        self.assertEqual((self.project / "design/materials/statement.txt").read_bytes(),
                         (self.base / "original.txt").read_bytes())
        before = (self.project / "README.md").read_bytes()
        retry = run_script(SCRIPTS / "init_project.py", self.project, "--team", "--title", "Retry")
        self.assertNotEqual(retry.returncode, 0)
        self.assertEqual(before, (self.project / "README.md").read_bytes())

    def test_extracted_design_runs_and_report_alone_reproduces_result(self):
        self.fill_design()
        design_zip = self.base / "design.zip"
        result = self.check("design", "--zip", design_zip)
        self.assertEqual(result.returncode, 0, result.stdout)
        labor = self.base / "second computer"
        with zipfile.ZipFile(design_zip) as archive:
            archive.extractall(labor)
        self.assertEqual(run_script(SCRIPTS / "handoff.py", "design", labor).returncode, 0)
        executed = run_script(labor / "motion.py", cwd=labor)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        actual = float((labor / "out.txt").read_text())
        self.assertAlmostEqual(actual, 6, delta=0.001)
        self.set_docs("report", {
            "README.md": "# Constant motion\n交接状态：可写作\nR1: Distance at 3 s. "
                         "[Method](methods.md), [answer](results.md), [repeat](reproduction.md), [source](references.md).",
            "methods.md": "Straight path at v=2 m/s from x(0)=0 m; integrate dx/dt=v from 0 to 3 s.",
            "results.md": "R1 / C1: 6.0 m at 3 s for constant 2 m/s. E1: [accepted value](ref.txt). "
                          "V1: [independent check](validation.txt). Measurement uncertainty is outside this exact model.",
            "reproduction.md": "From this folder run python motion.py using [input](in.csv); compare out.txt "
                               "to ref.txt, absolute tolerance 0.001 m.",
            "references.md": "The supplied problem fixes the velocity and time; the model uses the definition of velocity.",
        })
        for name, role, contents in [
            ("motion.py", "code", (labor / "motion.py").read_text()),
            ("in.csv", "input", (labor / "in.csv").read_text()),
            ("ref.txt", "result", str(actual)),
            ("validation.txt", "validation", "Rectangle area under v(t)=2 m/s for 3 s gives 6 m; E1 residual 0 m."),
        ]:
            self.add_material("report", name, role, name, contents)
        (self.project / "report/unlisted.txt").write_text("Must not travel")
        output = self.base / "report.zip"
        result = self.check("report", "--zip", output)
        self.assertEqual(result.returncode, 0, result.stdout)
        shutil.rmtree(self.project)
        shutil.rmtree(labor)
        isolated = self.base / "writer"
        with zipfile.ZipFile(output) as archive:
            self.assertNotIn("unlisted.txt", archive.namelist())
            archive.extractall(isolated)
        self.assertEqual(run_script(SCRIPTS / "handoff.py", "report", isolated).returncode, 0)
        self.assertEqual(run_script(isolated / "motion.py", cwd=isolated).returncode, 0)
        self.assertAlmostEqual(float((isolated / "out.txt").read_text()),
                               float((isolated / "ref.txt").read_text()), delta=0.001)
        (isolated / "ref.txt").write_text("500")
        altered = run_script(SCRIPTS / "handoff.py", "report", isolated)
        self.assertEqual(altered.returncode, 1)
        self.assertIn("SHA256SUMS", altered.stdout)

    def test_link_to_old_working_tree_or_unlisted_attachment_is_rejected(self):
        self.fill_design()
        for link in ("../experiment/README.md", "unlisted.txt", "file:///old/machine/model.py"):
            with self.subTest(link=link):
                self.set_docs("design", {"model.md": f"Read [the source]({link})"})
                result = self.check("design")
                self.assertEqual(result.returncode, 1)
                self.assertIn(link, result.stdout)

    def test_symlinked_material_directory_and_traversal_fail(self):
        self.fill_design()
        folder = self.project / "design"
        make_symlink(self, folder / "external", self.base, target_is_directory=True)
        with (folder / "materials.csv").open("a", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["external/original.txt", "input", "External directory"])
            writer.writerow(["../../original.txt", "input", "Traversal"])
        result = self.check("design")
        self.assertEqual(result.returncode, 1)
        self.assertIn("external/original.txt", result.stdout)
        self.assertIn("../../original.txt", result.stdout)

    def test_completed_report_requires_real_reproduction_result_and_validation_files(self):
        for path in (self.project / "report").glob("*.md"):
            path.write_text("交接状态：可写作\nCompleted narrative.\n", encoding="utf-8")
        result = self.check("report")
        self.assertEqual(result.returncode, 1)
        self.assertIn("validation", result.stdout)
        self.assertIn("result", result.stdout)
        self.assertIn("method", result.stdout)

    def test_export_never_overwrites_an_existing_zip_or_leaves_it_inside_handoff(self):
        self.fill_design()
        target = self.base / "existing.zip"
        target.write_bytes(b"existing archive")
        result = self.check("design", "--zip", target)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(target.read_bytes(), b"existing archive")
        inside = self.project / "design/drafts/archive.zip"
        self.assertEqual(self.check("design", "--zip", inside).returncode, 1)
        self.assertFalse(inside.exists())


if __name__ == "__main__":
    unittest.main()
