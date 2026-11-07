# B 题英文论文整合稿

[阅读 PDF](manuscript.pdf) · [编辑 LaTeX](manuscript.tex) · [稳定旋转球实验报告与复现](../report/stable-spin.md)

研究分支从三维修订稿 `bfd0c04` 接续。图 1 用题给三维坐标和已归档的样例 A 表示观测、未观测球路、门线交点与离脚受力。[独立矢量图](figures/problem-geometry.pdf) · [作图实现](flight_schematic.py)

本稿按 [历届获奖稿对照](../report/upc-award-strategy.md) 重排正文。主文集中于题面算例、物理不可辨识性和 [Z09 固定 100 ms 验证](../report/coverage-and-crossing.md)。Z10 用独立射门检验带噪稳定旋转球，并交叉使用 Z09 和 Z10 的校准阈值。附录给过线事件误差传播、完整的覆盖与面积数据、早期验证及现场采集条件。

在仓库根目录生成新增图表，再编译：

```sh
python paper/build_assets.py
python paper/build_revision_assets.py
python paper/build_visuals.py
cd paper
tectonic manuscript.tex
```

表格脚本只使用 Python 标准库。本稿用 NumPy 2.3.5 与 Matplotlib 3.10.9 重绘全部 12 幅矢量图。绘图清单记录每幅图的数值、输入路径和 SHA-256。图表和各章 TeX 随仓库交付，直接编译论文只需 TeX。[绘图数据清单](visual-data.json) · [视觉修订说明](../report/visual-revision.md)

关键结果复核：

```sh
python report/recheck.py
python report/recheck_field.py
python report/recheck_extensions.py
python report/recheck_spin.py --run report/evidence/z10-replay.zip
python design/start.py
```

[论证提纲](outline.md) · [独立审阅记录](review.md) · [最终导出检查](submission-checklist.md) · [原始实验报告](../report/README.md)

公开稿保留队号占位和 AI 披露缺口。提交前由队伍填实际 \TeamNumber，把经过覆盖核对的真实原始提问和完整输出放入 ai-verbatim.tex，重新编译、检查匿名性和每页队号，以实际队号加 B 命名。该私有附录和 private/ 中的部分交互记录不上传。只写使用概述不满足完整披露要求。
