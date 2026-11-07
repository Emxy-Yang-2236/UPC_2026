"""Check public package boundaries and the installed, extracted tool chain."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_builder", ROOT / "tools/build_release.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="UPC 发布 ")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def copy_payload(self):
        target = self.folder / "source"
        target.mkdir()
        _, payload = builder.load_payload(ROOT)
        for name, content in payload.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        shutil.copyfile(ROOT / "release-files.txt", target / "release-files.txt")
        return target

    def test_archive_is_reproducible_and_contains_only_allowlisted_files(self):
        source = self.copy_payload()
        (source / "private").mkdir()
        (source / "private/unpublished.txt").write_text("Synthetic private file")
        first = builder.build(source, self.folder / "one")
        second = builder.build(source, self.folder / "two")
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        _, payload = builder.load_payload(source)
        for file in (self.folder / "one").iterdir():
            self.assertEqual(file.read_bytes(), (self.folder / "two" / file.name).read_bytes())
        archive = next((self.folder / "one").glob("*.zip"))
        self.assertEqual(archive.read_bytes(), next((self.folder / "one").glob("*.skill")).read_bytes())
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {"upc-physics/" + n for n in payload})
            for name, content in payload.items():
                self.assertEqual(bundle.read("upc-physics/" + name), content)
        for line in (self.folder / "one/SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, hashlib.sha256((self.folder / "one" / name).read_bytes()).hexdigest())

    def test_extracted_package_initializes_and_diagnoses_without_source_repo(self):
        builder.build(ROOT, self.folder / "package")
        with zipfile.ZipFile(next((self.folder / "package").glob("*.zip"))) as bundle:
            bundle.extractall(self.folder / "isolated")
        scripts = self.folder / "isolated/upc-physics/scripts"
        project = self.folder / "new study"
        def run(script, *args):
            return subprocess.run([sys.executable, str(scripts / script), *map(str, args)],
                                  cwd=self.folder, capture_output=True, text=True)
        initialized = run("init_project.py", project, "--title", "Synthetic portability check")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        audit = run("audit_project.py", project)
        self.assertEqual(audit.returncode, 1, audit.stderr)
        self.assertFalse(json.loads(audit.stdout)["ready"])
        diagnostic = run("numerical_checks.py", "biquad", "--a1", "-1.9", "--a2", "0.88")
        self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
        self.assertFalse(json.loads(diagnostic.stdout)["stable"])

    def test_manifest_cannot_escape_root_or_reuse_a_path(self):
        source = self.copy_payload()
        path = source / "release-files.txt"
        original = path.read_text()
        for extra in ["../outside.md", "/absolute.md", "SKILL.md"]:
            with self.subTest(extra=extra):
                path.write_text(original + extra + "\n")
                with self.assertRaises(ValueError):
                    builder.load_payload(source)

    def test_symlinked_payload_is_rejected(self):
        source = self.copy_payload()
        link = source / "README.md"
        link.unlink()
        link.symlink_to(ROOT / "README.md")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            builder.load_payload(source)

    def test_missing_packaged_link_is_rejected(self):
        source = self.copy_payload()
        readme = source / "README.md"
        readme.write_text(readme.read_text() + "\n[Missing resource](missing.md)\n")
        with self.assertRaisesRegex(ValueError, "not packaged"):
            builder.load_payload(source)

    def test_changed_release_does_not_overwrite_existing_assets(self):
        source = self.copy_payload()
        output = self.folder / "release"
        builder.build(source, output)
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        readme = source / "README.md"
        readme.write_text(readme.read_text() + "\nSynthetic content change.\n")
        with self.assertRaisesRegex(ValueError, "different contents"):
            builder.build(source, output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})


if __name__ == "__main__":
    unittest.main()
