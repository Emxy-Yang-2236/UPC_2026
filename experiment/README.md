# B 题实验工作区

从[当前方案](../design/README.md)接手。首个结果是 [B01 有效力轨迹对及 MATLAB 复核](runs/B01/README.md)。整批试验按 V1 数值门槛、V2 开发、V3 区域校准、V4 合成盲测、V5 官方样例的顺序运行。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r experiment/requirements.txt
.venv/bin/python experiment/src/run_pipeline.py --out experiment/runs/B02-replay --workers 3
```

在 Windows 以 `.venv\Scripts\python.exe` 替换解释器路径。在仓库根执行，输出目录选全新 ID；所需软件为科学 Python，另用基础 MATLAB 实施 B01。每脚独立，默认 3 个 CPU 进程、每进程 1 个 BLAS 线程，使用 float64；改变工作进程数不改变各脚抽样种子。各运行实际版本见 `start.json` 或 B01 的两个 JSON。

- `src/` 包含批量前向动力学、独立自适应真值、条件抽样、校准评分及官方应用。`records/` 下六张表给出来源、要求、参数、主张、验证和运行对应关系。
- `runs/<ID>/` 保存按脚分开的输入与参考真值、评分前锁定并计算 SHA-256 的预测、盲测逐脚分数、官方格网与积分轨迹、运行环境和输出校验值。门内格编号为 `10 × y索引 + z索引`，从零开始。时间单位 s，长度 m。
- 在完整目录中看到 `complete.json` 表示该批正常结束。`failure.json` 记录异常，中断时原目录保留并换新 ID 重跑。真实点球的纳入状态独立于合成评分。
