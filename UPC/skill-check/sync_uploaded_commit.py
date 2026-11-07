"""Align an unchanged local tree with its verified GitHub API commit."""
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import zlib

root = Path(r"C:\Users\zhy\Desktop\UPC\UPC-skills")
commit = json.loads(Path(__file__).with_name("uploaded-commit.json").read_text(encoding="utf-8-sig"))
branch = "codex/upc-physics-v0.4.0"


def git(*args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


assert git("branch", "--show-current") == branch
git("diff", "--quiet")
git("diff", "--cached", "--quiet")
assert git("rev-parse", "HEAD^{tree}") == commit["tree"]["sha"]
old = git("rev-parse", "HEAD")
author_epoch = int(datetime.fromisoformat(commit["author"]["date"].replace("Z", "+00:00")).timestamp())
committer_epoch = int(datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00")).timestamp())
offsets = ["+0000", "+0800"] + [f"{s}{h:02}{m:02}" for s in ("+", "-") for h in range(15) for m in (0, 15, 30, 45)]
verified = None
for a, c in itertools.product(offsets, repeat=2):
    head = "tree " + commit["tree"]["sha"] + "\n"
    head += "".join("parent " + p["sha"] + "\n" for p in commit["parents"])
    head += f"author {commit['author']['name']} <{commit['author']['email']}> {author_epoch} {a}\n"
    head += f"committer {commit['committer']['name']} <{commit['committer']['email']}> {committer_epoch} {c}\n\n"
    for ending in ("\n", "", "\n\n"):
        body = (head + commit["message"] + ending).encode()
        obj = b"commit " + str(len(body)).encode() + b"\0" + body
        if hashlib.sha1(obj).hexdigest() == commit["sha"]:
            verified = obj
            break
    if verified is not None:
        break
assert verified is not None, "Exact commit bytes could not be verified"
destination = root / ".git/objects" / commit["sha"][:2] / commit["sha"][2:]
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_bytes(zlib.compress(verified))
if old != commit["sha"]:
    git("update-ref", "refs/archive/local-before-upload/" + old, old)
    git("update-ref", "refs/heads/" + branch, commit["sha"], old)
git("update-ref", "refs/remotes/origin/" + branch, commit["sha"])
git("branch", "--set-upstream-to", "origin/" + branch, branch)
print(json.dumps({"branch": branch, "sha": git("rev-parse", "HEAD"), "status": git("status", "--short")}, ensure_ascii=False))
