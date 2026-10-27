# 当前进度与恢复入口

更新时间：2026-10-27。

当前最新验证：**397 项全量 Python 测试通过**；真实小镇一天及保存重开通过。用户已接受性能差异并明确恢复迁移：继续讨论/协作、资料库、完整宿主/前端与制作 Agent 文档更新，后续验收仍监测 token 与时间。离线分析确认主要内容增量是模型推理，可见文字平均每次约 47→48 字符；不再继续做本次性能对照实验。


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

- 位置/移动/转交：place.info、movement.here、records.transfer 已迁为新 Module；AnnotatedLink 继承基础连接，保存应用属性，不修改 core。11 项专项覆盖移动三节点回滚、钩子锁范围、双向位置边、原始/直接调用者、同地点转交、AP 合并扣减、并发回执和日志重开。全量 305 项通过，证据见 evidence/2026-10-27-town-movement-transfer.json。

- 服务/商店/协议/场景：service.actions、shop.market、agreements.pair、places.query 已迁为新 Module；6 个服务纯算法与原 AST 一致，地图 PNG 渲染文件原样保留。11 项业务和 6 项场景测试覆盖事件上限、后钩子/双方记账回滚、到访版本/双方同意、公开人物范围和实际图片生成；全量 322 项通过。恢复工厂使用动态宿主事务端口，不能捕获已关闭/替换 Backend 的 NodeLocks。见 evidence/2026-10-27-town-business-scene.json。

- 家庭/出生：family.household、family.birth 已按新 Module/access 实现，8 项专项覆盖双方同意、怀孕起始时间/上下文、两阶段收费待办、模板失败与原键重试、双方家长引用及日志重开。全量 330 项通过。测试的模板端口是故障可控夹具，不能算真实模板服务或新生儿网络验收，后者仍待迁移。见 evidence/2026-10-27-town-family.json。

- 真实小镇项目：原 59 节点转为 52 个新节点；7 个工具发现器按 D009 放回 Agent，仅删除确认无引用的 7 个空工具亚节点，通信亚节点有引用而保留。33 份真实数据文件、2 个原固定模板和全部业务模块已装配。实际模板创建、参数/节点 ID/工具名称重映射、回滚与冷重开验证通过。Backend 支持新格式 initial_document，原生 RPC 可启动 TownProject。
- 原执行器每步刷新工具表行为已补齐，仍直接使用 Tools 和已取得的工具引用，不重复检查可达性。完整回归 337 项；真实 DSH 本机模型桥再次通过；真实 API 小镇 5 tick 完成，344 次请求（含重开续跑 2 次）。见 evidence/2026-10-27-town-project.json。
- 性能门槛：用户要求三个应用关注 token 和时间，明显差异时停止汇报。本轮已完成暂停、汇报和离线对照，用户接受差异并明确恢复迁移；见 PERFORMANCE_REVIEW.md、evidence/2026-10-27-town-performance.json 和 output-analysis.json。后续应用继续监测。

## 尚未完成

- 原项目业务模块、完整项目/信号宿主和前端尚未完成迁移。上下文组装器已完成模块级迁移，执行器 prepare/ACK 等模块级行为已迁入，真实宿主/RPC/锁/检查点已接通；完整 Studio 和项目组件接线仍待迁移。
- 小镇一天完整实际运行已通过；讨论与资料库两个应用尚未完成最终验收。临时 API 演示不是这两个应用的验收。
- 每个旧文件的语义审查、去留理由和迁移证据需继续记录在 FILE_INVENTORY.csv。

## 下一步

用户已解除性能暂停并要求继续迁移。当前处理讨论/协作应用，notes.text、discussion.seat、collab.participant 已完成组件迁移，discussion.session 和 collab.board 已完成组件迁移；接下来完成 git.integrator 与 app.coordinator.entry；模块只能通过 access 跨节点访问，信号使用独立运行器。之后迁实际资料库 catalog/tasks、完整 Studio/前端、复制/资源/宿主服务，最后更新制作 Agent 的 Skill/提示词。两个应用验收继续记录 token、API 次数和耗时。

讨论基础模块：notes.text、discussion.seat、collab.participant 已迁为新 Module/access；9 项专项和全量 346 项通过（30.972 秒）。覆盖真实文件部分写入回滚、并发追加、回执冷重开、角色发布、成员身份与候选委派。完整讨论状态机/实际 Git 整合与应用验收尚未完成。用户 domain/core/data_node.py 的 save_data=True 编辑继续保留且未暂存。scripts/analyze_town_output.cjs 是本轮离线诊断脚本，不打印推理文本，未调用 API。

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


## 讨论会话与协作板阶段

discussion.session.rev_697d80a33d 和 collab.board.rev_9191e2380f.rev_96569f0263 已迁为新 Module/access。新增 23 项专项通过，全量 369 项通过（32.894 秒）。原轮次/角色/成果/回执、路径冲突/成员退出/共享记录、短事务提交后发信号和失败报告保留；验证了跨事务状态写入限制。原配置的成员发现采用 access，不保留 ctx。未调用付费 API。

Git 整合器与应用协调器已经迁移并验证；原 SDK 工具宿主已分别在配置所选 0.2.1-rc.2 和默认安装 0.2.0-rc.2 验证。实际讨论项目的 15 节点配置装配与真实 Agent 验收仍未完成。


## Git 整合与应用编排阶段

- 新 GitIntegratorModule 保留原候选、成员分支、merge-tree/commit-tree、投票、退出、否决重开及 update-ref CAS；统一上下文参数和本节点 ID 表达后，39 个函数 AST 与源实现相同，仅配置/成员发现/终端入口 3 个函数适配新接口。终端直接迭代本节点 Tools 并调用实际工具引用，不经过别名目录、旧 invoke 或可达性复查。
- 9 项真实 Git/原生 SDK 终端测试通过（104.625 秒），包括保存重开、冲突保护、全票发布、外部改分支拒绝覆盖、busy 租约。测试仓库全在 E 盘 build，模型/API 调用 0。
- AppCoordinatorModule 已迁移；8 项专项通过（17.943 秒）。真实讨论/协作/成员入口/Git 模块共同完成手动驱动的讨论→交接→候选→否决重开→全员投票→发布→冷重开；不代表真实模型或原 15 节点应用已验收。保留部分 status/stop 报告，不再用旧 ComponentResult 包裹内部模块调用。
- 此阶段全量 386 项 Python 回归通过（154.364 秒），日志 build/discussion-git-full-regression.log。另 3 项应用差异专项通过：原讨论应用的活动续接提示词、消息 record_channels 与扣费回滚，不能直接套小镇差异配置。当前累计验证 389 项，但最后单次全量是 386 项。
- 原 OfficialToolsRunner 已迁入 adapt/harness/official；scripts/verify_native_official.py 验证配置所选及默认安装两版本各 10 个工具、返回契约和真实命令。兼容探测按实际插件依赖要求 workingDirectory，不把 app.asar 的虚拟包目录当普通目录检查。配置所选程序为 E:/dsh/Harness/DeepSeek Harness.exe；默认安装为 LOCALAPPDATA/Programs/DeepSeek Harness/DeepSeek Harness.exe。

下一步：迁移实际 discussion-collaboration 项目配置与 12 份资源，装配 15 个节点、宿主工具和原生执行器。旧配置 terminal_ref=harness:pwsh 须转为本节点真正的 CallableTool.name；多节点公开同款 SDK 工具可沿用原 ext_ + sha256(node_id + NUL + ref)[:24] 作为工具本身的名称，直接引用调用，不恢复旧 alias/catalog。接通后按原应用流程验收并监控真实 token/耗时。随后仍有资料库 catalog/tasks、完整 Studio/前端、资源/复制服务和制作 Agent 文档。


## 实际讨论项目装配 WIP

15 节点、10 Agent、31 个宿主工具和 12 份原文档已转换并能实际装载/冷重开。共用配置加载器已提取到 app/projects，原小镇 6 项模板/项目测试仍通过。生产 RPC 下 discover 声明预览、真实官方终端、便笺追加、Markdown 上下文和冷重开通过（无模型请求），原生模型桥再次通过。5 项运行端口边界测试通过。完整回归 397 项通过（154.638 秒），原生桥/实际项目 RPC 已通过；真实模型验收入口已准备，尚未运行。用户核心默认值编辑仍保留。下一步与原脚本差异说明见 DISCUSSION_ACCEPTANCE.md；真实模型讨论验收尚未运行。


实际讨论项目阶段：scripts/migrate_discussion_project.py 已转换完整 15 节点、12 文档和 31 宿主工具；应用层共用 Project 加载器、HostTools 工厂及原 runtime_ports 已接入。模块和工具恢复仍直接重建已有表，不检查依赖或重复判断可达性。只在 RPC 展示边界编码 Tools 的工具声明，核心对象及 discover() 不变；发现器 module.json 删除旧 collect/invoke/routes 声明，改为 discover。生产宿主可选择 discussion_collaboration。全量 397 项通过；付费 API 调用仍为 0。已准备 scripts/verify_native_discussion.py 和 native_discussion_acceptance.mjs；当前下一步是在确认代码检查后执行真实 API 验收，按 DISCUSSION_ACCEPTANCE.md 记录每阶段 usage/时间，遇到实际核心冲突停下讨论。


## 当前需用户决定：原 submit 请求键矛盾（B008）

已执行真实 API：讨论阶段完成，79 次请求、134.963 秒，输入 1,317,106、输出 45,176（总数含缓存读）；随后进入真实四成员协作，模型实际编写、测试并提交了部分成果。发现 participant.submit 的 key 契约冲突后停止 API 代理，运行中所有本次子进程均已退出。共开始 142 次请求，其中 140 次取得完整 usage；已观测输入 2,065,706、输出 65,227、合计 2,130,933，另 2 次中止请求没有完整 usage，不能称为最终总量。运行 build/native-discussion-newcore-4mg660xk，证据 evidence/2026-10-27-discussion-api-stopped.json。

原 collab.participant 的 Schema 允许 key，源码会把它原样传下游；原 Git submit Schema 不允许 key，旧 NodeModule 调用也会按该 Schema 校验。这是旧项目已有矛盾，并非已确认的新核心限制。按用户“不擅自改变原逻辑”的要求已通过异步问题请求决定。最小提案在 build/participant-submit-key-proposal.patch，尚未应用：仅成员入口不再向 Git 转交 key，仍使用原有 commit 幂等，不添加新业务规则。

等待此决定时可以继续资料库等不依赖该改动的离线迁移；不得自动重跑或继续付费讨论测试。若获准修复，先补回归。尽量保留已有真实仓库、会话和成果进行显式续跑；不能改状态强迫成功或自动重放 interrupted 信号，须使用原恢复/显式触发能力。完整三应用仍未验收完成。

资料库已读 projects/knowledge-archive/modules/knowledge.catalog/AGENTS.md（使用/查询/版本/来源规则），并逐段读取 documents.tasks、knowledge.tools、context.network、knowledge.catalog 的 module.py。当前 catalog 的 Historical KnowledgeStore 720 行，与先前五类新 DataNode 所用的其他 store 不是同一业务引擎，禁止直接换引擎。下一步审查该 store、自有 workspace/tasks/knowledge 资源的快照与事务边界，再按原逻辑迁移。


## 当前进展：D016 已获准并实现

用户明确批准仅在 participant.submit 转交时消费 key，保留 Git 的 commit 幂等，并要求后续业务逻辑改动继续先确认。修复及两项回归已实现：基础模块 10 项通过（1.408 秒），新增真实 Git/官方 SDK 专项 1 项通过（9.108 秒），证明相同 commit 返回重复、新 commit 即使沿用同一 key 仍可提交。最近单次全量仍为 397 项；新增两项尚未合入单次全量统计。证据 evidence/2026-10-27-participant-submit-key-fix.json。

中断运行只读恢复核对：日志校验到提交 258，存在两条未确认 executor_invoke；4 个任务由 3 位成员完成，另一个成员在任何工具执行前遇到上游 502，两个活动仍为 running。原活动状态机拒绝重放失败/运行中的活动，不能为验收篡改状态、补造提交或自动重放信号。因此保留 build/native-discussion-newcore-4mg660xk 的仓库、会话和证据，修复提交后用全新运行目录重新完成实际讨论应用验收。不对旧运行调用 reconcile 来假定未知效果已经处理。


## 当前 API 暂停：验收任务活动阶段互等

D016 修复已提交 9d825dd。新运行 build/native-discussion-newcore-6d98yuxv：讨论 81 请求、123.734 秒、输入 1,485,247、输出 45,752；4 位执行成员各完成一项任务并提交真实 Git commit，确认修复生效。随后成员在本次工作活动内反复等待候选，宿主却等待活动结束后才 integrate，构成验收驱动互等。按用户异常耗时/消耗先停要求，已核验并停止唯一验收主进程，保留仓库/会话/日志，不篡改状态。完整数字见 evidence/2026-10-27-discussion-activity-wait.json。

原业务协调器使用独立 collaboration.review 信号，活动状态机拒绝重叠活动；不应让宿主在旧活动运行时强行进入新验收信号。已准备纯测试输入修正：任务明确 complete+submit 后立即结束本活动、不轮询不 sleep，独立 review 信号到达后再验收并结束。未改任何业务提示词、模块、核心或断言。后续付费重跑等用户答复，期间继续资料库离线迁移。


## 当前任务恢复：D017 模块级旧协作协议；D018 资料库结构

用户批准继续，按 D017 恢复正确旧 propose/approve/reject/自动交付协议，只改模块及必要配置/验收接线，核心与通用执行器不动。真实 API 先等新协议离线及原生宿主验证通过，不再使用仅提示词结束活动的修补。D018：资料库 RAG 作为 Wiki 检索目录，返回链接，Agent 可直达 Wiki/数据库/其他信息节点。

历史资料库存储 WIP：projects/knowledge_archive/modules/knowledge_catalog/store.py 的 721 行由实际项目 720 行源码迁入，仅 CSV/SQLite/LlamaIndex 构造器改成现有 Dataer、文件原子替换及导航 import 改新路径；7 项真实文件/SQLite 专项通过（1.089 秒）。catalog module.py 为待接线 WIP，尚未应用验收；完整资料库协议和 D018 尚未完成。


## 新增约束与当前模块实现检查点

D019/D020 为最新完整验收依据：冲突分支可跳过，继续独立工作；前端阶段按原文档及真实旧客户端逐项比对书签/跳转等，真实客户端截图且不用 Computer Use；网络与组件两个制作 Agent 的工具、按需 Skill、所有文档都要可用，只更新过时内容；新小镇内置作学习范例。右键小镇节点咨询网络 Agent，真实工具查看后正确介绍是明确验收。三应用分别为五天小镇、根→管理员→两预设动态组装→CSV 转 JSON 的原测试、资料库原六阶段测试；不能继续把之前简化验收当最终目标。

D017 当前 WIP：cooperative_group 的原 claim/note/finish/member_exit 规则及 Workspace 原源码、快照材料、全员交付、通知、控制 conclude 已实现；cooperative_member 有继续/批准等待/否决唤醒模块循环。9 项真实 Git/文件协议专项通过（13.458 秒），未调用 API。正在把实际讨论项目的模块接线更新为该协议，新增交付/记录两个 Markdown 节点，当前 17 节点；此固定项目只是应用装配验证，尚未实现 D020 的根/管理员/动态预设全流程，不能付费跑替代任务。原测试/前端/文档清单继续定位。

注意：app_coordinator、runtime、17 节点配置与新模块均有未提交 WIP，尚需接线/循环/原生 conclude 验证；旧 tests/test_discussion_project.py 仍按 15 节点和 GitIntegrator 检查，待按 D017 改为检查新增交付节点和真实协议。保留 domain/core/data_node.py 用户编辑，不纳入迁移提交。原生适配器已经有控制结果支持，无需改 core 或 adapt。


## 网络中断恢复检查点：415 回归、原生协作收尾已通过

最近单次全量 415 项通过（188.106 秒，build/cooperative-full-regression.log），包括新协议 9 项与历史 catalog 7 项。实际项目 3 项通过；原协调器 8 项通过（18.798 秒）。真实 Harness SDK/原生 JSONL 集成 build/native-cooperative-iivg6a8b 通过：4 名成员工具都返回 conclude=true、全票、交付文件和归档；12 次本地 HTTP 模型夹具请求，包括结束通知后的简短回复，付费 API=0。测试入口 tests/cooperative_rpc_fixture.py 仅为实际项目指定 root 调用身份，其余执行/工具/事务/SDK 均走现有路径；不把本地回复当真实模型验收。现阶段 core 与 adapt 均未修改，DataNode 用户默认值编辑保留。

D017 仍有原同伴消息/一次性回复、终端日志、逐请求预算/全局期限等策略待迁，不宣称完整协作应用通过。新 17 节点配置仅用于组件装配；D020 最终原驱动已定位 scripts/prepare_root_hone_learning.mjs、run_learning_root_hone.mjs、grade_learning_hone.py：初始仅 root/administrator/workspace 三节点，真实模型委托组网，不预建团队；任务夹具来自 build/hone-fixed-20261014-r6/workspace/task，独立原测试为 7 单测+5验收+6CLI，原成功基线见 docs/evaluation/HONE_FIXED_RETEST.md（1617.418 秒，329 消息，未缓存 8044304、缓存 23292416、输出 546287）。最终比较应优先核对当前根委托版本的对应结果，不能把高推理旧固定组织直接当同条件基线。

D021 已记录六份演示与双击历史要求；旧演示确为六个独立目录，含可携带会话分块和 Git bundle，依据原 项目演示/README.md、scripts/package_release.py。前端清单见 FRONTEND_ACCEPTANCE.md；原文档已阅读，实际旧客户端对照留到前端阶段。网络中断恢复时未发现本任务付费测试进程，不重启已完成测试。


## 当前运行与并行分支

已提交 e6a0101：415 项回归与原生协作控制证据。五天小镇真实 API 验收已开始：build/native-town-newcore-9h_00tqg，exec session 40813，命令 scripts/verify_native_town.py --days 5；未完成前先读取该目录 verification.json 与该 session，不重复启动。沿用此前已通过一天的 API profile（maxTokens=10000/contextWindow=128000，未指定推理强度）；逐日 usage/耗时在新脚本记录，旧基线参数另列，不称严格同参数性能实验。保存 initial-state.json/final-state.json 为演示导出的原始依据。

B009 已提出适配层原请求事件的最小方案，批准前只跳过精确请求预算分支。继续消息/命令日志等无依赖工作；不拿 prepare 计数替代真实请求。


## 命令日志独立分支完成专项

原 command_logs 的四个记录/目录/筛选/查询方法及 record_values 原脱敏规则已迁入 cooperative_group 子组件；应用现有 official_port 返回时记录，不改 adapt/core。候选收集本成员、本次开始后的日志，log_ids 按原规则核对，复制源码/脚本/结果/日志到固定验收材料。项目协作工具表显式升级为 6 项（含 command_logs），不是加载时偷偷补表。4 项文件/分页/来源专项通过（1.131 秒），另实际官方 PowerShell 经新应用宿主端口记录并保留 executor-1 请求身份专项通过（0.899 秒），模型 API=0。最近单次全量仍为此前 415，不伪称本批单次全量已跑。

消息回执/一次性回复、精确请求预算等仍未完成；B009 等待宿主事件迁移边界答复时，继续资料库等独立分支。小镇五天运行 session40813 / native-town-newcore-9h_00tqg 正常：第1天302.307秒/323请求/input7340969/output136025；第2天224.105秒/215请求/input11858751/output90054。第一天与此前已接受的一天基线差异不大，继续其余天；原五天对应完整基线仍待归档核对。


## 2026-10-28 当前检查点：DSH 压缩补全，用户授权从第 16 时刻续跑

纠正旧状态：五天小镇 native-town-newcore-9h_00tqg 的 session40813 已失败退出，不再运行；第 17 时刻因临时 128k 配置和独立宿主未挂压缩服务失败，不能算完成。原独立宿主也漏挂，但当前已补接 DSH 官方计量/压缩/工具裁剪/图片卸载服务。旧默认 600k/50k 及原驱动 low/16k/20k 覆盖、60 秒流式空闲和 24 小时长操作均已审计；删掉新验收额外 3 分钟/40 分钟限制。

420 项全量回归通过（190.718 秒），两版实际 DSH 均通过压缩、超限恢复、取消、同会话重开，原生日志/锁位置及生产 RPC 通过，付费 0。用户明确不要重跑，按 D022 从断点继续。提交 1383 的稳定 tick16 与 7 个原生完成前缀已验证并恢复到 build/town-resume-7b_5az3v/runtime（恢复点 16c10846e7ac43f79e46ec831bad3b41）。下一步提交修复后，仅续跑 tick17–25；每 tick 显式完整检查点，保留失败尝试并分开消耗。详见 HARNESS_SESSION_AUDIT.md。

协作源审计修正：实际 项目演示/应用1-讨论协作-最终 使用 collaboration.group/member、git.workspace、execution.logs、groups.control、network.administrator，初始为两节点和 discussion/execution 两片段；较早三节点脚本属于另一引导版本。旧插件的单次回复/100 请求预算不是这份最终应用模块的依赖，B009 不阻塞最终演示源迁移。最终应迁移实际演示模块，不把当前 17 节点组件夹具当作完整 hone 验收。知识模块 WIP、制作 Agent、完整前端及六份演示仍未完成。

当前续跑目录更新为 build/town-resume-000c16ss/runtime，恢复点 a61415979f7549cdbc3d5a2adbc908d7。第一次恢复因未复制一个 DSH 附件对象而在请求前停止，付费请求 0；现已补复制整个附件库并逐文件哈希核对。旧失败目录保留，不续用其中的未完成第 17 时刻。

续跑当前目录更新：build/town-resume-y7_z7dk1/runtime，point=05188b9404ea4b5d813d185ff6ad9cac。前一个目录 7 次请求被 DeepSeek 以 developer 角色不支持的 422 拒绝，无 usage/无工具执行；现显式声明 API 路由不支持 developer，两版原生离线契约测试通过。仍只从原 tick16 断点继续。

小镇第 17 时刻已完成，56 请求，已持久化 point 0139c32c4f7a47989fa73d0a3f745584（commit103、pending为空）。脚本额外登记与自动登记碰撞已改为复用现有 NativeCheckpoints；两版原生验证再次通过。当前续跑仍用 town-resume-y7_z7dk1/runtime，下一时刻 18，不从 16 再恢复。

知识模块独立分支：documents.tasks、knowledge.tools、knowledge.collection 及 catalog 公开操作/Schema/原向导与 Wiki vendor 已迁移为新 Module/access。原始输入不可变、交付修订/作者、证据版本/回执、真实 CSV 原件保留/类型、只读保护及断线后不能直接读取真实记录，新增 4 项均通过；与原 catalog 7 项联合 11 项通过（5.174 秒），API=0。不是完整六阶段应用验收，也不宣称集合节点 DataNode 装配完成。B010 等待用户确认原文归档与 Wiki 目录关系；继续独立协作/制作 Agent/前端迁移。最近单次全量仍为 420 项（190.718 秒）。小镇续跑现已完成 tick18，执行 tick19，不能重启或重跑已完成波次。


## 2026-10-28 最新：五天小镇通过且已停止 API

当前没有小镇付费运行。build/town-resume-y7_z7dk1/runtime 完成 25 tick、保存冷重开、同会话续接及记忆读取；保留前16，从17续跑，17完成后协调器竞态停止一次再从18继续，没有重跑完成时刻。只读重建全部25完成状态并校验原提交链，976项业务检查全通过；7条实际原生日志 formal inputs无重复，usage与网关精确一致。五天1220请求、1398.573秒、输入91259448（缓存78820480）、输出548687、总91808135；含重开探针92087572，含原失败阶段已观测98005051，另7个422无usage。配置跨128k/10k→600k/16k/low，不宣称严格同比。完整证据 TOWN_FIVE_DAY_RESULT.md 与 evidence/2026-10-28-town-five-days.json。

实际最终应用1的 GitWorkspaceModule / ExecutionLogsModule 已按 项目演示 最终源迁入独立模块文件夹，Workspace 104行原样保留；4项真实Git、不可变候选源/结果、日志归属/分页和实际官方PowerShell证据专项通过（2.809秒），API0。尚未接入最终根/管理员与两片段，不能称完整应用1通过。下步继续迁移实际 discussion.group/member、collaboration.group/member、groups.control、network.administrator，并接通 Studio 管理端口；保留当前17节点夹具作组件测试，最终验收不能用它替代hone原任务。资料库B010仍等选择，不阻塞这些独立模块。完整前端、制作Agent工具/文档、内置小镇和六份可移植项目仍未完成。用户 domain/core/data_node.py 编辑保持，不暂存。最近全量420；其后知识联合11项与最终工作区4项为专项验证，不伪称已经全量428。


## 2026-10-28 制作 Agent 共用链路迁移检查点

用户最新要求：所有问题先跳过，只有剩余工作全部受阻才停工。继续优先制作 Agent 的工具、Skill、文档和管理员复用层，不调用子智能体。B010 仍只阻塞知识集合最终装配及其依赖验收。

已迁移四个 Skill 的33份资源并更新旧 ctx/v3/text_file/工具提供器机制；保留原文档结构与验收要求。新小镇复制为 resources/examples/npc-town，52节点、19模块（含2内置）、205边；只读查看、节点/模块/正文/源码、稳定编号及快照检查通过。两个实际 DSH 版本各18次本地夹具请求，两个制作角色均按需加载工具，并冷重开同一原生会话成功；付费0。这不是前端或真实模型咨询验收。

新 v4 ProjectModules 与 ModuleHarness/NetworkHarness 直接使用真实核心、独立信号运行器、NativeExecutor及检查点；7项专项通过。工作副本的原文件工具、只读资料、分页、编辑冲突、Git基线、独立验证进程、不可变发布已迁移；4项专项5.538秒通过，包括实际写组件测试→运行→发布→挂载→保存重开和真实当前图隔离测试。制作模板改用 Module 类；没有以旧核心执行任何制作产物。较早全量435项197.735秒通过，其后工作副本新增4项尚未计入新的单次全量。

尚未迁完：网络草稿批量命令/预设/重复组装、test_environment连续操作进程、Advisors/MakerManager完整RPC及运行中管理员范围、实际右键咨询/前端；当前 app/studio/service.py 仅已迁移部分接口，不能宣称两个制作Agent全部可用。继续这些独立分支，不等待知识问题。实际最终应用1六个模块仍为WIP，未改项目装配，不能拿旧17节点夹具替代根/管理员/hone验收。用户 domain/core/data_node.py 修改保留且不暂存。


制作网络第二检查点：新节点骨架、原 edit_network 短命令、v4 执行配置边界、网络/附加产物及模板校验已迁入 app/adapt；新装配由真实 Installer 生成工具表，完整序列化表直接恢复，不按更新的 manifest 重查依赖。原可重复单元算法迁到 app/studio/preset_repetition.py，改用统一 DataNode 路径和 links/tables，保留计数、共享入边、typed引用及独立数据复制，并重映射稳定工具名。5项网络专项3.765秒通过，随后与组件、夹具联合16项10.189秒通过（build/studio-network-combined-regression.log）；包含真实网络作者验证进程→候选调用→保存重开→发布。API0。全量仍为较早435项197.735秒，不把专项加成新全量。

发现根目录 context_assembler 清单已有 ui.html 但文件尚未迁；已迁原页面，仅把旧路由路径展示改为新 Markdown 文件地址，并同步内置案例。全部19模块清单校验通过。未改 core/ 中任何文件。

后续继续：test_environment 需复用真实持久 Backend 连续操作，默认 NetworkHarness 仍每用例独立克隆；准备将夹具初始化注册放到 Backend 冷恢复之前，并供交互测试进程复用。Advisors/MakerManager、预设磁盘/粘贴、管理员完整接线和真实前端仍待迁；实际最终应用1六模块WIP不激活。不能因B010未答复停工。


制作测试环境第三检查点：ModuleHarness/NetworkHarness 已改为先登记真实模块、节点及工具工厂再打开 Backend；作者用例默认独立克隆，交互测试进程显式复用同一 runtime/checkpoints.sqlite3。原 reset/mount/call/signal/inspect/snapshot、源码指纹、结果分页和超时边界已迁移；测试副本禁用真实模型及外部副作用，不用字典替代运行时。新增真实多进程专项6.803秒通过，状态2→5持续、源码变化必须reset、旧目录保留、正式图不变。联合18项17.334秒通过（build/studio-persistent-combined-regression.log）；上下文/检查点原有22项1.979秒通过（build/studio-context-persistence-regression.log）。付费0。仍未更新单次全量435的基线数字。

保存表工厂现在把明确的 channels/strength/channel_mode 交给 ContextAssembler 原构造器，防止新草稿装配丢掉设置；新增两层真实 Markdown 资料收集通过。通用检查点端口沿用原 TownModules 的 await wait_prepared 再 save，未改 core。下一步继续磁盘预设、复制粘贴与历史/书签资料、MakerManager/Advisors 和管理员RPC。应用1最终模块WIP保留；知识B010仍待选择但不阻塞其他工作。


## 2026-10-28 制作宿主与真实前端渲染检查点

451项单次全量Python回归通过，213.826秒（build/studio-host-full-regression.log），包含本轮Backend启动前配置、制作库检查点版本选择/冷重开、交互环境进程租约、真实新表复制与依赖装配。早先联合23项中的两个失败来自夹具把可编辑项目源码作为不可变标准发布登记，已改用实际project/v2资源映射扫描；两个业务断言保留，7项网络专项4.691秒通过后再跑上述全量。未改core，用户data_node.py默认值编辑仍不暂存。

MakerManager与Advisors控制器已迁入；Studio RPC接通原读写分类、修订、装配/卸载、数据/模块预览、图应用、脉冲与当前图观察。Studio在可选启用时先于图冷恢复登记模块，真实小镇52节点/19模块及Agent工具关闭重开专项通过。native_studio_advisors_integration.mjs使用真实原生DSH、控制器、Git咨询快照、Python stdio和当前核心，18次本地模型夹具请求通过：网络角色读取图/模块/文件，组件角色创建工作副本、写实际测试、运行验证，网络会话关闭重开后同session续接。记录build/native-studio-advisors-7hxcnpbs/verification.json；付费0，尚非真实API右键咨询验收。管理员局部范围与完整项目Git宿主仍待接通。

原frontends/network-editor与desktop源码及固定版本依赖已迁入，新产物输出build/network-editor；原项目只读。共享复制/预设/书签历史已使用新表，节点渲染摘要使用tables.modules与markdown。实际Electron图片观察器已接新路径，工具调用生成build/studio-renderer-nj6aj9k5/actual-town-network.png（8/52节点、43/205连线、159483字节）并目视核对，未使用Computer Use。这仅验收view_network图片入口；编辑器主体仍有旧modules/connections/参数字段、桌面项目入口/Host RPC/Skills/外部文本尚待适配，不可声称完整前端可用。

接着迁移完整前端的实际记录读写和项目宿主，随后真实右键咨询/工具使用；未完成应用1六个最终模块、知识集合B010及六份演示继续保留未完成状态。用户要求冲突先跳过，独立分支持续推进，不因未答复停止。


## 2026-10-28 前端记录、项目 Git 与原生工作区续接

新增项目宿主沿用原 Project.mjs 的 Git 分支、独立索引、Commit、咨询与原生前缀归档；改读写当前project/v2与project-network/v2，文本/二进制描述符均保留逻辑资源名。Python Project 同步支持v2文件描述符。实际小镇项目Git链路通过build/studio-project-git-f0cyo3qf/verification.json：52节点/19模块、真实制作分支、Skill导入/懒加载、消息归档，单独暂存personal.txt未被提交。新Python跨语言冷加载测试及制作/小镇联合16项17.760秒通过（build/studio-frontend-project-regression.log），后来工作区/RPC联合10项13.793秒通过。

原生制作角色再接入真实项目Git，build/native-studio-advisors-tkbxwfee/verification.json：18次本地HTTP夹具请求，两个角色、实际组件测试、同session冷续接、Git工作分支与可移植原生日志归档通过，付费0。不是最终真实API右键验收。

WorkspaceFiles与只读DSH log-host已迁入。上下文游标放在agents执行状态，不再写入节点；导出/导入完整原生事件和附件协议。两版实际DSH均通过导出→新目录导入→原消息逐条一致→继续运行，核心Markdown文件亦恢复，恢复门禁和pending均为空：build/native-workspace-zgns4ki7（4请求、20事件、6条历史消息）与build/native-workspace-020-wgjmgcm_（4请求、19事件、5条历史消息），均付费0。沿用原StudioTransport应用网络后返回最终commit编号的逻辑，避免前端继续编辑持有过期版本。

编辑器资源装配、模块配置、链接、Markdown路径、工具提供metadata和execution.skills已改直接操作新记录；复制放置等待真实异步工具名重映射，不再把复制结果送去补装依赖。保留已有组件状态/工具表/频道与强度；新记录专项3项通过，原模型选择约束2项通过，Vite构建通过。Skill解析与ModelConnections原实现已迁入。该版本仍为前端迁移中间态：原前端整套测试目前95项30通过65失败（build/frontend-original-suite.log），大多仍用旧记录、旧路径/同步paste，也包括未迁宿主或不兼容分支；不能用新3项宣称完整前端已通过。原桌面入口和startStudio Host尚未接通当前Python服务，尚不能交付正常桌面启动。

修正此前“studio_view无调用”判断：原main.jsx实际调用api('view')，原host转发studio_view；前端本地视角需要继续迁移，不能当无用接口删掉。旧路径详情、亚节点/借用出边、节点默认模块强度没有对应新核心概念，按用户要求先记录跳过相关分支，不改core、不恢复family权限；详见B011。独立数据预览/清空、项目宿主、其余前端和最终应用模块继续迁移。最近单次全量仍是451项213.826秒，之后只跑上述专项，不能把数字相加。


## 2026-10-28 通用工作台、数据入口与原桌面启动

通用 WorkbenchProject 已在 Backend 冷恢复前登记当前数据节点、v4模块及宿主工具工厂；实际原 desktop/main.cjs 启动该 Python 服务，读取 project/v2。HostTools 使用真实 CallableTool，模板端口直接交给原 TemplateService；端口声明及契约随检查点恢复，复制按真实表重映射工具名，不重装依赖。项目模块库变更同步实际模板目录。原模型连接、外部文本、HTTP编辑服务及原超时表接入；官方 DeepSeek API 明确登记原生 reasoning/消息协议能力，其他服务商不套用该配置。模型3项本地测试通过。

应用2五类 DataNode 现在各有实际 node_type，避免都序列化为 node。data.local/data.knowledge 的真实文件/SQLite/Wiki工具、只读及冷重开3项通过。操作员数据预览和清空按原接口迁移，使用隔离真实 Dataer 和原节点事务；包括CSV表头、SQLite结构、Wiki定义保留、正文及.bak的失败回滚。与原存储回归联合31项3.642秒通过，后来模板专项6项2.144秒通过。通用工作台/项目Git/RPC/数据联合14项13.559秒通过（build/studio-operator-combined-regression.log）；均API0。这些专项不等于新一轮全量。

实际HTTP宿主验证 build/studio-http-host-iofhb_to/verification.json：小镇52节点、21模块（19原案例+2数据模块）、4数据模板，实际Git分支/咨询快照/数据读取通过。原桌面入口截图及结果 build/desktop-current-71pznyi6/verification.json：52节点、属性与右键咨询窗口，pageerror为空；两条HTTP400已定位为B011待迁studio_view，不宣称无错误或完整前端通过。没有使用Computer Use。首次付费咨询验收的两个本地阻断尝试为UNSUPPORTED_REASONING_EFFORT，无HTTP模型请求/usage；验收脚本还修正了读取原UI sessionStorage令牌的方式。

当前正在运行 scripts/verify_desktop_consultation.py --live（build/desktop-consultation-0_gfr25r）；已通过真实API调用view_network、inspect_nodes/edges/modules，结束后再审计回答、usage和截图，未结束前不能宣布验收完成。五天小镇不重跑。原前端整套95项仍30通过65失败，需要继续迁移旧夹具和独立宿主分支；最终应用1六模块WIP、资料库B010、六份演示均未完成。最近单次Python全量仍451项213.826秒。冻结core无本轮编辑，用户data_node.py修改继续保持不暂存。


原桌面真实API咨询现已完成：build/desktop-consultation-0_gfr25r；52节点、205连线，12次模型响应，17次实际网络观察工具调用；最终回答核对角色、地点、模块、经济、时间/存档与四路上下文，明确是初始快照而非已运行结果。原生usage输入未缓存27161、缓存读取184448、输出8202、总219811；模型55.988秒，含桌面启动68.165秒。未找到同场景旧API基线，不宣称同比。关客户端后重新打开同一真实项目、右键小砾，历史回答保留；另存答案起止截图并目视核对，重开不调用API。证据evidence/2026-10-28-desktop-town-consultation.json。原stage截图显示对话开头而非答案，已补town-introduction-start/end.png；不重复付费运行。仍有B011两条视角HTTP400，完整前端仍未通过。

原发布库fork/delete与重复预设RPC也已迁入，当前表/锁、项目实际登记目录、运行/草稿删除保护、标准模块保护和失败文件回滚；真实制作验证→发布→副本→删除联合11项11.297秒通过（build/studio-release-rpc-regression.log），API0。现在运行新的单次完整Python回归，未结束前仍以前一451项为全量基线。


## 2026-10-28 当前单次全量与真实书签客户端

当前单次完整Python回归466项通过、239.252秒（build/workbench-current-full-regression-final.log）。此前465项那轮有2失败1错误，均来自加载器拒绝省略type的旧约定，已恢复缺省node、显式未知类型仍拒绝；下一轮466中的唯一错误为新增夹具缺少name，补齐后13项专项通过，再执行本次466完整通过。没有改断言去放宽业务行为。

原前端复制/资源22项、画布/数据7项、配置历史/网络预设9项、单节点预设4项、Skills/懒加载4项分别通过。这些是迁移原夹具到links/tables/data/元数据及异步paste，保留原业务断言；不把这些专项简单相加冒充全部前端已绿。原completeModules复制后补依赖已按用户决定移除；显式安装仍递归装配依赖，并保留现有配置/状态。

原bookmark-views.browser.mjs已真实客户端通过：build/bookmark-views-e2e-1793139781029/verification.json。包含3:1书签历史区、缩略图/文字切换、节点/边/网络/纯边历史拖入、取消无头连线、撤销重做、删除及草稿保存、侧栏自动展开/折叠与关闭重开、布局/运行区域，截图5张已目视核对02-text-view.png。模型调用0。真实渲染发现的bookmarks.jsx缩略图、use-bookmarks.js新增边历史、main.jsx连线属性/删除残留connections.interfaces已改为真实links。原脚本菜单定位“自定义快捷键”也落后于实际源客户端，改为源菜单“外部文本编辑器与快捷键”；未更改产品菜单。B011本地视角及其他前端分支仍未全部验收。

接下来继续实际最终应用1的管理员与分组模块，再做原hone CSV任务；当前六目录WIP尚未激活。B010知识集合仍只跳过有依赖的装配，其他分支持续推进。用户data_node.py改动保留，不暂存。
