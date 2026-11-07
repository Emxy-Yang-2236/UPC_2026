# UPC 2026 B · 两帧预测点球

本分支 `research/2026-b` 接续论文修订稿 `bfd0c04`。论文第 6.6 节与附录 H 检验稳定旋转球的早期预测，将两帧测量误差、升力先验与区域校准分别对照。[阅读论文](paper/manuscript.pdf) · [补充实验设计](design/stable-spin.md) · [完整实验报告](report/stable-spin.md) · [三维模型图](paper/figures/problem-geometry.pdf)

```sh
git clone --branch research/2026-b https://github.com/Emxy-Yang-2236/UPC_2026.git
cd UPC_2026
```

从已有副本接手时先查看 `git status -sb`，工作区干净后 `git fetch origin`、`git switch research/2026-b`、`git pull --ff-only`，并核对交接提交号。设计负责人维护 `design/` 下唯一的当前方案；实验负责人将运行和证据表存入 `experiment/`。实验结论冻结后在 `report/` 形成独立写作交接包，论文放在 `paper/`。

写作交接使用 [UPC skill 0.4.0 分支版本](https://github.com/Emxy-Yang-2236/UPC-skills/tree/08f45a8bb6a7b55e58395c2d2d67274faae7c522)。[比赛规则与写作入口](contest-rules.md) · [首次独立积分结果](experiment/runs/B01/README.md)

B01–B03 的[官方样例和合成盲测](experiment/results/README.md)，以及 D01–D03 的[三脚实测与辅助数据检验](report/field.md) 已完成。[整体实验报告](report/README.md)可单独交给写作者，末章列有[后续迭代方向和待解决问题](report/next-steps.md)。

稳定旋转球的完整实验、冻结预测和交叉阈值结果已归档于 `bff1160`。队员可从图表追溯到逐脚预测，也可从设计和报告包接手复现。[研究总方案](design/README.md) · [编译论文](paper/README.md) · [复现说明](report/reproduction.md)
