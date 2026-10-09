# LabInsight Agent 当前进度报告

检查日期：2026-10-09。依据：本地当前源码、实际 SQLite schema、CSV 和只读本地调用。本文是快照，不等于所有功能通过测试。最终目标见 PROJECT_GOALS.md。

## 1. 阶段结论

已经形成单份 CSV、静态规则和一个工具的 Agent 原型。程序按项目查询规则，生成判定函数，计算统计，返回规则和相对来源路径。用户此前反馈真实模型调用成功；本次未调用 API，不将此前成功视为最新版本全部场景验证。

实验时间、规则版本、多工具组合、RAG、系统化评估和界面尚未实现。生成器当前存在明确导入阻塞。

## 2. 当前结构

| 位置 | 实际职责 |
|---|---|
| config.py | 根目录、CSV、数据库、提示词、工具定义和环境文件路径 |
| labinsight/analysis.py | 有效筛选、通过/失败数、合格率、有效率 |
| labinsight/rules.py | 单条规则查询、规则转判定函数 |
| labinsight/tools.py | 读取数据和规则、统计、追加 rule/sources、注册工具 |
| labinsight/agent.py | API、多轮调用、参数解析、结果回传和上限 |
| scripts/run_agent.py | 命令行问题入口 |
| scripts/init_db.py | 静态规则表初始化 |
| scripts/generate_data.py | 按规则构造模拟记录，目前无法导入 |
| agents/tools/tools.json | 一个 analyze_project 工具定义 |
| agents/prompts/report_system.md | 中文报告、禁止编造、null 口径 |
| data/实验记录01/01.csv | 当前 100 条模拟记录 |
| data/lab.db | 静态 rules 表 |
| notebooks/ | 学习探索记录 |

本次新增 docs/ 是开发说明，不是 RAG 业务语料。尚无索引脚本、业务文档库、检索模块、评估集或界面。

## 3. 数据与统计已完成部分

当前 CSV 四列：记录编号、项目、测量值、是否有效；没有实验时间。读取文本为 string、测量值为可空 Int64。有效记录要求项目匹配、标记为“是”、测量值不缺失。

count_passed 用判定函数逐条判断后求和，返回普通 int；失败数为有效数减通过数。合格率为通过数除有效数；零有效返回 None，JSON 为 null。calculate_valid_rate 以该项目总记录为分母，但该指标尚未通过工具返回。

统计函数不依赖模型或数据库。CSV 在调用工具时读取，不在导入统计模块时读取。尚无重复编号/schema 的统一校验、按批次/时间统计和数据质量报告。

## 4. 规则与来源已完成部分

实际 schema：rules(project_id TEXT PRIMARY KEY, rule_type TEXT NOT NULL, lower_bound REAL, upper_bound REAL)。每个项目只有一行，没有版本和生效时间。

支持 at_least、at_most、between，包含边界。make_judge 检查必需上下限和顺序；找不到项目抛 ValueError；查询连接在 finally 关闭。

工具只查询一次规则，用同份字典生成函数和返回 rule，并添加 inclusive=True。sources 有 records_file、rules_database、rules_table、rule_project_id。路径转为项目相对路径。

已经有文件/表/项目级追溯，但无文件内容哈希、生成时间、规则版本和逐条判定审计。同一路径后续可能对应不同文件内容。

## 5. Agent 已完成部分

读取外部系统提示词和工具 JSON，加载 .env。OpenAI SDK 请求 DeepSeek 兼容接口；模型与密钥由环境变量提供。timeout=60、max_retries=0、关闭思考、max_tokens=1000。

最多五轮：有工具请求则先保存 assistant 消息，解析 JSON，检查字典参数，查 TOOL_FUNCTIONS 白名单，以 **arguments 调用，结果通过 tool_call_id 回传。ValueError/KeyError/TypeError 转成 error。没有工具请求时打印并返回正文。循环上限异常现在位于循环外，第一次调用工具后可以进入下一轮。

当前只有 analyze_project(project_id)。CLI 支持 python -m scripts.run_agent "问题"，不传问题默认查 B，支持 --help。运行之间不保留对话。

尚未检查直接输出的统计结论是否有对应成功工具结果。提示词尚未明确强制统计问题调用工具，也未要求显示来源。没有执行日志、完整网络/文件错误处理和空正文/输出截断检查。

## 6. 本次发现的问题

### 6.1 生成器导入阻塞：优先级最高

scripts/generate_data.py 导入 get_project_ids，但 rules.py 没有定义。本次导入得到 ImportError: cannot import name 'get_project_ids'。已有 CSV 可以统计，当前生成脚本无法重跑。

短期可实现从 rules 表读取项目编号；版本迁移后再调整规则选择。生成器代码计划按每项目概率抽样，再从合格/失败值池采样，默认范围已是 0～100，missing_probability=0.005，均值 0.8、方差参数 0.01。docstring 写方差 0.1，与代码不一致。概率被裁剪到 [0,1]，不能称其最终分布仍为原正态分布。

概率仅存在 DataFrame.attrs，不写入 CSV，实际合格率不必等于抽样概率。README 旧默认范围 50～100 和 C 无合格值的描述，需要随当前生成器修正。

### 6.2 时间与规则版本缺失

没有实验时间，项目规则只有一行，目前只能静态统计。不能宣称支持历史规则选择或更新前后比较。

### 6.3 可靠性与工程交付不足

API 鉴权/网络、CSV 缺失、数据库缺表等可能直接中断。数据库不存在时普通 connect 会创建空文件，之后无表报错；可加入路径检查或只读连接。初始化正常路径关闭连接，异常路径可继续完善。

尚无固定依赖清单、独立边界测试/问题集、评估指标、日志、迁移和备份流程。后续升级不能直接删除数据库。

## 7. 本次验证与证据边界

- 只读检查实际数据库：只有静态 rules 表。
- 当前 CSV：100 行、四列，没有实验时间。
- 本地调用 analyze_project_tool('B')：有效 18、通过 9、失败 9、合格率 0.5，规则 40～60、inclusive=True，sources 指向现有文件和表。
- 18=9+9，9/18=0.5；这是一次冒烟验证，不等于所有场景通过。
- 导入生成器失败，确认缺少 get_project_ids。
- 未运行生成/初始化命令、未覆盖 CSV、未请求模型 API、未读取密钥。

旧快照中 B 曾为 10%，本次为 50%，不能把旧数字当作固定真值。演示和评估应固定数据快照。

最近可读提交为 416d88e，此前推送已成功。本次 git status 报“this operation must be run in a work tree”，因此没有确认当前修改与远程同步情况，不能假定最新改动已推送。

## 8. 最终目标对照

| 能力 | 状态 |
|---|---|
| 本地 CSV 统计、静态 SQLite 规则 | 已实现，本次调用成功 |
| 返回实际规则与来源 | 已实现，本次返回验证 |
| API 工具循环 | 已实现，用户此前报告成功 |
| 重生成数据 | 阻塞，缺少 get_project_ids |
| 历史时间版本匹配 | 未实现 |
| 指定版本重评、时间/版本汇总 | 未实现 |
| 失败明细和偏离量 | 未实现 |
| 多业务工具和日志 | 未实现 |
| 业务语料、全文基线、RAG | 未实现 |
| 版本约束检索与引用 | 未实现 |
| 固定评估集和指标报告 | 未实现 |
| 展示界面和报告导出 | 未实现 |

## 9. 下一阶段顺序

1. 修复 get_project_ids 与生成器注释，保持只有显式运行才写数据。
2. 备份数据库，设计版本表和时间字段，明确无规则和分母口径。
3. 用手工小样本验证 82 在阈值 80/85 下的差异、更新时刻和缺失时间。
4. 实现历史/指定模式，返回可判定数、未解决数、版本分组，再适配随机生成器。
5. 增加失败明细、范围查询、schema、提示词和日志。
6. 准备有额外内容的业务文档，全文基线后实现 RAG 和独立评估。

不将当前进展估算为简单完成百分比：静态原型、时间规则、RAG 和评估工作量不同。当前处于基础工具闭环完成、时间版本功能待启动的阶段。
