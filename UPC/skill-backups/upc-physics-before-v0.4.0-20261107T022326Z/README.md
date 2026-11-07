# UPC Physics

**v0.3.0 · MIT · Python 3.9+ · MATLAB 可选**

面向 University Physics Competition（UPC）的物理研究 skill：从题目、假设与模型，到可复现计算、证据核验和完整参赛论文。默认中文讨论、英文写作。这是独立的备赛工具，与赛事主办方无隶属或背书关系。


内含六个按需加载的功能模块：审题、资料研究、物理建模、计算与实验、验证、论文写作。机制细节与开放设计两条路线按问题特点选择，可以组合。核心方法由 2021、2022、2023、2025 年题目与 16 篇论文的比较提炼，发布内容为方法摘要、原创流程、脚本及模板。

## 1. 如何安装

### 准备 Node.js

先用 `node -v` 查看版本。已有 **Node.js 22.20.0 或更高版本**，可直接跳到下面的「全局安装 skill」。需要安装时，按系统选择一条命令。

**macOS（Homebrew）**

```bash
brew install node
```

**Windows（PowerShell，使用 WinGet）**

```powershell
winget install --id OpenJS.NodeJS.LTS --exact --source winget
```

**Linux / WSL（Bash 或 Zsh，通过 nvm 安装 Node.js 26 LTS）**

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.41.0/install.sh | NODE_VERSION=26 bash
```

安装后重新打开终端，用 `node -v` 和 `npx -v` 确认两者可用。macOS 或 Windows 也可使用 [Node.js 官方安装包](https://nodejs.org/zh-cn/download)。

### 全局安装 skill

`-g` 表示全局安装，当前用户的所有 Codex 项目都可使用。

```bash
npx skills add Emxy-Yang-2236/UPC-skills --skill upc-physics --agent codex -g
```

### 更新

首次改用 `npx` 时先执行上面的安装命令，之后按名称更新这个 skill。

```bash
npx skills update upc-physics -g
```

## 2. 需要的环境与材料

| 项目 | 需要准备什么 |
| --- | --- |
| 技能核心 | 本包已包含流程、四年案例摘要、工具与模板；|
| 当前研究 | 完整题面、当前比赛要求，以及已有模型、代码或数据；从零开始时只需先提供题面 |
| 附带 Python 工具 | Python **3.9+**，仅使用标准库，无额外 `pip` 依赖；实际仿真库按题目另行选择 |
| MATLAB / Simulink | 可选；选择它们时需自行安装、具备相应许可及所需工具箱，先检查环境再运行 |


## 3. 子 skill 结构

`upc-physics` 是主入口，按当前任务读取六个功能子 skill，无需分别安装：

| 子 skill | 主要职责 |
| --- | --- |
| [upc-analyze](modules/analyze/SKILL.md) | 审题、拆解要求、比较研究路线 |
| [upc-research](modules/research/SKILL.md) | 阅读材料、检索文献、核实参数与来源 |
| [upc-model](modules/model/SKILL.md) | 确定假设、建立方程、比较模型 |
| [upc-compute](modules/compute/SKILL.md) | 实现仿真、设计实验、处理数据 |
| [upc-validate](modules/validate/SKILL.md) | 检查物理一致性、数值误差与证据 |
| [upc-write](modules/write/SKILL.md) | 从真实研究结果组织、撰写和完善论文 |

建模另有“机制细节”和“开放设计”两条路线，可按题目组合，不固定对应 A/B 题。

## 4. 如何使用

**调用主 skill：**

安装后在 Codex 中新建会话，输入 `$upc-physics`，同时提供题面或已有材料的路径。若未被识别，直接让 agent 读取安装目录中的 `SKILL.md` 及其引用文件。其他 agent 的调用方式以其技能支持为准。

**配合自备的 grill 技能讨论建模：**

最初构思时，可以用自备的 grill 技能分轮讨论模型选择。下例使用 `$mattpocock-skills:grilling`，请按本机安装的名称调用。

> 使用 $upc-physics，并结合 $mattpocock-skills:grilling。题面在 problem.pdf，先和我讨论方案。按“题目目标与评价指标 → 系统边界、主导机制和假设 → 状态变量、方程框架、初始/边界条件 → 参数来源与验证方法”的顺序推进。每轮只问当前可决定的关键问题，编号并给出推荐方案、理由和取舍，等我回答后再进入依赖这些答案的问题。可查证的事实请先读文件或检索。最后整理出假设表和大体建模方案，包含最简基线、可选改进及待验证问题；我确认开始执行后再进入仿真或实验。

你可以逐题修改，也可以回复“本轮都按推荐”。讨论确认的是研究计划，假设的适用性仍需后续检验。

### Grill 定案后写方案设计报告

在团队研究仓库的原对话中，用这段提示词生成草稿。

> 使用 $upc-physics，把已确认的方案写进 `design/`。在 `problem.md` 列题目要求和验收标准，在 `model.md` 写假设、方程、初边条件和参数表（值、单位、来源），在 `protocol.md` 给出首例输入、运行命令或待实现接口、预期输出、容差及后续工况。用 `README.md` 说明选型理由、待验证项和队友的第一步，附件列入 `materials.csv`。先保留草稿。

让队友在新会话中只看方案目录，试跑首例或完成第一个实现步骤。通过后，在方案首页记录检查结果，标记 `交接状态：可执行`，再从研究仓库根目录运行 `python3 tools/handoff.py design design`。[方案报告模板](assets/team/design/README.md)

### 常见调用示例

**新题目：**

> 使用 $upc-physics。题面在 problem.pdf，研究成果保存到本项目目录。先解释题目要求、比较建模路线，明确假设，再推进可运行的基线模型、验证和论文。

**已有代码或数据：**

> 使用 $upc-physics。阅读 src/ 和 data/，检查方程、单位、边界条件、数值误差及结论证据，修复问题并更新研究状态。

**开始写论文：**

> 使用 $upc-physics。根据本项目的真实研究结果和图表，搭建论证结构并完成英文参赛论文；列出证据缺口，不补造结果或引用。

想使用 MATLAB 时追加：“优先使用 MATLAB，先检测可执行程序、版本与工具箱；如果当前不能运行，明确区分已写代码与已验证结果。”把示例中的路径换成自己的实际文件位置，也可以直接用自然语言指定任务。

有时间或算力限制时一并说明，例如：“先完成足以回答原题的基线，在少数代表工况检查关键近似，再决定是否扩展昂贵仿真。”需要反复讨论构思时说明这一偏好；关键方案已经确认后，助手应继续完成获授权的工作。

流程按需要在“审题 → 资料 → 建模 → 计算/实验 → 验证 → 写作”之间迭代，已有成果可以从中途进入。机制细节与开放设计两条路线可以组合，不固定对应 A/B 题。

### 两位队友在不同电脑接力

共同克隆团队的**研究仓库**，进入该目录后再打开 Codex。仓库根 README 给出当前任务、负责人和下一步。初建工作区可用 `python3 <skill>/scripts/init_project.py <新目录> --title "研究题目" --team`。已有队友建好的仓库直接克隆即可。

| 接手时机 | 可直接交给 Codex 的任务 |
| --- | --- |
| 在另一台电脑开工 | 使用 $upc-physics，只从收到的 design/README.md 开始。核对方案版次，按协议完成首例并对照预期，再在 experiment/ 保存后续运行、数据和验证。 |
| 实验完成 | 使用 $upc-physics，将实际方法、带单位结论、图表、可复现材料和引用整理进 report/。在独立目录按报告复核一个代表结果，再交给写作者。 |
| 只拿到总报告 | 使用 $upc-physics，只依据这份 report/ 撰写完整英文参赛论文。让摘要数字、正文主张、图表和引用逐项对应包内证据；指出需要实验负责人补充的具体缺口。 |

确认设计、完成基线/一批实验、出现重要失败、冻结报告或形成可审阅稿时，各保存一次 Git 提交并同步约定分支。交接时提供分支、完整提交号、报告入口和下一步。检查及导出方法见 [团队仓库与两次交接](references/team-handoff.md)。

## 5. 可选的工具自检 （若建模阶段出现异常）

在 `upc-physics/` 目录打开终端，运行：

```text
python3 scripts/numerical_checks.py biquad --a1 -1.9 --a2 0.88
```

应返回 JSON，极点约为 `1.1` 与 `0.8`，`stable` 为 `false`。这是预设的不稳定示例，正常退出表示诊断工具成功运行。如果本机 Python 命令是 `python` 或 `py -3`，替换命令开头即可。

也可让agent调用 `scripts/init_project.py` 创建新的研究目录，再用 `scripts/audit_project.py` 检查交付材料。新建空项目得到 `ready=false` 属于正常情况；审计只检查材料结构与关联，不证明物理结论正确。详见 [研究项目约定](references/project-contract.md)。MATLAB 的可选检查见 [软件适配](references/software.md)。

审计中的 `integrity_ok` 表示文件与关联完整性，`status_findings` 列出未完成或未通过的登记项。保留失败试算时，文件可以齐全而 `ready` 仍为 false；不要删掉失败或放宽标准来获得通过。


## 6. 许可与来源

本仓库的原创 skill 文本、脚本、模板和文档采用 [MIT License](LICENSE)，允许使用、修改和再分发，须保留版权和许可声明。第三方原始作品及软件继续适用各自的许可，详见 [NOTICE.md](NOTICE.md) 和 [第三方来源](references/third-party.md)。

原始赛题与获奖论文 PDF、完整解答、个人研究数据和开发对话不随本仓库分发。案例摘要保留来源定位与核验边界；获奖论文中的报告值不能直接视为已独立复现的结果。使用时应自行核实当届比赛要求。

## 7. 维护与版本

版本变化见 [CHANGELOG.md](CHANGELOG.md)。附带脚本只需 Python 标准库。在源码仓库根目录运行：

```text
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/build_release.py
```

构建使用 `release-files.txt` 的明确文件清单，输出到 `dist/`：版本化 `.zip`、`.skill`、`manifest.json` 与 `SHA256SUMS`。安装包只包含使用 skill 所需文件和许可说明；维护测试与构建工具通过源码仓库获取。后续维护步骤见 [MAINTAINING.md](MAINTAINING.md)。
