# 来源与证据范围

- S1. University Physics Competition, 2026, Problem B. 给出几何、两次观测、官方样例和任务。本文的风限与观测噪声均为情景假设。[原题](https://uphysicsc.com/2026contest.html)
- S2. J. E. Goff and M. J. Carré, “Soccer ball lift coefficients via trajectory analysis,” European Journal of Physics 31 (2010), 775–784. 支持速度相关阻力基线与由飞行估计升力的方法。[DOI](https://doi.org/10.1088/0143-0807/31/4/007)
- S3. J. E. Goff, J. Kelley, C. Hobson, K. Seo, T. Asai and S. Choppin, “Creating drag and lift curves from soccer trajectories,” European Journal of Physics (2017). 作者的 29 条飞行轨迹覆盖初速 9.3–29.9 m/s。用这个速度域限制另一条曲线的延伸是本研究的建模选择。[作者稿](https://shura.shu.ac.uk/15728/1/Kelley%20-%20Creating%20drag%20and%20lift%20curves%20%28AM%29.pdf) · [DOI](https://doi.org/10.1088/1361-6404/aa6fcd)
- S4. T. Mizota et al., “The strange flight behaviour of slowly spinning soccer balls,” Scientific Reports 3, 1871 (2013). 支持低旋非定常力机制。补充真值中的振幅和周期为设定情景。[论文](https://www.nature.com/articles/srep01871)
- S5. Ł. Grad, M. K. Czajkowski and A. Varashylau, “Physics-Based 3D Ball Trajectory Reconstruction from Monocular Soccer Video,” 2026. 多视角球轨迹、数据分组与标注单位已核实；本批没有使用原始标注来评价实测精度。[作者项目页](https://lukaszgrad.github.io/soccer-ball3d/) · [发行数据说明](https://github.com/lukaszgrad/ball3d/blob/bba36a2cc8415701134b1f25a9c31602dde8d953/DATA.md)
- S6. 本队方案 B-1.0 的模型权重、风速、球款偏移及尾流参数为预设情景，所有种子和单位见包内 `config`。[本轮参数与验证记录](evidence/measurements.json)
