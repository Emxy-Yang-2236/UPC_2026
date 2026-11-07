# V6 真实点球数据 · 来源核验

2026-11-07 已读取 Ball3D 固定版本 `bba36a2cc8415701134b1f25a9c31602dde8d953` 的公开文档。作者列出比赛及练习片段、三角测量文件 `track/ball_3d-gt.csv`、触球标注及序列帧率，坐标单位 dm。匿名访问其 Google Drive 数据目录实际返回登录界面。当前能核实数据发布和格式，尚未取得可逐脚筛选的原始标注；候选、纳入、排除、遮挡扑出等分母均未知。[原始数据说明](https://github.com/lukaszgrad/ball3d/blob/bba36a2cc8415701134b1f25a9c31602dde8d953/DATA.md) · [数据作者的项目页](https://lukaszgrad.github.io/soccer-ball3d/)

接手人可将已获授权的轨迹、标定、触球标签和帧率置于受控的 `private/sources/`，保存文件版本、字节数与 SHA-256。按[方案 V6](../../../design/protocol.md)核实同一脚分组、点球点、时间对齐、独立过线参考及提前接触。实测留出统计与合成盲测分别发布。

已从独立来源取得 [德国联赛点球的三维跟踪及过线参考](idsse-penalties/README.md)，可直接开始按原生帧时间的案例分析。
