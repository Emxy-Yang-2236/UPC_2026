#!/usr/bin/env python3
"""Check a standalone UPC handoff folder, optionally export the listed files as a ZIP."""

import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
import unicodedata
from urllib.parse import unquote, urlsplit
import zipfile


DOCUMENTS = {
    "design": ("README.md", "problem.md", "model.md", "protocol.md"),
    "report": ("README.md", "methods.md", "results.md", "reproduction.md", "references.md"),
}
STATUS = {"design": "可执行", "report": "可写作"}
MATERIAL_FIELDS = ("path", "role", "description")
MARKER = "〔待填〕"
LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))", re.MULTILINE)


def package_file(root, name):
    """Accept only regular files reachable by the same relative name on both platforms."""
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or path.as_posix() != name
            or any(c in name for c in '\\:*?"<>|') or any(ord(c) < 32 for c in name)
            or any(p.startswith(".") or p.endswith((".", " ")) or PureWindowsPath(p).is_reserved()
                   for p in path.parts)):
        raise ValueError(f"不安全或不可移植的包内路径：{name!r}")
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"交接包应包含文件本体，请替换符号链接：{name}")
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise ValueError(f"缺失或空文件：{name}")
    return candidate


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_text(digests):
    return "".join(f"{digests[name]}  {name}\n" for name in sorted(digests))


def check_links(name, content, files, errors):
    for pattern in (LINK, REFERENCE):
        for match in pattern.finditer(content):
            target = match.group(1) or match.group(2)
            url = urlsplit(target)
            if url.scheme.lower() in {"http", "https", "doi", "mailto"}:
                continue
            path = unquote(url.path)
            if not path and not url.netloc and not url.scheme:
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
            if url.netloc or url.scheme or resolved not in files:
                errors.append(f"{name} 链接未随包交付或指向包外：{target}")


def inspect_folder(kind, root):
    files, errors, pending, roles = {}, [], [], set()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"交接目录缺失或为符号链接：{root.name}")
    inventory = "materials.csv"
    entries = list(DOCUMENTS[kind]) + [inventory]
    index = package_file(root, inventory)
    with index.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if tuple(reader.fieldnames or ()) != MATERIAL_FIELDS:
            raise ValueError(f"{inventory} 表头应为 {','.join(MATERIAL_FIELDS)}")
        for row in reader:
            if None in row or any(not (row[col] or "").strip() for col in MATERIAL_FIELDS):
                errors.append(f"{inventory} 第 {reader.line_num} 行缺少路径、类型或用途")
                continue
            entries.append(row["path"].strip())
            roles.add(row["role"].strip())
    seen = {"sha256sums"}
    for name in entries:
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            errors.append(f"重复或保留的包内路径：{name}")
            continue
        seen.add(key)
        try:
            files[name] = package_file(root, name)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    if kind == "report":
        for choices in ({"code", "method"}, {"result", "table"}, {"validation"}):
            if roles.isdisjoint(choices):
                pending.append(f"整体实验报告缺少附件类型：{' / '.join(sorted(choices))}")
    for name, path in files.items():
        if path.suffix.lower() != ".md":
            continue
        content = path.read_text(encoding="utf-8-sig")
        if MARKER in content:
            pending.append(f"{name} 仍有模板待填项")
        if name == "README.md":
            states = re.findall(r"^交接状态[：:]\s*(\S+)\s*$", content, re.MULTILINE)
            if states != [STATUS[kind]]:
                pending.append(f"接手检验后在 README.md 单独一行填写 交接状态：{STATUS[kind]}")
        check_links(name, content, files, errors)
    receipt = root / "SHA256SUMS"
    if receipt.exists() or receipt.is_symlink():
        supplied = package_file(root, "SHA256SUMS").read_text(encoding="utf-8")
        expected = checksum_text({name: digest_file(path) for name, path in files.items()})
        if supplied != expected:
            errors.append("SHA256SUMS 与本包的文件清单或内容不一致")
    return files, errors, pending


def check_folder(kind, root):
    try:
        return inspect_folder(kind, root)
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        return {}, [str(exc)], []


def zip_info(name):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def export_zip(root, files, destination):
    destination = destination.absolute()
    if root in destination.resolve().parents or root == destination.resolve():
        raise ValueError("导出位置应在交接目录外")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        try:
            with zipfile.ZipFile(output, "w") as archive:
                digests = {}
                for name, path in sorted(files.items()):
                    digest = hashlib.sha256()
                    with path.open("rb") as source, archive.open(zip_info(name), "w", force_zip64=True) as target:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
                            digest.update(chunk)
                    digests[name] = digest.hexdigest()
                archive.writestr(zip_info("SHA256SUMS"), checksum_text(digests).encode("utf-8"))
        except BaseException:
            output.close()
            destination.unlink()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=DOCUMENTS)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--zip", type=Path, help="write a new ZIP outside the source folder")
    args = parser.parse_args()
    count = 0
    try:
        root = args.folder.expanduser().absolute()
        files, integrity, pending = check_folder(args.kind, root)
        errors = integrity + pending
        count = len(files)
        if args.zip and not errors:
            export_zip(root.resolve(), files, args.zip)
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        errors = [str(exc)]
    print(json.dumps({"package_ok": not errors, "files": count, "errors": errors}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
