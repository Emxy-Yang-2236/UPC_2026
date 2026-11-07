# 研究项目约定

适用于新的完整研究项目；已有项目可以适配，不强行搬文件。所有本地路径相对项目目录；元数据 CSV、`project.json` 和研究产物解析后的真实路径均须留在项目内。允许指向项目内文件的符号链接；指向项目外、循环或断开的链接不能满足交付要求。脚本需要 Python 3.9 或更高版本，仅使用标准库。

## 初始化

团队使用同一 Git 仓库或需要跨机器交接时，加 `--team` 建立四阶段工作区。此布局采用 `format_version=2`，题面摘要在 `design/problem.md`，六张表在 `experiment/records/`，表中路径仍相对研究仓库根目录。独立报告的附件清单则相对该报告目录。跨阶段操作见 [团队仓库与两次交接](team-handoff.md)。

团队布局的项目审计还返回 `handoffs.design` 和 `handoffs.report`。完整项目的 `ready` 同时要求两个交接包、研究证据和稿件就绪。单独交方案或交总报告时使用 `handoff.py`，可以在尚未写稿时完成阶段验收。

```text
python3 <skill>/scripts/init_project.py <new-project> --title "题目" --problem <problem.md>
```

生成 `project.json`、`problem.md`、`research-state.md`、六份 CSV，以及 `src/`、`data/raw/`、`data/derived/`、`figures/`、`paper/`。不覆盖已有目录、文件或符号链接。`--problem` 可省略，此时题面文件明确标为待提供。题面及随技能分发的论文提纲会在创建目录前读取；输入不可读或提纲缺失时不会留下新项目。初始化返回 `ready=false`，复制题面不表示研究已经完成。

CSV 用 UTF-8 与标准转义；引号必须闭合，数据列数必须与表头一致。单元格中多个 ID/路径用分号分隔。保留表头，空表不是完成。使用稳定 ID（如 R1、S1、C1、V1）便于交接，不给每一句普通叙述都建登记行。参数的显式数值不得为 NaN／Infinity；允许有说明的区间或符号文本，其语义需人工检查。

| 文件 | 列（顺序） | 用途 |
| --- | --- | --- |
| `requirements.csv` | `id,question,status` | 题目可检查要求，status 为 open/answered |
| `sources.csv` | `id,kind,locator,status` | kind 为 problem/literature/data/assumption/derivation；status 为 verified/assumed/pending；assumed 仅用于 assumption |
| `parameters.csv` | `symbol,value,unit,role,source_ids` | role 为 given/literature/measured/assumed/fitted/derived；无量纲 unit 写 1，范围可用明确文本 |
| `claims.csv` | `id,requirement_ids,statement,source_ids,artifact_paths,status` | 主要结论及支撑；status 为 supported/conditional/open；条件主张在 statement 写出条件 |
| `validation.csv` | `id,claim_ids,method,criterion,result,artifact_paths,status` | status 为 pass/fail/pending；接受标准和实际结果分开 |
| `runs.csv` | `id,kind,command,input_paths,output_paths,status` | kind 为 simulation/measurement/analysis；status 为 completed/failed/planned；测量可在 command 写实际采集步骤与方法文件路径 |

来源 locator 对 literature 允许 DOI/URL/书籍及页码，对 problem/data/derivation/assumption 使用本地相对文件路径，可在 `#` 后追加页码/定位。外部来源 verified 表示已人工核对支持内容，不是脚本自动联网认证。

`project.json` 须为标准 JSON 对象，键唯一，数值有限。`title` 为非空字符串，`stage` 为 analyze/research/model/compute/validate/write/deliver 之一，`paper_path` 为完整稿源文件路径。整数 `format_version` 取 1（原布局）或 2（团队布局）。审计按版本定位证据表，使用相同的科学证据判据。

## 交付完整性检查

```text
python3 <skill>/scripts/audit_project.py <project>
```

检查空表/字段、ID 重复、状态、来源/要求/结论关联、产物存在且非空、完成运行的输入输出，以及稿件路径。检查 `answered` 要求至少有 supported/conditional 主张，主张至少有通过的验证条目；open 主张、fail/pending 验证、failed/planned 运行及被参数或主张引用的 pending 来源会阻止就绪。条件主张允许交付条件研究，但输出提醒限制；assumed 来源不能伪装已验证文献。

定性或纯解析研究无需强行造运行：`runs.csv` 可为空。没有外部参数时 `parameters.csv` 可为空。主要结论仍需要本地推导/分析文件和适用的验证。仿真/实测型结果应登记实际运行。

返回 JSON：`ready`、`errors`、`warnings` 和数量，另将完整性与研究状态分开显示：

- `integrity_ok` / `integrity_errors`：格式、必需表、字段、文件和引用等是否完整。缺失产物、无效状态值或未知 ID 仍是完整性错误。
- `status_findings`：结构可解析但未满足就绪条件的登记状态，含表名、ID、状态和说明。例如保留的 failed 试算、fail/pending 验证、open 主张和未验证来源。
- `ready`：继续执行原严格判定；上述任何问题都会为 false，原有 `errors` 仍包含所有问题，退出码仍为就绪 0 / 未就绪 1。新增分类不会把失败改成通过。

研究可能文件齐全而仍有未通过的关键检查。此时可以交付说明条件、失败与缺口的阶段报告，但不能借 `integrity_ok=true` 宣称物理验证完成或论文已可提交。失败条目属于历史试算、被替代候选还是当前主张的关键缺口，需要阅读关联的结果和研究状态判断；不要按 ID 名字自动忽略。脚本**不判断**语义真伪、量纲正确性、引用支持力、数值收敛或当前比赛规则。

## 证据流

题面 → 要求 → 主张 → 推导/数据/图表；来源 → 参数/事实；运行 → 数据 → 验证 → 主张；论文只引用已建立的研究事实。

保留科研所需的真实输入/输出与方法，不保存提示词、AI 回答、对话文本、AI 使用报告或模型耗用统计。审阅用的研究报告/论文是任务成果，不是聊天归档。
