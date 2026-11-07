#!/usr/bin/env python3
"""Build a reproducible, explicitly allowlisted skill archive (stdlib only)."""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)\)")


def load_payload(root):
    root = Path(root).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("VERSION must contain a numeric major.minor.patch version")
    names = [line.strip() for line in (root / "release-files.txt").read_text(
        encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate release file")
    required = {"SKILL.md", "README.md", "LICENSE", "NOTICE.md", "VERSION"}
    if not required.issubset(names):
        raise ValueError("Missing required release documents")
    payload = {}
    for name in sorted(names):
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name
                or path.as_posix() != name or any(p.startswith(".") for p in path.parts)):
            raise ValueError(f"Unsafe release path: {name}")
        candidate = root
        for part in path.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError(f"Symlink is not a portable release file: {name}")
        if not candidate.is_file():
            raise ValueError(f"Missing release file: {name}")
        if candidate.stat().st_size > 512_000:
            raise ValueError(f"Review unexpectedly large release file: {name}")
        content = candidate.read_bytes()
        content.decode("utf-8")
        payload[name] = content

    # A local Markdown link must also resolve in the extracted package.
    for name, content in payload.items():
        if not name.endswith(".md"):
            continue
        for link in LINK.findall(content.decode("utf-8")):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
                continue
            target = link.split("#", 1)[0]
            if not target:
                continue
            resolved = (root / name).parent.joinpath(target).resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                raise ValueError(f"Link leaves release root: {name}: {link}") from None
            if relative not in payload:
                raise ValueError(f"Link target is not packaged: {name}: {link}")
    return version, payload


def make_archive(payload):
    stream = io.BytesIO()
    # Stored entries avoid compression-version differences between hosts.
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo("upc-physics/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload[name])
    return stream.getvalue()


def build(root, output):
    version, payload = load_payload(root)
    bundle = make_archive(payload)
    stem = "upc-physics-v" + version
    artifacts = {stem + ".zip": bundle, stem + ".skill": bundle}
    manifest = {
        "name": "upc-physics", "version": version, "license": "MIT",
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()},
        "artifacts": {name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()},
    }
    artifacts["manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    checksums = "".join(hashlib.sha256(artifacts[name]).hexdigest() + "  " + name + "\n"
                        for name in sorted(artifacts))
    artifacts["SHA256SUMS"] = checksums.encode("utf-8")
    output = Path(output)
    # Do not leave a partially rewritten release when one destination already differs.
    if output.is_symlink():
        raise ValueError("Release output directory must not be a symlink")
    for name, content in artifacts.items():
        destination = output / name
        if destination.is_symlink() or (destination.exists() and (
                not destination.is_file() or destination.read_bytes() != content)):
            raise ValueError(f"Output exists with different contents: {name}; use a fresh --output directory")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        (output / name).write_bytes(content)
    return {"version": version, "files": len(payload),
            "archive_sha256": hashlib.sha256(bundle).hexdigest(), "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"Release build failed: {exc}", file=sys.stderr)
        sys.exit(1)
