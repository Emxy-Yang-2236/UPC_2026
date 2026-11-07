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

**B03 历史冷启动记录（初版 13 个文件）。** 2026-11-07，实验端在空目录解压 ZIP 后核对完整性，仅使用报告中的命令、源包和本机既有依赖复核。13 个包内文件通过校验。标准库复算返回 30/33、29/33、0.357216 m² 和 0.04379675 m 条件下界；从离线源码重新运行时改用 2 个工作进程，三组锁定预测、逐脚盲测、校准分位数、官方概率与轨迹、两张主图与冻结结果逐字节一致。此检查在同一台机器的全新目录完成，其他操作系统未实测。

## 实测重放与绘图

在独立报告根目录执行 `python3 -I recheck_field.py`，标准库会从 303 个原生帧重建三个门线参照和三个加速度下界，并核对每个有点预测的欧氏误差。应得到 `compatible_two_frame_cases=0`、晚帧唯一误差 0.8486902239 m、全族加速度上界 102.6478632 m/s²。图中的歧义时刻与交点可用 `python3 plot_ambiguity.py` 从包内冻结数值重画。[实测复核入口](recheck_field.py) · [歧义图脚本](plot_ambiguity.py)

[实测运行归档](evidence/field-replay.zip) 来自提交 `6afc4b8a007c4ee65979ebb1d84e6980a398a664`。从报告根执行以下命令。D02 及其输入核验全程可离线运行；D03 如无两份对应 SHA-256 的本地缓存，最后一条命令需联网下载。原始 IDSSE 及本包相应衍生数据沿用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，来源和改动见[文献](references.md)。
```sh
python3 -m zipfile -e evidence/field-replay.zip replay-field
cd replay-field
python3 experiment/src/empirical_penalties.py --out scratch/D02
python3 experiment/src/check_empirical.py --run scratch/D02 --masking
python3 experiment/src/check_auxiliary_tracks.py --output scratch/D03.json
```

D02 的 `inputs.json`、`predictions.json`、`lock.json`、`support.csv`、`reference.csv`、`scores.csv`、`summary.json` 可与归档中的 `experiment/runs/D02/` 比较；软件版本变化时锁中的环境字段可不同。D03 应与包内 [auxiliary.json](evidence/auxiliary.json) 一致。两种实验的输入接口、时钟和目标各自定义，故保留各自的评分表。

**本次实测扩充的验收。** 2026-11-07，独立上下文只读 ZIP 解包，运行两个标准库复核，得到官方区域 0.357216 m²、合成命中 30/33、现场加速度上界 102.647863 m/s² 与唯一末帧点误差 0.848690 m。实验端另外在空目录离线重放 D02，预测与评分七个文件逐字节相同，隐藏帧扰动检验通过 3/3；D03 由公开来源重取后与包内聚合逐字节一致。随后增加末章的迭代方向，稿件审阅又补明取整与有界误差的区别、系统重采样及等预算对照。数表未变，最终 24 项均从解包目录按 SHA-256 核对。

## 补充实验 Z05–Z07

从报告目录执行 `python -I recheck_extensions.py`，可用标准库复算 Z05 基准面积、Z06 的逐脚分母和表内均值，以及 Z07 三脚的纳入状态。需从同一份源程序重新运行时，将 [补充复现包](evidence/z05-z07-replay.zip) 解到空目录。使用 Python 3.10.11、NumPy 2.2.6 可得到本轮运行，三个输出目录须为新路径。

```sh
python -m zipfile -e evidence/z05-z07-replay.zip replay-extensions
cd replay-extensions
python experiment/src/factor_sweep.py --out scratch/Z05
python experiment/src/additional_information.py --out scratch/Z06
python experiment/src/field_anchor_check.py --out scratch/Z07
```

预测阶段读取各自的可见读数，Z06 在评分前写出每批预测及 SHA-256。参考求解器用同一生成力律的 1 ms 积分，并自动与 48 脚冻结 DOP853 参考比较。新测试的种子、初始条件、真实事件、每种子校准分位数与逐脚结果均保存在运行目录。独立报告同时携带 Z05 数据表、Z06 评分与汇总、Z07 诊断表。Z07 复现包的 IDSSE 派生帧来自已注明版本的 CC BY 4.0 数据，出处见来源章节。 [补充复核脚本](recheck_extensions.py) · [来源](references.md)

本轮计算时设置 `OPENBLAS_NUM_THREADS=1`。解包后的 Z07 复放在所有 18 行的事件、标志与分母上相同，默认线程设置下 ESS 的最大差约 $1.1\times10^{-13}$。数值复核采用容差，SHA-256 用于核对冻结文件。
