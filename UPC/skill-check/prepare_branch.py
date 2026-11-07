"""Recover a verified shallow Git baseline from GitHub data without touching source files."""
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import zlib

work = Path(r"C:\Users\zhy\Desktop\UPC\UPC-skills")
backup = Path(r"C:\Users\zhy\Desktop\UPC\skill-backups\upc-physics-before-v0.4.0-20261107T022326Z")
data = json.loads(Path(__file__).with_name("upstream-git-data.json").read_text(encoding="utf-8-sig"))
commit = data["commit"]
tree = data["tree"]
expected_commit = "44fe8c46cdb78f9bdb32314d6736ec48b535ae4b"
branch = "codex/upc-physics-v0.4.0"
assert commit["sha"] == expected_commit
assert tree["sha"] == commit["tree"]["sha"]
assert not (work / ".git").exists(), "Repository already initialized; inspect it instead"


def object_bytes(kind, body):
    return kind.encode() + b" " + str(len(body)).encode() + b"\0" + body


def sha(kind, body):
    return hashlib.sha1(object_bytes(kind, body)).hexdigest()


objects = {}
entries = {entry["path"]: entry for entry in tree["tree"]}
for path, entry in entries.items():
    if entry["type"] == "blob":
        content = (backup / path).read_bytes()
        assert sha("blob", content) == entry["sha"], "Baseline content mismatch: " + path
        objects[entry["sha"]] = ("blob", content)

directories = [path for path, entry in entries.items() if entry["type"] == "tree"] + [""]
for directory in sorted(directories, key=lambda p: p.count("/"), reverse=True):
    children = [(path.rsplit("/", 1)[-1], entry) for path, entry in entries.items()
                if path.rpartition("/")[0] == directory]
    children.sort(key=lambda pair: (pair[0] + ("/" if pair[1]["type"] == "tree" else "")).encode())
    body = b"".join((entry["mode"].lstrip("0") + " " + name).encode() + b"\0" + bytes.fromhex(entry["sha"])
                    for name, entry in children)
    expected = tree["sha"] if not directory else entries[directory]["sha"]
    assert sha("tree", body) == expected, "Tree reconstruction mismatch: " + directory
    objects[expected] = ("tree", body)

# GitHub normalizes dates to UTC in its JSON; recover the original timezone
# headers only if the reconstructed bytes hash to the known upstream SHA.
author_epoch = int(datetime.fromisoformat(commit["author"]["date"].replace("Z", "+00:00")).timestamp())
committer_epoch = int(datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00")).timestamp())
offsets = ["+0800", "+0000"] + [f"{sign}{hours:02}{minutes:02}" for sign in ("+", "-")
            for hours in range(15) for minutes in (0, 15, 30, 45)]
payload = None
for author_offset, committer_offset in itertools.product(offsets, repeat=2):
    head = "tree " + commit["tree"]["sha"] + "\n"
    head += "".join("parent " + p["sha"] + "\n" for p in commit["parents"])
    head += f"author {commit['author']['name']} <{commit['author']['email']}> {author_epoch} {author_offset}\n"
    head += f"committer {commit['committer']['name']} <{commit['committer']['email']}> {committer_epoch} {committer_offset}\n\n"
    for ending in ("\n", "", "\n\n"):
        candidate = (head + commit["message"] + ending).encode()
        if sha("commit", candidate) == expected_commit:
            payload = candidate
            break
    if payload is not None:
        break
assert payload is not None, "Could not reconstruct exact upstream commit; no repository created"
objects[expected_commit] = ("commit", payload)


def git(*args):
    result = subprocess.run(["git", "-C", str(work), *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


git("init", "-b", "main")
for digest, (kind, content) in objects.items():
    destination = work / ".git/objects" / digest[:2] / digest[2:]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(zlib.compress(object_bytes(kind, content)))
(work / ".git/shallow").write_text(expected_commit + "\n", encoding="ascii")
git("update-ref", "refs/heads/main", expected_commit)
git("update-ref", "refs/remotes/origin/main", expected_commit)
git("remote", "add", "origin", "https://github.com/Emxy-Yang-2236/UPC-skills.git")
git("config", "core.autocrlf", "false")
git("config", "user.name", "zhaohaoyang20070613")
git("config", "user.email", "309985152+zhaohaoyang20070613@users.noreply.github.com")
git("read-tree", expected_commit)
git("switch", "-c", branch)
changed = [item["path"] for item in data["files"] if item["changed"]]
git("add", "--", *changed)
git("diff", "--cached", "--check")
git("commit", "-m", "Complete UPC research and manuscript workflow for v0.4.0")
print(json.dumps({"branch": branch, "commit": git("rev-parse", "HEAD"),
                  "base": expected_commit, "changed_files": len(changed), "status": git("status", "--short")}, ensure_ascii=False))
