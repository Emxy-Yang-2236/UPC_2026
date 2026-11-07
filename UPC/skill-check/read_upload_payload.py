"""Read committed text for the authorized GitHub branch upload."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(r"C:\Users\zhy\Desktop\UPC\UPC-skills")


def git(*args):
    return subprocess.check_output(["git", "-C", str(root), *args])


files = git("diff", "--name-only", "origin/main...HEAD").decode().splitlines()
if len(sys.argv) == 1:
    print(json.dumps({"local_commit": git("rev-parse", "HEAD").decode().strip(),
                      "local_tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
                      "parent": git("rev-parse", "HEAD^").decode().strip(), "files": files}))
else:
    name = files[int(sys.argv[1])]
    mode = git("ls-tree", "HEAD", "--", name).decode().split()[0]
    print(json.dumps({"path": name, "mode": mode, "type": "blob",
                      "content": git("show", "HEAD:" + name).decode("utf-8")}, ensure_ascii=False))
