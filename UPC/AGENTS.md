# UPC research workspace

User-authorized synchronization targets `Emxy-Yang-2236/UPC_2026`, branch `zhaohaoyang`, repository directory `UPC/`. The checkout `UPC_2026/` transports the workspace and is excluded from its own snapshot.

At the start of research work, check the remote branch and local changes, then inspect `experiment/`, `report/` and every non-template `next-step.md`. Read applicable task files before executing them. If a named task file is absent, record the missing input and request its location rather than inventing its instructions.

Use `experiment/src/` for active code, `experiment/results/` for computed outputs and `experiment/data/raw/` for real measurements with provenance. Mark simulations and hypothetical parameter scenarios explicitly. Use `report/` for research reports. Historical `problem_b_guidance/` files are retained as source material; maintain active successors in the designated directories.

After each meaningful authorized update, update relevant reports and the scan status, prepare the snapshot with `python sync_workspace.py`, review its manifest and diff, and commit/sync it to the authorized branch. Check the current remote head before publishing and preserve remote additions and local edits. Use the connected GitHub tools when native Git authentication is unavailable. Confirm the remote commit and uploaded file hashes before reporting synchronization complete. This is a per-task workflow, not a continuously running file watcher.

See `SYNC.md` for scope and recovery details. Keep `_sync/`, Git internals, caches and secrets outside the uploaded snapshot.

当前活动研究位于本地 UPC_2026/experiment、UPC_2026/report、UPC_2026/paper。研究仓库根目录的实验与报告为准，UPC/ 快照中的旧资料作为历史背景。实际待办文件为 UPC_2026/report/next-steps.md。
