# 从交接目录独立复现

在本目录运行 `python3 -I recheck.py`，Windows 可用 `py -3 -I recheck.py`。只用标准库。它从两个 CSV 独立复算面积、名义格、误差、Brier、原始/校准命中与轨迹对界限。预期 `status=pass`、门内命中 30/33 和 29/33，样例面积 0.357216 m²。点及面积核验容差为 10⁻¹⁰（SI）。[复核脚本](recheck.py)

## 离线还原上游代码并运行

源码 bundle 含指定提交及先祖、题目设置、三个模型、数据生成器和相应的作者证据。解包后，代码本身无需网络；若本机尚无数值依赖，可从队伍环境或按 requirements 安装。B03 环境为 Python 3.13.9、NumPy 2.5.4、SciPy 1.18.1、Matplotlib 3.11.2，CPU float64。独立 MATLAB 检验为 R2026b，仅用基础 ode45。先创建全新输出目录名。

```sh
git clone --branch replay evidence/b03-source.bundle replay-work
cd replay-work
git rev-parse HEAD
python3 -m pip install -r experiment/requirements.txt
python3 experiment/src/run_pipeline.py --out scratch/replay --workers 3
```

HEAD 应为 `4cb0292f4e7ca656ce8ca4cfca3699ab5266b57c`。新结果在 `scratch/replay/`；比较 `official.json`、`blind_scores.csv`、`calibration.json`、全部锁定预测的哈希及数值核验。允许不同库/架构因浮点运算出现细小差距，主要指标和计数应单独比较，运行时间戳有意随运行变化。B01 的两条独立复算命令也在克隆内 `experiment/runs/B01/README.md`。重绘第一张图随管线完成；第二张图在 `replay-work` 内从本包运行以下命令。

```sh
python3 experiment/src/plot_blind.py scratch/replay/blind_scores.csv scratch/replay/blind.png
```

**冷启动记录。** 2026-11-07，本次实验端在空目录解压 ZIP 后核对完整性，仅使用报告中的命令、源包和本机既有依赖复核。13 个包内文件通过校验。标准库复算返回 30/33、29/33、0.357216 m² 和 0.04379675 m 条件下界；从离线源码重新运行时改用 2 个工作进程，三组锁定预测、逐脚盲测、校准分位数、官方概率与轨迹、两张主图与冻结结果逐字节一致。此检查在同一台机器的全新目录完成，其他操作系统未实测。
