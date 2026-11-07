# UPC 2026 B · 规则与写作交接

核实日期 2026-11-07。题号 B，队号由队伍在私有定稿时填入。官方起赛为 11 月 6 日 18:00 MST（UTC−7），比赛时长 48 h，收件截止换算为 **11 月 9 日 09:00 北京时间（UTC+8）**。[当届安排与 B 题](https://uphysicsc.com/2026contest.html) · [正式规则第 5、6 节](https://www.uphysicsc.com/contestrules.html)

英文、全文匿名、每页顶部列队号；首页仅含队号、题号、标题和至多 300 词的摘要。正文从次页开始，解释假设、算法、方法、结果与局限。论文写作使用生成式 AI 时，在文末按规则列实际系统、原提问及完整可见输出。最终文件作为附件送达，队号出现在文件名（加 B）、邮件主题及正文。队员在赛内自行处理正式提交。[官方规则](https://university-physics-competition.com/contest-rules)

**0.4.0 接手步骤。** 本研究的设计、求解器、验证、交接包和六张证据表沿用已冻结版本。实验完成后，先从 `report/` 交出可独立写作的结果；撰写时使用 `paper/template.tex`，用 `paper/review.md` 记独立审阅，用 `paper/submission-checklist.md` 核对实际导出。研究完成、审阅、版式、披露覆盖各自标注。

当前处于实验阶段，尚无本轮参赛正文和提交文件。正式引入既有 AI 输出或开始辅助写作时，用宿主真实导出补齐所用交互；历史写作用途与完整性待队员按实际使用范围核对。原始导出放在各机受控的 `private/`，公开远端仅登记覆盖状态。可用 `python3 tools/ai_report.py add --help` 及 `render --help` 了解录入和生成方法。
