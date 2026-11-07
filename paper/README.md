# B 题英文论文整合稿

[阅读 PDF](manuscript.pdf) · [编辑 LaTeX](manuscript.tex) · [修订说明与人工依赖](../report/paper-revision.md)

本稿按 [历届获奖稿对照](../report/upc-award-strategy.md) 重排正文。主文集中于题面算例、物理不可辨识性和 [Z09 固定 100 ms 验证](../report/coverage-and-crossing.md)。附录给过线事件误差传播、完整的覆盖与面积数据、早期验证及现场采集条件。

在仓库根目录生成新增图表，再编译：

```sh
python paper/build_assets.py
python paper/build_revision_assets.py
cd paper
tectonic manuscript.tex
```

图表生成需要 NumPy 和 Matplotlib。已生成的图表与正文分册随仓库交付，直接编译无需 Python。旧版图表输入见 asset-sources.json，新版基准与过线扰动的输入、锁和代码哈希见复现档案。原两幅图由 paper/figures/draw.py 从冻结门面及见证轨迹数据生成。

关键结果复核：

```sh
python report/recheck.py
python report/recheck_field.py
python report/recheck_extensions.py
python design/start.py
```

[论证提纲](outline.md) · [独立审阅记录](review.md) · [最终导出检查](submission-checklist.md) · [原始实验报告](../report/README.md)

公开稿保留队号占位和 AI 披露缺口。提交前由队伍填实际 \TeamNumber，把经过覆盖核对的真实原始提问和完整输出放入 ai-verbatim.tex，重新编译、检查匿名性和每页队号，以实际队号加 B 命名。该私有附录和 private/ 中的部分交互记录不上传。只写使用概述不满足完整披露要求。
