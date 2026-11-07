# 三个真实 11 m 点球的逐帧数据

下载 [frames.csv](frames.csv) 即可读入 MATLAB 或 Python。[shots.csv](shots.csv) 用同一个 match_id 和 event_id 对应比赛、进球标签和门线参考位置。共有 303 行，来自 3 场比赛，每脚保留官方事件时间前后各 2 s 的 101 个连续帧，含死球帧。坐标单位为 m，时间间隔 40 ms。ball_status=1 表示比赛球处于活动状态。逐帧表保留原始球场中心坐标、UTC 时间、帧号、相对官方事件的毫秒数和原始高度读数。

| 比赛 ID | 主客队 | 首个活动帧距官方事件 | 门线参考 (Y,Z) / m |
| --- | --- | ---: | ---: |
| J03WMX | 科隆 – 拜仁慕尼黑 | −600 ms | (2.75, 0.16) |
| J03WOH | 杜塞尔多夫 – 雷根斯堡 | +880 ms | (2.92, 1.18) |
| J03WR9 | 杜塞尔多夫 – 凯泽斯劳滕 | +40 ms | (3.07, 0.47) |

**筛选与门线定位。** 逐场解析 IDSSE v1 的全部 7 份赛事 XML，仅选实际执行的 Penalty/ShotAtGoal，得到 3 条，均标为 SuccessfulShot，登记距离均为 11.00 m。三场球场长度均为 105 m，这三脚均向跟踪系 X 正方向进攻。取两条连续活动帧夹住 X=52.50 m 的时刻，以 X 线性插值 Y、Z。科隆一脚恰有一帧位于门线上。门线参考直接取自后段跟踪，与预测器的前段拟合分开。数值沿用供应商的 Y 正向与球高口径，未独立校准场地的高度零点或跟踪误差。按本题以罚球点为平面原点时，这三脚的纵向坐标为 x=X−41.50 m。

**使用范围。** J03WOH 的首个活动位置为 (41.56, −0.04, 0.11) m，距罚球点水平约 7 cm，最适合先做案例。J03WMX 和 J03WR9 的首个活动位置已分别超过罚球点纵向 0.71、1.47 m。活动窗口由连续的球状态和过线帧识别，真实离脚时刻的 ±10 ms 精度仍待独立核对。先按原生帧时间做外推，单独列实测结果与时间不确定性。只有确认离脚时刻和观测截止后，才能纳入原协议的 0.05/0.10 s 严格盲测。两帧输入只可使用截至该时刻已经获得的读数。三脚均为进球，无法据此评估总体进球率或校准总体 90% 覆盖率。[本队 V6 协议](../../../../design/protocol.md)

**来源与许可。** 原始比赛数据来自 DFL / Sportec Solutions。Manuel Bassek、Robert Rein、Hendrik Weber 和 Daniel Memmert 发布的 *An integrated dataset of spatiotemporal and event data in elite soccer*，Figshare v1 (2025)，以 CC BY 4.0 许可发布。本包的改动为选取点球窗口、转换表格、增设时间差和插值门线参考值；选取后的数据沿用 CC BY 4.0。[原始数据 DOI](https://doi.org/10.6084/m9.figshare.28196177.v1) · [数据论文](https://doi.org/10.1038/s41597-025-04505-y) · [文件镜像](https://huggingface.co/datasets/pysport/idsse-data/tree/a715a38dfbaf5f58e431727c2b78d174101a703c) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

**复现。** 从研究仓库根运行下面的命令，使用 Python 3.9+ 标准库和公开下载。脚本对 7 份事件和 3 份比赛信息逐文件核对 Figshare 的 MD5；三份大型跟踪 XML 仅读取覆盖目标时段的字节范围，分别核对内容范围和 SHA-256。镜像提交、数据版本、文件名和哈希见[来源清单](source-manifest.json)。输出目标须是新目录。

```sh
python3 experiment/src/screen_idsse.py --out scratch/idsse-replay
```
