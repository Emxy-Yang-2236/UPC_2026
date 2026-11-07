"""Back up the installed UPC skill, then synchronize this authorized local revision."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

source = Path(r"C:\Users\zhy\Desktop\UPC\UPC-skills").resolve()
installed = Path(r"C:\Users\zhy\.codex\skills\upc-physics").resolve()
backup_root = Path(r"C:\Users\zhy\Desktop\UPC\skill-backups").resolve()
assert (source / "VERSION").read_text(encoding="utf-8").strip() == "0.4.0"
assert (source / "SKILL.md").is_file() and (installed / "SKILL.md").is_file()
assert installed.name == "upc-physics" and installed.parent == Path(r"C:\Users\zhy\.codex\skills").resolve()
backup = backup_root / ("upc-physics-before-v0.4.0-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
assert backup.parent == backup_root and not backup.exists()
backup_root.mkdir(parents=True, exist_ok=True)
shutil.copytree(installed, backup, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
files = []
for path in source.rglob("*"):
    relative = path.relative_to(source)
    if any(part in {"dist", "__pycache__", ".git"} for part in relative.parts):
        continue
    if path.is_symlink():
        raise ValueError("Unexpected source symlink: " + str(relative))
    if path.is_file():
        files.append((path, relative))
for path, relative in files:
    destination = installed / relative
    if destination.is_symlink():
        raise ValueError("Unexpected installed symlink: " + str(relative))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
for path, relative in files:
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256((installed / relative).read_bytes()).digest(), relative
result = {"installed": str(installed), "backup": str(backup), "verified_files": len(files), "version": "0.4.0"}
Path(__file__).with_name("installed-version.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
