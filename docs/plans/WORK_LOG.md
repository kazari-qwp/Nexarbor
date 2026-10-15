# 实施工作记录

主规划：COMPONENTS_AND_KNOWLEDGE_BASE.md。

## 当前状态

- 起点：main 工作树干净，基于 v0.4.0 后的仓库。
- 两批规划已保存，组件拆分与知识库主体已实现。
- 当前状态：组件拆分与知识库源码实现、必要验证和交付文档已完成；待用户决定提交、发布与真实模型验收安排。

## 待办

- [x] 组件目录、依赖闭包与装配实现
- [x] 第一应用基础组件拆分、依赖完善
- [x] Python/Harness/构建入口统一组件装配
- [x] 第一应用必要回归
- [x] 知识库数据与节点、目录和读取
- [x] 归档与检索 Agent 接入
- [x] 混合资料、恢复、性能和权限测试
- [x] 用户文档与 Agent 文档检查清单

## 约束与决定

- 仅修改 E:/DataNet-模块化成品。
- 用户本轮授权实施；未要求发布新安装包或 push，不自动发布。
- 核心仅承担通用组件机制；业务留在扩展能力。
- 不使用子 Agent（当前指令要求明确授权才可委派）。

## 第一阶段实现进度

- 增加标准库 component_catalog：多来源目录、选择清单、依赖闭包、确定性排序、版本约束、缺失/循环/重复冲突。
- 共享组件已从 multi_agent 移至 foundation 与 storage；工具绑定拆到各工具箱自己的 bindings.json，无源码复制。
- Agent 挂载、执行和私人记忆桥接提取 agent_runtime，知识库无需网络管理即可复用。
- Harness 原生扩展路径来自 Python 已解析目录；构建脚本扫描所有分发组件。
- 依赖加载与 baseline 工具授权解开：第一应用显式配置 baselineToolboxes，其他应用不继承。
- 5 项应用测试与 4 项新依赖/独立加载测试通过。完整测试首轮发现局部 manager 引用未更新（已修）和停用节点恢复（已实现 DormantNode 保留记录）。
- Windows 沙箱临时目录/子进程干扰测试，使用 build/test-temp 并在授权上下文执行 Git/后台进程回归。当前日志 build/component-refactor-tests3.log。
- 下一步：完成剩余回归和组件文档，再实现知识库。不要将中途失败误报为最终通过。

第一阶段最终回归：build/component-refactor-tests4.log，95 项，94 通过、1 打包二进制测试按配置跳过；最小协作单项另通过。开始第二阶段知识库。

## 第二阶段中途记录

- knowledge_base 已实现固定拓扑、两个按需 Agent、自动归档、结构化路由复用、CSV/SQLite/RAG/Wiki 节点、统一读写与检索、更新/删除/版本/来源/混合批次。
- 8 项知识库离线测试通过（含两应用共存无工具授权泄漏、混合归档、SQLite 聚合与中断恢复）。
- 真实原生 Harness 两项测试通过：modular_shared_runtime_test.cjs、modular_cooperation_test.cjs。模拟生成模型，不调用付费 API。
- RAG 直接复用 LlamaIndex，已在本目录 .venv 安装 llama-index-core 0.14.25 与 HuggingFace embedding 0.8.0；build/models/bge-small-zh-v1.5 是忽略的测试模型。
- 真实本地中文嵌入、更新、删除和恢复测试通过：冷加载/两份导入合计 26.384s，热查询中位 12.36ms，5 次样本（CPU 2 线程，小样本，不能泛化为大库性能）。metrics: build/knowledge-semantic-metrics.json。
- Wiki 新增复用 MkDocs 的 markdown_wiki 基础组件，待实际导出测试；不要误称 MkDocs 本身实现 Agent 知识维护。
- 用户强调任意扩展功能都优先复用现有实现：下一步应收敛自研业务逻辑、整理通用能力边界，不扩张定制 Wiki 引擎。
- 最新额度检查：五小时剩余 23%，周剩余 88%；后续低于 8% 立即暂停，不重置。
- 待完成：MkDocs 测试、知识库原生桥接测试、最终回归、依赖/架构/使用/Agent 审阅文档、性能最小基线、构建检查与工作树检查。尚未 commit/push/发布。

最新补充：
- 原生知识库桥接测试 native_knowledge_base_test.cjs 已通过：真实 Harness AgentLoop + 模拟生成模型完成归档、直接读取、路由复用、两个固定 Agent 及只读权限。
- 独立 MkDocs 组件已接到 Wiki 导出，正在跑 9 项知识库测试。
- 用户进一步强调任何扩展模块可复用已有实现，只有核心框架为自研。后续不要扩张自定义 Wiki/索引引擎，优先成熟上游和薄适配。

## 收尾状态（2026-10-15）

- 知识库数据、节点、目录、读写、固定归档/检索 Agent 和两个应用共存已实现。
- 实际 MkDocs 页面与搜索构建、原生 Harness 知识库桥接、本地中文嵌入更新/删除/重启已验证。
- 最新性能：1000 条 SQLite 批量写入 7.448s；20 次直接过滤 p50 1.753ms，按 ID 读取 p50 1.377ms。详细范围见 docs/VALIDATION_COMPONENT_KNOWLEDGE.md。
- 最终依赖清单修正：根网络所配置工具箱、讨论与协作预设显式声明依赖；预设停用同步从服务目录移除；新增重复工具箱/角色/工具定义检查。
- 组件解析 5 项通过；最终调整后全量回归正在运行，日志 build/components-knowledge-regression-final.log；进程会话 93098。
- 文档：docs/COMPONENTS.md、COMPONENT_MAP.md、THIRD_PARTY_COMPONENTS.md、applications/knowledge_base/README.md、KNOWLEDGE_AGENT_REVIEW.md、VALIDATION_COMPONENT_KNOWLEDGE.md。
- 尚未 commit、push 或重打包。没有启动/关闭用户客户端，没有付费生成 API 调用。
- 后续：收集最后回归结果；如失败，仅修相关回归。确认组件目录和 Agent 审阅文档后收尾。五小时额度低于 8% 立即暂停，不使用重置卡。

## 额度暂停存档

五小时额度剩余 7%，遵照用户低于 8% 即暂停的要求停止工作，不使用重置卡。

最终全量回归已经完成：106 项，104 通过、2 跳过，140.432s。git diff --check 通过。构建脚本已改为发现所有组件，但未重建二进制。

主体实现及文档已落盘；当前未 commit/push。收尾时最后一次重新执行 native_knowledge_base_test.cjs 的进程退出 0、输出为空，未将此空输出单独算作新增通过证据；之前有明确成功输出的原生知识库测试已通过。

恢复入口：先读主规划与本日志，再检查 docs/KNOWLEDGE_AGENT_REVIEW.md 和最终 Git 差异。无需重复全量回归；如没有新修改，整理交付即可。组件映射 96 个组件已重新生成。所有业务实现仍在扩展能力组件中。

## 恢复开发与完成（2026-10-15）

- 用户决定继续维护自己的核心并恢复第二应用开发；不迁移到 Jac，也不开始 NPC 应用。
- 开始时五小时额度剩余 89%；保留低于 8% 即暂停的约束，不使用重置卡。
- 上次的 106 项全量结果已核实：104 通过、2 跳过，不重复执行。
- 找到并修复文件入口遗漏：kb_ingest 的相对路径按应用工作区解析，保留 resolve 后的范围限制。新增最小用例先复现失败，修复后通过，覆盖 CSV 类型、前导零、直接导入和相对/绝对路径越界拒绝。
- 原生 Harness 测试以 subprocess 捕获明确 PASS 和退出码，解决之前空输出无法判定的问题。进一步改为加载真正的 knowledge-base 插件入口及其默认装配，测试通过：build/native-knowledge-entry.log。
- 模型采用模拟响应；本机当前没有 DEEPSEEK_API_KEY 测试凭据，没有执行真实生成模型付费测试。此前本地真实嵌入和 MkDocs 测试结果仍有效。
- 主体与必要验证已完成。未新建业务循环，未改动核心来修复文件入口；修复在知识库能力组件内。
- Agent 文档仅补充 USAGE.md 的相对路径说明，工具描述原文未变；审阅入口 docs/KNOWLEDGE_AGENT_REVIEW.md。
- README 及四份说明此前已提交并推送 e9a8477；组件拆分与知识库实现代码仍在本地未提交。此次未发布安装包、未修改用户客户端。

## 单主 Agent 与受限助手完成（2026-10-15）

- 本轮设计存于 KNOWLEDGE_HELPERS.md；合并固定检索/归档角色，根即主 Agent，默认独立工作，助手最多一层。
- foundation 新增通用 task_documents、scoped_workers；复用现有 AgentNode、agent_runtime、agent_messaging、普通文本节点和检查点。助手可选 components，默认继承可授予业务权限；没有递归创建能力。
- 知识库用 topology.json 配置 csv/sqlite/rag/wiki 映射。服务检查业务写入类型及图的实际读写可达性；只读任务拒绝修改知识记录。新集合不恢复已被撤销的助手连接。
- 原始任务/原始资料引用、独立成果文档、证据版本及本任务实际写入回执，均持久化。send 唤醒/一次性回复复用既有机制。
- llm-wiki 固定 cd5466678341885fa29ca9e27fa9604c2e9c11c5，复用原版 ingest/query/lint 指南及 BM25/链接图算法，Apache-2.0、原文件哈希保留。现有记录系统仍负责跨类型来源与版本，MkDocs 仍负责站点，不引入上游云服务或新模型循环。
- 核心只修复 serialization 对未加载的可选替换 codec 的误判：普通核心文本可恢复；真正依赖已停用扩展的文本仍休眠。新业务代码均在 capabilities。
- 21 项定向回归通过；最后四项助手测试通过（含父模型、思考与 50k 输出参数继承）；真实 Harness + 模拟生成模型通过消息唤醒、文档交付、权限拒绝。没有付费生成调用，没有重新打包、commit 或 push。
- 所有 Agent 文档与新增/修改描述原文集中在 docs/KNOWLEDGE_AGENT_REVIEW.md；应用说明与组件映射已更新。

## 实际读写资料准备（2026-10-15）

- 用户要求先找资料，稍后再实际测试。本轮只采集、整理并校验材料，没有调用知识库、启动客户端或付费模型。
- 目录：build/knowledge-readwrite-20261015。README.md 为资料清单；workspace 是后续客户端工作区；updates 与 evaluator 在工作区外。
- 13 篇 SQLite/USGS 官方技术文档，约 214959 字符；14 条 CSV 来源目录；USGS 2024-09、震级至少 4.5 的冻结查询返回 481 条观测，首批 JSON 300 条、增量 CSV 181 条。
- 明确标注的虚构 QuakeDesk 项目要求 v1/v2，包含 SQLite 版本、缓存保留期和待评估的部署变更。用于来源版本、Wiki 修订及缺失信息测试，不冒充公开来源。
- 保存原始网页/API CSV、URL、SHA256、逐字节重复文档、独立统计和抽查值；结构、前导零、事件唯一性与来源文件哈希已校验。更新与答案没有提供给 Agent。
- 读写验收为 evaluator/acceptance-plan.md 草案，用户尚未要求现在开测。没有更改应用代码或工具描述。

## 真实 Harness 端到端启动（2026-10-15）

- 用户明确授权现在测试。独立客户端目录 build/knowledge-e2e-20261015-r1，使用 high thinking、500k 上下文、50k 输出，拟总限时 30 分钟。
- 启动前修复批量导入导致切换任务、既有助手失去后续 intake 读取权限的问题。kb_ingest 追加到当前非只读任务；kb_task 仍显式建立新任务。两项最小测试通过，未修改 Agent 文案。
- 测试插件最初通过 junction 引用产品源码，循环导入失败；改为测试目录正常插件布局并重启后循环激活。补齐安装目录 Python 核心后 session/create 成功。
- 原生会话 session-22d8f579-8ff3-494c-9a33-fa3de25ad22a；本地服务 127.0.0.1:54614。当前客户端 PID 52948（以后操作前重新核对 client-process.json 与独立 user-data-dir），用户其他客户端未改动。
- 首次 prompt 失败：MISSING_CREDENTIAL，deepseek-official 路由缺 API key；没有成功模型响应，不能算归档完成或有效端到端结果。已停止自动阶段驱动，test-status.json 标记 blocked_authentication。
- 自动审批明确拒绝从其他本地凭据文件探测可复用认证材料，不得绕过。已请用户直接在本次客户端模型设置配置 API key，不要在聊天提供密钥；等待配置后重启测试计时。
- run_phases.py 为预定五阶段驱动草案，后续继续前需增加“模型/认证错误立即停止”的硬检查，避免把空闲错误态当作阶段完成。后续阶段尚无有效测试结果。
- 最后额度五小时剩余约 16%；遵守低于 8% 暂停，不用重置卡。


## 2026-10-15 实际 Harness 读写测试暂停（5小时剩余7%）
用户已在隔离客户端登录。已将测试profile modelRoute切换deepseek-account，不读取/复制任何其他凭据。有效会话session-3d6151fd-a6b6-4bba-a973-9b2431fbd6bb，工作区build/knowledge-e2e-20261015-r1/workspace-valid，meta.json存计时，前四阶段已跑完。第一阶段落盘：CSV14、SQLite300、RAG13、Wiki9。增量与查询阶段尚未独立验收，不可声称全部通过。
第五阶段真实客户端重启后恢复失败：datanet/request-tail seq12 unknown and not ignorable；runner-valid.stderr.log、runner-error.json记录完整错误。runner已异常退出，无模型继续运行。测试客户端保留供用户查看，只操作client-process.json所指且命令行匹配本次desktop-user-data的进程。
待查：adapters/harness/runtime/session-events.js包装persistence.create/open，将扩展事件设ignorable；agent-loop/lib/index.js constructor1562调用，createStoredSession1830和resume1932后来才取sessionPersistence，可能是服务尚未可用导致安装早退，需验证实际服务加载时序/副本。不应只修改历史日志掩盖恢复问题；修复后最小化覆盖延迟加载路径，再真实重跑。tests/native_session_restore_test.cjs当前只覆盖服务已加载后主动install，可能漏掉此条件。
登录前失效记录已放authentication-failed。有效阶段快照phase-1至4-stored-records.json和client-records.json等在测试base；恢复阶段RPC失败，没有第五阶段结果。未修改任何agent文档/描述。额度刷新后继续，禁止使用重置卡。


## 2026-10-15 真实知识库验收完成

持续修复后，干净 r2 的五阶段存储/查询/增量/只读/客户端重启约11分20秒完成；另完成单助手带文档协作，真实RAG维护验证约83秒，15文档168片段，中文命中 SQLite 网络访问/WAL 和 JSONB 官方原文。74项独立数据和日志检查通过，最终9项Python最小测试、4项原生Harness回归通过，所有会话已空闲。

修复：实际persistence handle.append及enqueueLive都标记自定义事件ignorable；Wiki YAML标量规范；LlamaIndex fsspec Windows extended路径；组件启动在主线程预载完整HuggingFace依赖（只SciPy不够）；local_files_only；非RAG不伪称语义命中；locator和aggregate.field指南及错误反馈。无新增核心业务耦合。临时诊断wrapper已从测试profile移除，保留堆栈证据。

报告 docs/applications/knowledge_base/TEST_REPORT_20261015.md；Agent指南改动清单与原文 docs/KNOWLEDGE_AGENT_REVIEW.md。本次未commit/push。保留原始认证失败和工程中断记录，不把有问题的会话冒充完整无故障重跑。
