# B01 · 官方读数下的两条可行轨迹

设计版本 `4ad681dc280c5abfd8b78f01348e1b1620ba00b3`，实现 `0d47c6c5803adef117ad30213298ab90d8b75b2b`，2026-11-07 在 macOS 上执行。两种解都位于 S 模型参数支持内。两条轨迹的早期读数吻合，门面交点相距约 0.08759 m；条件最坏误差下界为其一半。此量不是射门总体的典型误差。详见 [Python 反演](pair.json) 与 [MATLAB 独立积分](matlab.json)。

从仓库根、用新输出目录运行以下命令。Python 版本和数值库版本记在 JSON 中，MATLAB 为 R2026b。

```sh
mkdir -p scratch/B01
python experiment/src/pair.py > scratch/B01/pair.json
matlab -batch "addpath('experiment/src'); verify_pair('scratch/B01/pair.json','scratch/B01/matlab.json')"
```
