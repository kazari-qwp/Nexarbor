# 当前进度与恢复入口

更新时间：2026-10-27。

当前最新验证：**294 项 Python 测试通过**；D015 独立信号运行器、脉冲及 agents.activity 已迁入并通过组件联动。真实 DSH/RPC/JSONL 再次重开续跑通过；三个完整应用尚未验收，core 本阶段未改。

## 已完成

- 基线提交 `6cbf57af33ed0c6698abb69a396feb23fdcd5efa`；计划提交 `7c95aac`；结构整理提交 `cae9fee`。
- 已保存完整计划、三应用验收目标及 5641 项原文件结构索引；语义审查尚未全部完成。
- 确认原小镇一天是 5 tick，并定位原应用、锁、工具路由与 DSH 检查点测试。
- 基础实现已移入 `domain/core/`，结构整理提交时 14 个文件与基线 AST 一致；后续已授权的频道和复制扩展见 D004、D005。
- Agent、工具发现、记忆内部策略已移入 `modules/`；模型 HTTP 适配移入 `adapt/models/`。
- 更新了现有代码、示例和测试的 import；目录整理时 106 项行为测试通过。
- 原 allow/deny 频道匹配已按用户确认迁入；两张表的浅拷贝已实现，提交 `3bb3a08`。此前 115 项测试通过（106 原有 + 6 频道 + 3 表复制）。
- D001 等待式门禁、局部快照和节点事务已实现并完成组件级验证；完整日志/宿主接线待迁移，详见后续记录。
- 用户补充应用二数据节点统一继承当前 DataNode；已定位五类旧实现并建立迁移清单。五种数据节点均已继承新 DataNode，完成节点级迁移。Value 按 D007 文件化；CSV/SQLite 阶段提交 `af9f53c`；知识集合/向量及目录快照已验证。
- D006 的上下文组装器、原 AgentInputs 和文件端口已迁移，提交 `02aa403`；131 项测试及来源 UI 脚本语法检查通过，core 未改。
- 原 state_journal/state_store/Checkpoints 已迁入 app/persistence（提交 `d062d7b`），AST 一致。8 项原存储层断言及 2 项原杀进程恢复断言通过；该阶段 141 项 Python 测试通过。
- 原 DSH AgentLoop、会话事件和原生日志游标实现已迁入 adapt/harness；3 项真实 SDK 的本地模型替身测试通过。证据见 evidence/2026-10-27-runtime.json；不代表三应用验收完成。
- 知识节点阶段 169 项 Python 回归通过；本地真实 BGE/LlamaIndex 检索、源目录移走后副本查询、独立修订、索引删除和计算进程均验证通过。证据见 evidence/2026-10-27-knowledge-nodes.json。
- D008 已确认：不保留同归属树无连线调用，不增加 family 访问模式；新负向/显式连线验证通过。


- D010：按用户要求撤回未接入运行的工具目录和 RuntimeModule 原型；发现器恢复简单 discover()，旧执行器后续直接消费可迭代 Tools，不添加目录/来源包装或重复可达性检查。撤回后既有 169 项 Python 回归通过。

- D011：上下文组装器主流程精简，四路提取为策略类，共用 Markdown 收集逻辑。删除重复验证、正文核对与多余注释；12 项相关测试及全部 169 项回归通过，core 未改。

- D012：内置模块已按模块目录归拢；Agent 的输入/记忆和组装器策略均随主体放在同一目录。后续应用模块采用相同规则。

- D013：Agent 已改成 domain/agent/ 的 AgentNode/MarkdownAgentNode，类型 agent；删除 AgentModule。工具发现跳过 Agent 工具表/中继，上下文只读 markdown 类型，Agent 的本地工具自行加入。保存重开保留记忆和输入状态。
- 原执行器 prepare/ACK/bind/prune/工具引用调用已迁入 adapt/harness/executor，使用新 Agent 节点；AsyncRuntime 原样迁入 app/runtime。13 项专项通过，完整 Python 回归当前 186 项通过。锁/完整宿主与三应用接线仍待迁移。

- D001 实施：app/transactions 已迁入原等待/重入/超时/取消/死锁协调，access 到达节点后等解锁；汇合、偏置、处理函数、出边受门禁保护。快照保持节点/模块/工具/回调身份，覆盖真实文件、输入和执行状态/配置。21 个协调方法、NodeRecords/SignalWork 保持原 AST。
- 锁组件阶段全量 219 项 Python 回归通过；真实 RAG、LlamaIndex 和计算进程回滚通过，付费 API 调用 0。原三项节点事务杀进程验收、完整生产快照编码/存储和宿主接线尚未完成。证据见 evidence/2026-10-27-node-locks.json。

- D001/P4：新 Backend 已联动原 Checkpoints、节点事务、会话游标和文件恢复；原 3 项节点事务杀进程断言通过。恢复包分支、游标版本检查和模块/工具箱重建新增 10 项通过，全量 234 项通过。核心本轮未改，用户 DataNode 默认值编辑仍未暂存。详见 evidence/2026-10-27-persistent-runtime.json。

- P4 接线：原 JsonRpcTransport 和原 NativeRunner/SDK host 已迁入 adapt；240 项 Python 回归通过。真实 Python↔DSH 进程、原生工具回调、实际 Markdown 文件、JSONL 游标和 4 个恢复点验证通过，关闭重开后继续同一会话（5 次本机模型 HTTP，付费 0）。修复检查点确认的通知循环以及 Agent 初次发现工具时在事件循环同步等待的问题。证据见 evidence/2026-10-27-native-bridge.json。

- P5 业务迁移起步：projects/npc_town/modules/ 下 records_store、clock_counter、world_time、periodic_checkpoint 均为新 Module 类，节点操作用 access，事务/宿主保存以明确端口注入。原记录仓 7 个纯算法和时钟 2 个纯算法保留；13 项业务验证通过，全量 253 项通过。时钟的 5 tick 验证仅为组件测试，不是完整小镇应用验收。证据见 evidence/2026-10-27-town-foundations.json。

- P5 私人记忆：原 agents.memory 的列表/记忆键/查询/上限规则已迁为新 Module，6 项专项通过；工具参数 Schema 与原声明一致。原始请求者 ID 随 prepare/invoke 调用链传递，只保存身份元数据，节点访问仍通过 access。全量 259 项通过，真实 DSH 重开续跑再次通过，付费 0。证据见 evidence/2026-10-27-town-memory.json。

- 消息模块迁移提交：messages.box/messages.relay 已用新 Module/access 实现；11 项专项通过，消息阶段全量 270 项通过。扣费/入箱回滚、并发去重、原请求者、私有读取、同层延后通知和保存重建均验证。公开消息箱的实际 CallableTool.name 使用原稳定 hash 名称，执行器仍直接 for Tools 并调用引用。证据见 evidence/2026-10-27-town-messages.json。
- D014 已被 D015 撤回：移除可选去重和 7 项专属重访测试，access 恢复到 e79b09e 的父提交版本。用户决定信号不复用 access，由独立 app 运行器保留原业务；不再等待共享层接口讨论。撤回后全量 270 项通过，证据见 evidence/2026-10-27-signal-access-rollback.json。

- D015 实施：信号运行器独立位于 app/runtime/signal_runtime.py；使用现有节点门禁，保留分层汇合/去重、LayerWork 收尾、单次回源、预算/取消/故障和幂等日志。PulseNode 继承新 Node，保存/恢复及局部快照覆盖脉冲参数和状态。agents.activity 按新 Module 实现，模型通过显式异步端口运行，不包进节点事务；模块订阅位于 app/runtime/module_signals.py。16 项信号、8 项活动测试通过，其中实际时钟/双 Agent 活动/消息箱/中继联动验证同层回应先完成再推进。全量 294 项通过，真实 DSH 重开续跑通过（5 次本机 HTTP，付费 0）。见 evidence/2026-10-27-independent-signals.json。

## 尚未完成

- 原项目业务模块、完整项目/信号宿主和前端尚未完成迁移。上下文组装器已完成模块级迁移，执行器 prepare/ACK 等模块级行为已迁入，真实宿主/RPC/锁/检查点已接通；完整 Studio 和项目组件接线仍待迁移。
- 尚未运行三个应用在新核心上的验收。临时 API 演示不是最终验收。
- 每个旧文件的语义审查、去留理由和迁移证据需继续记录在 FILE_INVENTORY.csv。

## 下一步

五种数据节点的节点级迁移已完成（提交 `d8e298f`）。B006 已按 D008 解除；B007 已按 D015 解除，信号独立运行器与活动组件已迁，先读 SIGNAL_BOUNDARY.md；D014 的共享方案已撤回。先按 D009/ACTIVE_APPLICATIONS.md 核对实际入口；小镇工具发现器迁回 NPC 本节点，不迁无连线亲缘捷径。按 D010 从实际旧执行器及应用调用点迁移，直接使用既有 Module/access/Tools；不先造目录和框架。Agent 新方案 D013 已完成节点级验证，继续原执行器的真实宿主/RPC/检查点联动；D001 锁/局部回滚已接入增量存储，原三个节点事务杀进程断言已通过；真实 NativeRunner/RPC 已接通；继续实际应用模块（记录仓和时钟已迁）；调用者身份元数据、私人记忆、消息箱/私信中继已迁，继续位置/移动/转账等模块、实际项目装配、信号订阅刷新与模块自有资源快照联动。完整前端、制作 Agent 文档和三应用最终验收均未完成。

## 继续时遵守

1. 先读 PLAN.md、DECISIONS.md、BLOCKERS.md、本文件和 Git 状态。
2. 工作目录始终为 E:/项目_手动重构；不在 C 盘工作区写实现，不使用子智能体。
3. core 是包目录，不是 core.py；按 D013，Agent 属于 domain/agent 节点包，内置业务模块为工具发现/上下文组装器；其他模块属于应用项目，每个模块及其辅助组件归入独立目录。
4. 原项目是逻辑依据；禁止通过新写简化应用、旧运行后门或修改断言掩盖失败。
5. 真实模型读取本项目 .env 的 DeepSeek 配置；不输出密钥。
6. 旧实现适配新设计；直接 for/list 使用 Tools，access 完成可达性判断后不反复检查；确有核心冲突再讨论。
7. 更新文件清单与阶段证据，未通过三应用验收不能报告全量迁移完成。

## 并行编辑记录

结构整理提交之后，工作区 DataNode.save_data 的默认值由 False 改为 True。该编辑已保留，未覆盖、未暂存到迁移文档提交。
CORE_BASELINE.json 描述的是结构整理时与基线一致的状态；当前默认值变化应在后续验证时单独对齐，不能再声称工作区所有基础定义仍与旧基线相同。

## 当前 Python 环境

- 运行与向量验证：`.venv-runtime/Scripts/python.exe`，Python 3.11.16，复用 E:/miniconda3/envs/ml 已有科学库；额外依赖只安装在本项目环境中。
- 基础开发环境 `.venv` 为 Python 3.14，当前向量依赖没有装在其中；后续默认使用 `.venv-runtime`，不要回到共享环境安装包。
- 项目模型：build/models/bge-small-zh-v1.5，从原项目已有模型复制。模型、缓存、测试日志和环境目录不入 Git。
- 向量工作进程现在显式使用 UTF-8，先 EOF 正常退出再升级终止；已验证中文路径和关闭后日志句柄释放。
