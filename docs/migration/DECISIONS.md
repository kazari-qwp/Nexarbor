# 已确认的迁移决定

## D001：访问遇锁等待，回滚以节点为快照单位（2026-10-27）

用户明确提出：access 遍历到锁定节点时，等待解锁再执行。例如删除 A→B 前锁 A，删除后释放，随后到达 A 的访问按删除后的连接继续。

采用等待提交后的读取语义，不再要求其他事务在锁定期间读取旧路由快照。旧快照可见性的专项测试需要据此改为验证等待、提交后的读取、回滚后的读取；这项变化不授权修改其他应用规则。

节点是局部快照的单位。多节点事务必须收集参与节点快照、成组恢复并在恢复后统一释放。数据文件及 DSH 会话游标必须按原恢复协议纳入边界。

实现约束：等待和取得访问保护需要原子协调；本事务可重入；节点操作及连接/偏置/汇合策略读取不能绕过门禁。恢复原对象的状态，保留 Node/Module 身份、工具绑定和外部引用。

状态：方向已确认；访问门禁和事务迁移尚未实现。

### D001 实施进度（2026-10-27）

等待门禁已接入 access，保护目标节点汇合/偏置、处理函数及出边读取。保留广度推进、同层并发和整层屏障；黑名单频道在源节点推进时解析，回滚后可使用恢复的出边。Node/Network 只增加门禁绑定，安装/移除遵守事务生命周期约束；无额外路由授权或网络环路检查。

原锁协调器迁入 app/transactions，21 个协调方法 AST 与原实现一致。快照按节点保存 info、连接、模块状态/配置/发布数据、工具箱成员/声明、Agent 输入、执行状态/配置和真实资源，恢复保持对象/回调身份，不重装模块或检查依赖。模型等待让出访问，返回后重入；NodeRecords 和 SignalWork 原样迁入。

当前 219 项 Python 回归通过，另有实际 BGE/RAG/LlamaIndex 和计算进程回滚验证。可选文档/提交端口已保留，但完整生产保存器、原三个节点事务杀进程恢复用例及完整宿主仍未接通；不能据此宣称 P3/P4 或三应用验收全部完成。证据：evidence/2026-10-27-node-locks.json。

## D002：core 是文件夹，不是单文件（2026-10-27）

用户明确纠正：目标是 `domain/core/` 包，保留其中按职责拆分的原文件。不得合成 `domain/core.py`。

误合并尚未提交，现已纠正。14 个基础实现文件与迁移前提交的 AST 一致；`modules/` 保留内置模块，模型 HTTP 适配归入 `adapt/models/`。

平台注册的业务模块仍只允许 Agent、工具发现、上下文组装器三种。记忆策略是 Agent 的内部支持代码，不另注册成模块。

## D003：应用二的数据节点继承当前 DataNode（2026-10-27）

用户明确要求：应用二的各种数据节点通过继承当前 `domain/core/data_node.py` 的 DataNode 实现。

不复制旧 Node/数据节点继承树作为运行底座；具体节点保留原业务语义，以对应 Dataer 和 Saver 实现访问与保存。所有节点最终均应满足 isinstance(node, DataNode)。

原项目实际类型已定位：ValueNode、CsvNode、SqliteNode、LlamaIndexNode、CollectionNode（含不同 storage 后端）。迁移位置与原行为对照详见 APP2_DATA_NODES.md。

## D004：频道沿用原 allow/deny 逻辑（2026-10-27）

用户答复“沿用旧逻辑”，授权 Link、Module、access 支持原频道白名单/黑名单。默认 allow；模块 deny 在调用时根据当前已声明频道全集解析，连接 deny 直接执行匹配；显式空频道仍可指定只在本节点执行。保存加载保留连接模式。

状态：已实现，6 项新增回归与原 106 项行为测试通过。B003 已解除。

## D005：复制表不重新检查依赖（2026-10-27）

用户要求：前端复制节点或网络时直接复制，不检查节点的依赖表、不通过安装器重新补装。

核心增加 Tools.copy() 与 Modules.copy()，均为浅拷贝：容器可独立增删，成员对象引用保留，Modules 的聚合工具箱入口独立。过程不展开工具、不读取依赖声明、不绑定模块、不安装或校验依赖。

这两个接口用于表级副本，不能将同一模块实例直接挂到另一个节点。完整节点/网络副本继续沿用原 shared/graph/subnets.js 的配置复制流程：复制已有模块配置/状态、重分配节点 ID、重映射内部引用、复制资源并清空会话游标；装配独立运行实例时直接恢复已有表，不经过依赖规划。完整前端/运行装配尚待迁移。

## D006：上下文收集文件地址，不扩展 access 传路径（2026-10-27）

用户明确要求：不要传网络路径；仿照工具收集器，在遍历过程中收集 Markdown 文件地址，现有遍历顺序即是组装顺序。

已实施：ContextAssemblerModule 使用现有 @access 收集 Markdown 文件地址和当前正文；system_prompt/context/inputs/tail 分别遍历，配置来源先于网络来源。输出保留文件地址、稳定来源 ID 和频道，不再生成网络路由 path。串联按外层 BFS 收集下游 collect 的结果，不递归提前插入更深的组装器。去重、变化冲突、直接文件授权和 1 MiB 限制沿用原规则。

前端来源预览改为显示文件地址，access 接口和 core 不作修改。preview/assemble 均只返回 patch，不消费事件；原 AgentInputs 状态对象已原样移入 Agent 模块，实际投递和 DSH 会话恢复仍由后续执行适配器迁移。

验证：12 项上下文行为测试 + 4 项原输入状态/组合测试；全部 131 项 Python 测试通过；迁移的 UI 脚本语法检查通过。AgentInputs 与原实现 AST 一致。

## D007：ValueNode 改为真实文件存储（2026-10-27）

用户针对 B005 明确答复“改成文件存储即可”。因此不调整通用 Saver：ValueNode 继承 DataNode，ValueDataer 实时读写 JSON 文件，ValueSaver 提供真实 path 并直接复制源文件。数值/文本/列表/对象等仍是单个 JSON 值，固定键 value、insert 冲突、查询状态等规则保留，JSON 中的文件路径字符串不会被解引用。

save_data=False 保存实际源文件路径；True 复制源 JSON 文件。旧内联 parameters.value 在项目数据迁移时写入真实 JSON 资源后改成文件路径，不能只改节点外观。业务节点位于 projects/knowledge_archive/nodes，采用可直接作为 Python 包导入的目录名。

状态：ValueNode 与 7 项文件/保存/跨节点测试已实现并通过；旧应用模板/配置转换随完整项目迁移接入。core 未改。

## D008：不保留同归属树的无连线调用（2026-10-27）

用户明确选择“不保留这种无连线调用”。因此不增加 access(scope="family")；parent_id 自身不授予访问权。跨节点模块调用统一经实际连接、频道、强度和阈值判断，包含节点与亚节点之间的调用。

原 module_requests.local_call / ModuleRuntime.local_access 中按 same_family 直接跳转的捷径不迁移。原执行器 prepare 对外部节点也不能借 same_family 绕过连接；旧配置依赖该入口时迁成可见的业务连接和对应频道授权，不引入隐式家庭连接或旧 ctx 后门。

原 tests/test_subnodes.py 的 parent_pure_local_call_ignores_channels 等允许无连线调用的断言因本决定不再适用，替换为“有归属也不可越过连接/频道/阈值”的负向验证；业务输出断言仍需保留。D008 不自动删除亚节点类型或显式配置的出边共享能力，其他原行为继续逐项迁移。

## D009：管理复用频道，不为遗留机制扩展核心（2026-10-27）

用户明确指出，管理需求可以拉管理员频道，复用现有频道逻辑，并要求核对三个应用是否实际使用旧机制。

核对实际 profile 入口后：讨论/资料库没有无连线跨节点依赖；小镇 7 个工具亚节点确实通过 tool_sources + same_family 被访问。迁移方案是把工具发现器直接装到 NPC 节点，保持它自己的频道与强度，取消这条亲缘捷径，不添加 family 模式。管理用显式频道，不另造权限体系。

执行准则：先核对当前三个项目及明确要求保留的前端/制作 Agent 功能的真实调用，再决定旧实现去留。不能只因旧测试存在就认定某旧能力必须迁入 core。具体证据与当前入口见 ACTIVE_APPLICATIONS.md。

## D010：旧实现适配新设计，直接使用 Tools（2026-10-27）

用户明确要求：迁移原则是修改旧实现来兼容新内容，不是修改新内容去兼容旧实现。工具发现器返回的 Tools 已可迭代，使用处直接 for/list；经过 access 取得对象就已经完成可达性判断，不在各处重复寻路或验证。

据此恢复原 ToolDiscoveryModule.discover() 和原 Markdown 记忆工具实现，删除刚新增但尚未接入实际执行器的 collect/invoke、ToolCatalog、DeclaredTool 和配套实验测试。新核心不变。旧执行器随后直接遍历 discover() 结果，把工具本身已有的 name/description/parameters 交给模型协议，调用所取得的工具引用；不再添加工具来源目录、别名目录、路径、中继调用协议或调用前重新发现。

状态/配置等确有原业务职责的协议随实际应用逐项迁移，不能先搭空框架。未验证的 RuntimeModule 原型已撤回。未接入真实调用点的 JSON 值支持原型一并撤回。

D010 替代之前 B002 和工具目录阶段中“保持旧来源协议、调用时可达性复查”的迁移安排。原 f422995 的 182 项记录仅为当时实验结果，不代表当前实现必须保留这些代码或断言。旧应用若实际暴露与新核心冲突的行为，记录具体实例讨论，不能预先加兼容层。

## D011：上下文组装器保持清楚主流程，四路策略拆分（2026-10-27）

用户要求清理非必要验证/核实/注释，并将四类重复处理拆为策略类，主结构像工具发现器一样清楚。

ContextAssemblerModule 主流程为 collect → 收集本地配置与四路 Markdown 来源，assemble → 合并下游 collect 并生成 patch，preview → 复用 assemble。SystemPromptStrategy、ContextDocumentStrategy、InputEventStrategy、TailStrategy 分别处理四种输出格式，共用 ContextStrategy 的 access 收集过程。策略为模块内部支持类，不注册额外业务模块。

删除重复模式/字符串验证、每次请求的重复深拷贝、重复来源正文核对和说明性注释。去重按 (kind,id) 保留首次来源，不再逐字比较后续副本；相应断言改为首次来源优先。频道选择、BFS 顺序、下游自身配置、文件读取错误展示、预览不消费输入等行为继续验证。

验证：12 项组装器行为测试及全部 169 项 Python 回归通过，未改 core。见 evidence/2026-10-27-context-strategies.json。

## D012：模块组件归入同一模块目录（2026-10-27）

用户要求：同一模块拆成多个文件时，所有组件放在同一个模块文件夹，不在 modules 根目录散放；后续应用模块迁移同样遵守。

三个内置模块统一为 modules/<模块名>/ 包。Agent 的 inputs/memory 与主体放在一起；上下文组装器的 strategies 与主体放在一起。__init__.py 公开模块类，原 modules.agent / modules.context_assembler / modules.tool_discovery 导入名称保留为正式包入口。应用项目以后同样采用 projects/<项目>/modules/<模块名>/ 归拢实现及其内部辅助文件。

## D013：Agent 改为节点类型，按类型隔离收集内容（2026-10-27）

用户要求：Agent 实现为节点，继承记忆策略对应的节点；目前支持 Markdown 与其他/空记忆，节点类型统一为 agent。上下文只读取 Markdown 节点，工具收集器跳过 Agent 节点。完成后继续全量迁移。

现实现位于 domain/agent/：AgentNode(Node) 提供空记忆分支；MarkdownAgentNode(AgentNode, MarkdownNode) 复用 Markdown 的 Dataer/Saver 并选择 Markdown 记忆策略。Node.node_type='node'、MarkdownNode.node_type='markdown'，AgentNode 覆盖为 'agent'。AgentModule 已删除，不留旧安装入口。

工具发现器跳过所有 agent 类型节点的工具表与中继调用，本 Agent 自身的工具由 AgentNode.available_tools 加入。跳过内容不裁剪 access 的路径；仍沿现有频道、强度继续遍历。上下文按 node_type='markdown' 选择文件，MarkdownAgentNode 即使继承 MarkdownNode 也不被当作普通文档读取。

保存加载记录 Agent 类型及输入状态；Markdown Agent 仍遵守 save_data 的文件引用/复制行为。自定义数据 Agent 可通过多继承选择对应数据节点，未匹配记忆策略时为空策略；自定义数据类型的持久化按 node_types/agent_node_types 注册。

本决定取代之前“所有 Agent 功能放可安装 AgentModule”的安排。内置节点包为 domain/agent/，内置业务模块现在是工具发现与上下文组装两个包；应用模块仍按独立模块目录迁移。没有恢复旧 AgentNode 实现或旧 ctx/公开工具表机制。

验证：22 项 Agent/输入/隔离行为断言通过；新执行器 13 项行为断言通过；当前全部 186 项 Python 测试通过。原模块安装/卸载专项因 Agent 已不再是模块而删除，记忆 CRUD 等断言已移入 Agent 节点测试。证据见 evidence/2026-10-27-agent-nodes.json。


### D001 / P4 持久化接线进展（2026-10-27）

- app/runtime/backend.py 以新 Network、Node/DataNode、Module/access 实现原快照/事务提交协议，没有保留旧 Backend 或 ctx 的运行路径。
- app/network_saver.py 增加纯配置生成/重建入口；节点信息平铺为 NodeRecords 所需 node_id。日志保存引用当前资源，显式导出才按 save_data 复制；事务快照独立于导出开关。
- 模块实现由应用登记工厂，恢复实际配置/状态/工具表并绑定新节点；不重新安装或校验依赖。工具函数不作为 Python 对象写进 JSON，直接调用方式没有变化。
- 原恢复包校验、游标待确认/确认协议迁入 app/persistence/recovery.py，3 个独立函数 AST 一致。
- 原 inside、inside-no-save、committed 三种节点事务杀进程断言全部通过；10 项新持久化行为验证通过，当前全量 234 项。真实宿主、项目装配和模块自有工作目录快照还在迁移中，未宣称 P4/三应用完成。


## D014：信号共用 access，并提供可选去重（已撤回）

此前按用户要求实现了可选去重，并验证 7 项专项与全量 277 项测试；层生命周期接口及信号接入尚未实施。用户随后明确撤回共享方案，改为独立信号运行器，见 D015。此决定不再作为当前实现依据。


## D015：信号独立运行，恢复原 access（2026-10-27）

用户明确要求：“回滚这个信号机制和access吧，不复用access实现信号”。

撤回 D014 的 deduplicate 参数、条件去重分支及专属重访测试，access 恢复到 e79b09e 的父提交版本。保留原有节点去重、频道/强度、同层并发、分层屏障及 D001 遇锁等待；不加入信号层钩子或回源策略。

信号按原业务迁入独立的 app 运行器，负责分层推进、LayerWork.drain、脉冲回源回执、预算、取消、故障和持久化。已有 LayerWork 属于原业务迁移，不因撤回共享方案删除。此决定解除 B007 的共享接口讨论；独立运行器本身仍待迁移，不能宣称已经实现或通过三应用验收。

验证：access 文件内容与 e79b09e 父提交完全一致，撤回后全量 270 项测试通过（原 277 项扣除已撤回参数的 7 项专项）。用户 DataNode.save_data 默认值修改保留且不纳入本次提交。证据见 evidence/2026-10-27-signal-access-rollback.json。
