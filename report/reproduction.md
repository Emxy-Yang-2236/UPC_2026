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

## Z08 采集条件仿真

解压 [Z08 复现包](evidence/z08-replay.zip) 后，在包根运行 `python experiment/src/capture_feedback.py --out scratch/Z08`。本轮用 Python 3.10.11 和 NumPy 2.2.6，设置 `OPENBLAS_NUM_THREADS=1`。输出包含设定、独立合成参考、可用输入、评分前锁定的预测、逐脚评分和汇总。`python -I recheck_extensions.py` 可从交接包表格重算采集分母、名义命中和平均区域。

预测器将不等间隔积分拆为不超过步长上限的子步。时钟情景使用离脚偏移的有界均匀先验，对 5 或 7 个 Gauss–Legendre 节点分配同一总提议预算，并按节点先验与读数似然合并事件分布。ESS 在归一化权重下计算，避免极小权重平方下溢。测试覆盖 5 ms 间隔的抛体解析解、迟到帧及缺帧、三帧预算、极小权重和 B03 官方复算。 [采集清单](field-acquisition.md) · [反馈表](evidence/z08-feedback.csv)

## Z09 固定 100 ms 留出与事件误差

在研究仓库根目录使用 Python 3.10.11 和 NumPy 2.2.6，指定全新输出路径。

```sh
python experiment/src/coverage_benchmark.py --out scratch/Z09-replay
python experiment/src/event_sensitivity.py --out scratch/plane-sensitivity-replay.json
```

将结果与冻结汇总、复现档案和事件诊断逐项核对。复现档案保留两个误差情景的输入与真值、全部锁定预测、校准阈值和 720 条评分。墙钟时间和含计时值的文件哈希随机器与重跑而变。取整情景两种气动力方法在匹配操作点均覆盖 70/71，带跟踪误差时重力与两帧气动力方法均覆盖 67/71。 [完整实验说明](coverage-and-crossing.md) · [复现档案](evidence/z09-replay.zip) · [事件诊断](evidence/plane-sensitivity.json)


## Z10 稳定旋转球独立留出

在报告目录运行 `python3 recheck_spin.py --run evidence/z10-replay.zip`，标准库即可重算分位秩、命中、面积及代表性曲率诊断。全部归档均可离线使用。[完整运行包](evidence/z10-replay.zip) · [实验结果与限制](stable-spin.md)

要从初始条件重新生成射门，将 Z10 运行包解到空目录，进入解压根目录，安装 `experiment/requirements.txt`，运行 `python experiment/src/stable_spin.py --out scratch/Z10-replay --workers 4`。根目录的两个分布压缩包、两次锁和逐脚表是此前运行的冻结结果。重放输出使用新的目录。浮点末位可能随 NumPy、SciPy 和硬件变化，检查校准样本数、各组命中和打印精度下的科学量，环境信息见归档内 config.json。实验使用相互独立的整脚工作进程和每程一个 BLAS 线程。

交叉阈值诊断可在同一报告目录运行 `python3 cross_spin_calibration.py`。默认读取包内 Z09 与 Z10 归档，输出四个留出批次与校准来源组合。
