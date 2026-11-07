# UPC 2026 B · 两帧预测点球

本分支 `research/2026-b` 接续论文修订稿 `bfd0c04`。当前研究为[稳定旋转球独立复验设计](design/stable-spin.md)，[完整实验报告](report/stable-spin.md)。[阅读论文](paper/manuscript.pdf) · [三维模型图](paper/figures/problem-geometry.pdf) · [研究方案](design/README.md) · [固定截止时间验证](report/coverage-and-crossing.md)

```sh
git clone --branch research/2026-b https://github.com/Emxy-Yang-2236/UPC_2026.git
cd UPC_2026
```

从已有副本接手时先查看 `git status -sb`，工作区干净后 `git fetch origin`、`git switch research/2026-b`、`git pull --ff-only`，并核对交接提交号。设计负责人维护 `design/` 下唯一的当前方案；实验负责人将运行和证据表存入 `experiment/`。实验结论冻结后在 `report/` 形成独立写作交接包，论文放在 `paper/`。

写作交接使用 [UPC skill 0.4.0 分支版本](https://github.com/Emxy-Yang-2236/UPC-skills/tree/08f45a8bb6a7b55e58395c2d2d67274faae7c522)。[比赛规则与写作入口](contest-rules.md) · [首次独立积分结果](experiment/runs/B01/README.md)

B01–B03 的[官方样例和合成盲测](experiment/results/README.md)，以及 D01–D03 的[三脚实测与辅助数据检验](report/field.md) 已完成。[整体实验报告](report/README.md)可单独交给写作者，末章列有[后续迭代方向和待解决问题](report/next-steps.md)。

队员可直接[阅读英文论文初稿](paper/manuscript.pdf)或[编辑与编译 TeX](paper/README.md)。审阅后对齐的报告提交为 `10bb233a0e907b7c58ecf36009263d52b49c2847`。
