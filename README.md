# UPC 2026 B · 两帧预测点球

本分支是 B 题队友共用的研究工作区。[当前方案](design/README.md) · [实验记录](experiment/README.md)

```sh
git clone --branch research/2026-b https://github.com/Emxy-Yang-2236/UPC_2026.git
cd UPC_2026
python3 design/start.py
```

从已有副本接手时先查看 `git status -sb`，工作区干净后 `git fetch origin`、`git switch research/2026-b`、`git pull --ff-only`，并核对交接提交号。设计负责人维护 `design/` 下唯一的当前方案；实验负责人将运行和证据表存入 `experiment/`。实验结论冻结后在 `report/` 形成独立写作交接包，论文放在 `paper/`。

写作交接使用 [UPC skill 0.4.0 分支版本](https://github.com/Emxy-Yang-2236/UPC-skills/tree/08f45a8bb6a7b55e58395c2d2d67274faae7c522)。[比赛规则与写作入口](contest-rules.md) · [首次独立积分结果](experiment/runs/B01/README.md)

B01–B03 已完成。[盲测与官方样例结果](experiment/results/README.md)。[只需此目录即可复核与接手写作](report/README.md)。另已筛出 [3 个真实点球的逐帧轨迹和门线坐标](experiment/data/raw/idsse-penalties/README.md)，可从杜塞尔多夫对雷根斯堡的案例接续。
