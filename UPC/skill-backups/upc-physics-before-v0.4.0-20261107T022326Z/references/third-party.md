# 第三方能力的适配与来源

核心方法来自四年题目与16篇论文的比较，见 [案例方法索引](methods.md)。本文件登记辅助来源和采用范围，不是AI使用记录。下述流程与脚本为本项目重新组织/编写，没有整段复制第三方技能或捆绑其实现。调用第三方时仍需检查其当前版本、实际依赖与许可。

| 来源 | 第一轮采用的部分 | 本项目适配 |
| --- | --- | --- |
| [anticipate218/math-modeling-skill](https://github.com/anticipate218/math-modeling-skill) | 基线→改进→验证、任务覆盖与结果表达 | 不继承国赛/MCM等特定规则；不恢复AI使用报告；模型选择以物理案例为主 |
| [K-Dense SymPy](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/sympy/SKILL.md) | 假设明确的符号推导、精确量与数值化 | 仅作数学支持，物理机制和分支仍独立判断 |
| [K-Dense literature-review](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/SKILL.md) | 缺口导向检索、来源定位与证据核实 | 普通竞赛查参不自动变成系统综述 |
| 已安装 `research-writing-skill` | 从论点和证据组织章节，再成篇与润色 | 讨论中文、论文默认英文；支持从零写完整稿 |
| [K-Dense scientific-writing](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-writing/SKILL.md)，本地2.3 | 证据驱动、方法/结果/讨论一致性、引用与图表核对 | 保留科研准确性，不套用临床申报、期刊投稿或逐条人为审批流程；不增加AI使用记录 |
| 已安装 `mattpocock-skills`，本地插件1.3.1：writing-for-agents、diagnosing-bugs | 按需读取、明确完成条件；先复现信号再修正 | 前者用于技能架构，后者用于科研计算故障，不要求所有探索都先写测试 |
| [K-Dense MATLAB](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/matlab/SKILL.md)，本地1.4 | 函数化、单位/数组语义、版本/产品边界与复现 | 用户已授权按需使用专业软件；不导入重复确认步骤；具体命令另核对MathWorks文档 |
| Codex `skill-creator` 与已安装 `skill-creator` | 精简入口、功能资源、可执行检查、独立前向试运行 | 不保存原始提示词/回答、对话或耗用统计；保存科研测试输入/产物和判断结果。第一轮结束不强制等待人工反馈 |

本地文件的准确路径、内容散列和读取版本登记在开发项目 `training/round-01/third-party-manifest.json`，不作为可分发技能运行依赖。需要调用时通过当前技能列表定位；未安装时继续使用本技能的内置流程，不擅自批量安装。

专业软件的接口来源另见 [software.md](software.md)。首轮构造时没有实际运行 MATLAB、Simulink、COMSOL 或 ANSYS。后续反馈修订已在 macOS / R2026b 验证随包的基础 MATLAB 算例；这不代表其他产品或工具箱已验证，不将文档支持写成执行成功。

## 软件方法来源署名

辅助方法参考 K-Dense 的 Scientific Agent Skills，依其来源说明在此登记：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065)。作者与版本元数据于2026-10-11在[arXiv记录](https://arxiv.org/abs/2609.00065)核对；该署名说明辅助来源，不是参赛论文已获得的研究结论或强制AI使用声明。
