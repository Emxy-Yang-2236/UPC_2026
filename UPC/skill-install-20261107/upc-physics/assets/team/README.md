# 参赛研究工作区

## 从这里接手

| 阶段 | 先打开 | 应当留下的成果 |
| --- | --- | --- |
| 审题、查资料、定方案 | [方案设计报告](design/README.md) | 可执行的模型、参数、工况和首项实验验收标准 |
| 开始或继续实验 | [实验工作区](experiment/README.md) | 运行入口、实际输入输出、失败记录和验证 |
| 实验结束、准备写作 | [整体实验报告](report/README.md) | 独立可读的结论、可复现材料、可用于论文的图表和来源 |
| 撰写与交稿 | `paper/outline.md` | 在 `paper/` 保存可编辑正文、排版资源和最终导出稿 |

第一步是确定题目，将可共享的题面与要求写入 `design/problem.md`。当前负责人及下一位接手人待团队指定。交接时把这一段改成当前任务、负责人、下一步及对应报告入口。切换阶段时同步更新 `project.json` 的 `stage`。精确的工作版本由 Git 提交标识。

## 换电脑或换负责人

1. 首次在新电脑克隆团队提供的研究仓库。在已有副本运行 `git remote get-url origin`、`git status -sb`、`git fetch origin`，确认仓库、目标分支和本地修改。切到约定分支，在工作区干净时用 `git pull --ff-only` 对齐，核对 `git rev-parse HEAD` 与发件人给的提交号。
2. 方案确认、首个基线完成、一批实验结束或中断、验证改变结论、总报告冻结、论文形成可审阅稿时，保存当时的材料和下一步。检查变更并只提交这一步的文件，向约定的远端分支推送。用 `git ls-remote origin refs/heads/main` 核对远端提交号，使用其他分支时替换 `main`。离线时先本地提交，标注“待同步”，推送完成后再通知对方接手。
3. 两人并行时各自用任务分支。发现分叉先保留各自提交，协调合并、重新核对结果。交接消息只需“仓库、分支、完整提交号、报告入口、下一步”。公开仓库仅同步可公开的文件，受限输入在报告中给出版本、校验值和合法获取方式。
4. 在新 Codex 会话中，实验负责人从 `design/README.md` 开始，写作者从 `report/README.md` 开始。两份报告分别配有验收步骤。工作所用计算平台为 MATLAB 与科学 Python。记录实际用到的版本和设置。

两个报告各有一张 `materials.csv`，用 `path,role,description` 登记固定章节以外的附件。所有路径相对本报告目录。总报告须附实际代码或操作规程（`code` 或 `method`）、数值/推导结果（`result` 或 `table`）和验证证据（`validation`）；主图另列为 `figure`。在 Windows 上可用 `py -3` 代替 `python3`。

`tools/handoff.py` 可直接在克隆后的仓库检查或打包交接目录；`tools/audit_project.py .` 检查整项研究的证据关系。两者都用 Python 标准库。

例如从仓库根目录执行 `python3 tools/handoff.py design design` 或 `python3 tools/handoff.py report report --zip exports/report.zip`。空模板会列出待补项。原始工具和模板来自 UPC Physics，许可声明保存在 `tools/LICENSE`。
