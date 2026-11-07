# D03 · 连续球轨迹外推与射门终点核对

这两项辅助检验回答不同问题。ISSIA-3D 用于检查两个位置对稍后位置的预测价值。StatsBomb 用于核对有事件终点的点球能否提供门线真值。两份资料的原始视频与标注均由发布方维护，仓库交付[聚合结果和两个原始文件的 SHA-256](summary.json)。

## ISSIA-3D 的短时外推

原采集者给出六路同步相机、25 帧/秒的单场片段。Gutiérrez-Pérez 与 Agudo 根据多视角球心标注三角定位，发布以米计的坐标。校准模板以中圈为原点，x 沿边线、y 沿门线，横梁位于 z = −2.44 m。本项使用原生三维欧氏距离，对坐标平移、轴反向均不敏感。[采集说明](https://pspagnolo.jimdofree.com/download/) · [标注作者与数据格式](https://github.com/mguti97/SoccerNet-v3D/blob/4d7d7c4e350e2ea8a4885c038d793f7883883f7e/README.md#issia-3d) · [校准模板](https://github.com/SoccerNet/sn-calibration/blob/f2d878d83649fa9c2f274bb83a3ead1834c0c565/src/soccerpitch.py#L112-L138) · [研究论文](https://openaccess.thecvf.com/content/CVPR2025W/CVSPORTS/papers/Gutierrez-Perez_SoccerNet-v3D_Leveraging_Sports_Broadcast_Replays_for_3D_Scene_Understanding_CVPRW_2025_paper.pdf)

按原帧号顺序读取。每个三维点须有三个有限坐标且 `cam_list` 中至少两个不同视角。任何帧号或有效定位中断都开启新段。每个连续段仅取一次窗口，覆盖多个连续段的同一脚球仍可能相关。段首为 f，只要 f 至 f+2 连续有效，即用 f 与 f+2 的位置（相隔 80 ms）在 f+2 发出预测。目标为 f+5，距决策 120 ms。若中途跟踪中断，就登记未能评分。两种方法的输入和目标相同。记 p₀、p₂ 为两个位置，匀速预测为 p₂+1.5(p₂−p₀)，位置保持预测为 p₂。评分参照为同一相机系统稍后三角定位的 p₅。全程按同一规则提取，未筛速度、高度、球路或误差大小。

| 一段比赛录像内的筛选 | 数量 |
| --- | ---: |
| CSV 帧行 | 2,465 |
| 至少两个视角有二维球标注 | 1,801 |
| 得到可用三维位置 | 1,689 |
| 可用定位的连续片段 | 79 |
| 取得两次输入，实际发出预测 | 61 |
| 发出后又失去连续跟踪 | 14 |
| 可评分的非重叠窗口 | 47 |

以段为单位，对 47 次三维欧氏误差取中位数，匀速为 **0.162 m**，位置保持为 **0.996 m**。匀速误差在 44 段较小、2 段较大、1 段相等。该结果描述一般比赛画面的短时视频跟踪，参照含三角定位误差。数据表没有逐脚离脚、11 m 点球或接触/过线事件标签，因而对本赛 V6 不贡献可计分的点球。相邻段共享一场比赛和相机环境，未报告独立每脚射门的总体区间。

## StatsBomb 的射门终点

数据来源为 StatsBomb Open Data，2022 年世界杯决赛，比赛编号 3869685。筛选 `shot.type.name == "Penalty"`。4,407 个比赛事件中有 11 次点球，其中比赛及加时 3 次、点球大战 8 次。11 次的 `shot.end_location` 都有三个有限坐标。按提供方的 120×80 场地坐标，9 个进球和 1 个射偏的记录终点位于 x=120，而 1 个被扑的记录止于 x=118.8。这个被扑案例缺少自然过线参照。事件文件也没有每脚 0.05、0.10 s 球心读数，因此本项只检查事件与终点语义。[StatsBomb 固定版本事件](https://github.com/hudl/open-data/blob/0bb2d94a146808c2297936b99b6da8e9b2a05138/data/events/3869685.json) · [数据规范](https://github.com/hudl/open-data/blob/0bb2d94a146808c2297936b99b6da8e9b2a05138/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf)

<img alt="StatsBomb" width="118" src="https://raw.githubusercontent.com/hudl/open-data/0bb2d94a146808c2297936b99b6da8e9b2a05138/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png">

## 复现

从仓库根用 Python 3.9 以上版本运行。命令下载并校验两个固定来源，在指定的新文件中写入聚合结果。若已有原始文件，可追加 `--source-dir private/sources/alternatives` 使用同一校验流程。[复现脚本](../../src/check_auxiliary_tracks.py)

```sh
python3 experiment/src/check_auxiliary_tracks.py --output scratch/d03-replay.json
```

已分别以本机缓存和匿名公开下载运行，两次输出与交付的 `summary.json` 逐字节相同。另以帧号减序号分组并用闭式 2.5p₂−1.5p₀ 重算，可评分段数和两项误差中位数在 10⁻¹² m 内一致。独立点球事件摘录复核了进球、被扑、射偏计数及被扑终点。
