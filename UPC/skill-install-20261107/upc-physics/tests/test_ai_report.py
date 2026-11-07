"""Synthetic interaction fixtures; verify exact preservation and failure behavior."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_report", ROOT / "scripts/ai_report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class DisclosureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.records = self.root / "records"
        self.prompt = self.root / "prompt.txt"
        self.response = self.root / "response.txt"
        self.prompt.write_bytes("合成测试输入\r\nKeep exact spacing.  \r\n".encode())
        self.response.write_bytes(b"Synthetic output\r\n```python\nprint(1)\n```\n````\n")

    def add(self):
        return report.add(self.records, "Synthetic system", "Unit test fixture",
                          self.prompt, self.response)

    def test_exact_round_trip_and_nested_markdown_fences(self):
        self.add()
        record = report.load_records(self.records)[0]
        self.assertEqual(record["prompt"].encode(), self.prompt.read_bytes())
        self.assertEqual(record["response"].encode(), self.response.read_bytes())
        output = self.root / "report.md"
        result = report.render(self.records, output)
        text = output.read_bytes().decode()
        self.assertIn(record["prompt"], text)
        self.assertIn(record["response"], text)
        self.assertIn("`````text", text)
        self.assertFalse(result["coverage_verified"])

    def test_tampering_is_detected(self):
        path = self.add()
        record = json.loads(path.read_text(encoding="utf-8"))
        record["response"] += " changed"
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Changed response"):
            report.render(self.records, self.root / "out.md")
        self.assertFalse((self.root / "out.md").exists())

    def test_empty_input_or_record_set_cannot_look_complete(self):
        self.records.mkdir()
        with self.assertRaisesRegex(ValueError, "No interaction"):
            report.render(self.records, self.root / "out.md")
        self.response.write_text(" ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nonempty"):
            self.add()
        self.assertEqual(list(self.records.iterdir()), [])

    def test_reports_are_not_overwritten_and_inputs_are_not_replaced(self):
        self.add()
        output = self.root / "report.md"
        report.render(self.records, output)
        original = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            report.render(self.records, output)
        self.assertEqual(output.read_bytes(), original)

    def test_multiple_records_are_retained(self):
        first = self.add()
        second = self.add()
        self.assertNotEqual(first, second)
        self.assertEqual(len(report.load_records(self.records)), 2)


if __name__ == "__main__":
    unittest.main()
