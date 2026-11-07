# B 题英文论文整合稿

[阅读 PDF](manuscript.pdf) · [编辑 LaTeX](manuscript.tex) · [修订说明与人工依赖](../report/paper-revision.md)

本稿以原九页初稿为基础，纳入截至 ee3a661 的 B01–B03、D02–D03 和 Z04–Z08 证据。主答案仍为题面假想射门在 100 ms 的两帧条件预测；新章节解释观测误差、影响因素、等预算比较及等待代价。论文不宣称现场验证已通过或保证获奖。

在仓库根目录生成新增图表，再编译：

```sh
python paper/build_assets.py
cd paper
tectonic manuscript.tex
```

图表生成需要 NumPy、Matplotlib；已生成的四个表和两幅新增矢量图均随仓库交付，直接编译无需 Python。asset-sources.json 保存输入数据 SHA-256。原两幅图由 paper/figures/draw.py 从冻结门面及见证轨迹数据生成。

关键结果复核：

```sh
python report/recheck.py
python report/recheck_field.py
python report/recheck_extensions.py
python design/start.py
```

[论证提纲](outline.md) · [独立审阅记录](review.md) · [最终导出检查](submission-checklist.md) · [原始实验报告](../report/README.md)

公开稿保留队号占位和 AI 披露缺口。提交前由队伍填实际 \TeamNumber，把经过覆盖核对的真实原始提问和完整输出放入 ai-verbatim.tex，重新编译、检查匿名性和每页队号，以实际队号加 B 命名。该私有附录和 private/ 中的部分交互记录不上传。只写使用概述不满足完整披露要求。
