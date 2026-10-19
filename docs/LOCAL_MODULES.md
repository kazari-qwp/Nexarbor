# 访问、信号与组件协议 v3

2026-10-18。当前组件协议为 `nexarbor-module/v3`，网络配置为 v8。旧应用、旧生成组件及旧网络配置没有自动迁移。新版工作台默认使用独立的 `build/workbench-v3`。

## 网络不要求根节点

网络可以有任意数量的节点，包括零个节点；`root` 只是普通编号，没有不可删除的保护，也不隐含读取其他节点私人数据的权限。新工作区提供一个可删除的“起始节点”，删除后不会自动补建或另选根节点。管理父节点必须由配置明确指定，复制时失效的父节点引用会清空。

完整网络预设、制作工作副本、应用和增量存档均接受无根网络与空网络。删除节点时编辑器同时清理相关连接、管理父节点和显式委托；其余节点的 Agent 会话和独立数据继续保留。应用自己的入口或管理员锚点只是业务配置，不是网络格式要求。

## 框架自带组件的更新

框架自带组件的源码更新后，现有工作区会采用当前随项目提供的标准版本；磁盘组件索引与旧快照中的版本记录不能把它重新降回旧版。来源明确的用户发布组件和测试候选仍使用自己的版本，已删除的组件也不会自动重新登记。

标准源码按版本和摘要存入新的发布目录，旧目录不覆盖；改变索引前在 `studio/library-history` 保留旧索引。节点上的配置、状态、文档与日志保持原数据。此机制更新框架自己的组件定义，不会静默删掉配置字段或替用户兼容失效的自制组件。

## 两种网络动作

**访问是一只手。** 从组件所在节点出发，沿实际连接，按授予的频道和强度读取信息、取得工具或调用另一个组件。独立调用立即开始、并发执行，可以等待需要的结果。回调结束前框架会汇合它启动的访问任务。

路径检查决定能否进入目标操作。被调用组件进入后使用自己的装配授权，不继承调用者剩余强度或频道。允许继续转调和回访；每条遍历独立去重，调用链另有 1000 次请求和 180 秒资源预算。资源预算用于终止失控任务，不代替权限。

**信号是一道波。** `emit` 将不可变信号交给核心，立即返回回执。发出者正常结束、被取消，或等待者取消，都不取消波。显式取消回执或关闭核心才停止对应任务。核心按广度逐层传播，同层并行，全部响应完成后才进入下一层。响应者按自身装配授权工作，其必要访问任务也纳入本层等待。信号的频道集合保持原样，边有任意频道重叠才允许通过。

```python
first = ctx.network.call('worker/a', 'worker', 'run', {'task': 'a'})
second = ctx.network.call('worker/b', 'worker', 'run', {'task': 'b'})
a, b = await first, await second  # 两个请求已经并行开始
receipt = ctx.network.emit(channels=['tick'], strength=3, content={'day': 1})
# 可选择 await ctx.network.wait_signal(receipt['signal_id'])
```

不要在一个信号响应中等待必须由自己先完成才能继续的同一条波。

需要在本时刻启动后续回应、又不能让发送者等待收信者整轮模型时，可调用 `ctx.network.post(target, module, operation, arguments, channels=[...])`。仅在当前信号层可用，仍检查本模块的实际路径、频道和强度；真正执行时重验，使用新的访问上下文，不继承原事务或请求者身份。本层所有后续访问结束后才进入下一层；数量受信号投递预算约束，时间受该波期限约束。独立持续存在的传播仍使用 emit。

锁的判断与本次小镇的错误复盘见 [反面教材](NODE_LOCKS.md#反面教材用锁和串行拓扑掩盖并发问题)。

## 固定入口与返回

```python
from datanet.core.module_protocol import ComponentResult

async def execute(ctx, activation):
    ctx.state['count'] = ctx.state.get('count', 0) + 1
    return ComponentResult(data={'count': ctx.state['count']})
```

只有 `ModuleDefinition` 可以登记。框架检查异步函数签名，必须恰好是 `execute(ctx, activation)`，不接受额外形参或默认形参。清单的 entry 固定为 `module.py:execute`。

- `activation.kind`：`access` 或 `signal`。
- `operation`、不可变的 `parameters`、框架绑定的 `source` 和 `request_id`。
- 信号激活额外提供不可变的 `signal` 和 `delivery`。
- 返回必须是 `ComponentResult(status='ok', data=...)` 或 `ComponentResult(status='error', error='...')`。

业务参数仍可由各操作声明，但位于统一封套中，并受 JSON Schema 检查。一个节点 ID 只是数据，不能绕开路径检查。参数不能覆盖框架绑定的调用身份。

清单声明 `id/version/node_types/requires/config_schema/state_schema/operations/signals`。每项 operation 声明 `name/channels/parameters/result`；其中 result 校验返回的 data。配置、状态和结果都经校验，跨实例交换 JSON 副本。旧清单在导入源码前拒绝；新版源码的入口签名不合规则不能登记。

可选 `name` 提供中文显示名称，程序 ID 保持稳定。`requires` 声明同节点直接依赖，工作台装配、应用和加载时递归补齐；已存在实例复用原配置、状态与授权，不重复挂载。缺少发布模块、依赖成环或节点类型不符时拒绝装配。客户端的依赖数字只统计一层，不递归累计。

`ctx.caller_id` 是直接调用者，`ctx.requester_id` 是访问链最初发起者，转调不会覆盖最初身份。它们均由核心绑定，不能用参数中的节点编号代替；身份也不授予额外访问权限。

## 普通组件能力

核心节点锁提供 `async with ctx.network.lock_nodes([...])`，支持重入、异步等待、旧节点记录拼接存档和内部回滚。网络查询 nodes/metadata/tools/visit/tool_sources 使用 await。见 [节点锁与节点持久化](NODE_LOCKS.md)。

装配项包含 `config`、`state`、`access`：

```json
{"config":{},"state":{},"access":{"strength":2,"channels":["town.local"]}}
```

装配者授予权限，组件不能自授。节点的 `module_strength` 是模块的默认强度；模块 `access.strength:null` 表示继承该默认值，显式数字可以超过节点默认值。模块运行时的请求仍不能超过本实例授权，频道也不能扩大。它与节点散度 `divergence`、Agent 执行器的强度分开。直接 mount 省略 access 时继承节点默认强度、频道为空。配置只读，状态属于本实例。

| 接口 | 行为 |
|---|---|
| `ctx.metadata/read/write` | 本节点元数据和本地数据 |
| `ctx.publish_metadata(fields)` | 在本节点、本模块 ID 下发布字段；卸载撤销 |
| `ctx.update_inputs(patch)` | 更新所在 Agent 的四路输入；不加载任意文件路径 |
| `ctx.network.nodes/metadata` | 从本节点按频道和强度取得可达信息快照 |
| `ctx.network.edges` | 异步读取可达节点的出边快照 |
| `ctx.network.patch_edges` | 校验整批后修改可达节点出边；两端和频道均受授权限制 |
| `ctx.network.visit/tools` | 访问可达节点，取得其提供的已登记工具引用 |
| `ctx.network.tool_sources` | 查询可达节点明确声明的工具提供模块；返回操作名，不暴露实例 |
| `ctx.network.call/invoke` | 立即启动可等待的组件／工具调用 |
| `ctx.signal_id` | 当前信号层的标识；非信号活动为 None |
| `ctx.network.post` | 在当前信号层排入有界后续访问，立即返回；本层等其完成再传播 |
| `ctx.network.emit` | 交付核心持有的波，返回回执 |
| `signal_status/wait_signal/cancel_signal` | 查询、等待、取消本节点发出的信号 |

没有 Backend、原始 Network/Node、任意起点、全局扫描、其他组件 state 或任意宿主 RPC。接口只能在本组件的有效回调中使用；卸载、禁用、重装使旧授权失效。长业务不应私自启动脱离回调的后台任务，独立传播交给核心信号。

出边修改格式为 `[{"source":"起点","target":"终点","action":"add","metadata":{"channels":["movement"],"threshold":1,"multiplier":1,"attributes":{"relation":"location"}}}]`。每项固定四个字段，action 为 add 或 remove。两端都要在当前可达范围，连接频道不得超过本实例授权；add 对完全相同的边去重，remove 按完整连接数据精确匹配。整批先预检再写入，不会因后项失败只写入前半批。包含资料与输入修改的多步骤业务仍需先锁住相关节点，锁本身不增加权限。固定步骤直接依次 await；可配置流程才需要执行图。

## 可选官方网关

`capabilities/network_gateway` 是显式启用的宿主扩展，不默认加载。公开操作使用 `network.extended` 频道，支持 nodes、metadata、incoming、interfaces、connect、disconnect。装配时必须另给：

```json
{"strength":0,"channels":["network.extended"],"extension":{"operations":["metadata","incoming"],"targets":["place/mine","npc/miner"]}}
```

访问者仍需实际可达网关。网关的全局操作受显式 operation 和 target 白名单限制，编辑连接时两端都要获准；`targets:["*"]` 才是全局目标权限。普通组件清单无法声明宿主扩展，替换同名定义也不能冒充官方注册。

这是框架 API 边界，不是恶意 Python 的操作系统沙箱。源码仍是可信本地代码；反射、任意 import 和系统调用若需隔离，必须增加进程及操作系统边界。

## 外部工具

节点 `modules` 与 `offered_tools` 是两份列表。外部工具由可信提供器登记，节点只保存引用：

```json
{"offered_tools":[{"ref":"harness:read","channels":["tools"]}]}
```

Agent 的 execution 设置 `channels:["tools"]` 与足够 strength，调用内置 `network_visit` 后取得工具，适配层将其装配到 Agent。每次执行重新检查引用、提供节点、当前图路径、频道、强度和参数 Schema。断开连接或移除 offer 后，即使 Harness 历史中仍有旧声明，也不能继续执行。伪造工具描述 JSON 不会登记新执行能力。

目前工作台提供本机 Harness SDK 的十个真实工具：read、write、edit、read_image、glob、grep、pwsh、job_output、job_list、job_kill。它们通过官方文件／终端／任务服务执行，不是我们重新实现的工具；属于显式外部宿主能力，外部效果由宿主权限控制。模型、凭据、需要交互或其他服务的工具及通用 MCP/Skill 导入不在本轮范围。

可选的标准模块 `tools.collector` 按自身授权收集工具，并调用可达的同类收集器合并结果，按原始节点＋工具引用去重。串联调用保持各实例自己的权限，远端工具通过收集器链执行。当前不添加收集器环检测。见 [组件说明与六节点验收图](../extensions/foundation/capabilities/tool_collector/README.md)。

需要向 Agent 提供工具列表的组件可在清单声明 `tool_provider:{"list":"collect","invoke":"invoke"}`，两个值必须是已声明的操作。list 无参数并返回含 id/name/description/parameters 的数组；invoke 接收 tool_id 和 arguments。Agent 访问后，通用适配器装配带来源的工具，执行时重新访问该提供模块。普通模块不会仅因有 operations 就成为 Agent 工具。`network.tools` 仅查询，不自动装配，避免收集过程重复登记。

固定的模块工具可声明 `agent_tools:[{"id":"move_here","name":"移动到此","description":"移动到此地点。","operation":"move"}]`，参数模式直接复用公开操作。框架登记为 `module:模块ID/工具ID`，执行时仍检查当前路径与操作授权。拖工具自动装配实现模块和递归依赖，拖模块即提供所携带工具；模块工具不重复写入 offered_tools，卸载模块后停止提供。静态 agent_tools 与动态 tool_provider 不在同一模块混用。工具收集器同时支持宿主工具和静态模块工具。

“移动到此”示例见 [模块说明](../extensions/foundation/capabilities/move_here/README.md) 和 [三节点网络](../examples/move_here/README.md)。它依赖最小的“位置资料”模块，以 NPC、旧地点、新地点的节点锁保护位置边、访客和 Agent 输入更新，异常回滚；不经过 LangGraph。

## 验证范围

新协议、频道、信号、Agent 输入和存档的定向核心回归，加上前端布局测试与真实桌面端到端验证。桌面验证涵盖工具目录与装配、访问后取得并调用官方 read、断开路径后拒绝、v3 组件验证发布挂载、关闭后重新恢复。未运行付费模型；旧应用和旧协议测试不属于本轮兼容性验收。

## 模块执行图

`capabilities/module_graph` 提供 v3 模块 `modules.executor`。调用 run 或收到配置频道/种类的信号后，复用已有 LangGraph 后端执行 call/sequence/parallel/branch。每一步均为受网络权限约束的模块调用。详见 [配置、参数引用和返回值](../extensions/foundation/capabilities/module_graph/README.md)。客户端模块页可使用已有可视化执行图编辑器。旧事件触发器及旧应用不作兼容迁移。


## 本地数据接口与资源（2026-10-19）

`ctx.schema()` 读取所在节点的数据结构，`ctx.read(request)` 与 `ctx.write(key,value,mode=...)` 仍只作用于本节点。不同节点的读写通过既有网络访问进入目标节点上的数据模块，不把网络对象、磁盘路径或数据库连接传给模块。模块 `node_types` 支持扩展节点标识，实际装配仍校验该节点类型、配置与操作声明。

`data.local` 复用上述接口，支持 JSON、CSV、SQLite、文本和本地知识集合；`data.knowledge` 通过同节点依赖复用只读检查，管理知识版本、章节与索引。修改操作使用现有节点锁，成功后统一存档，异常恢复本节点旧数据。

节点编解码器通过 `resources` 声明文件，通过 `resource_directories` 声明目录。文件快照可为 UTF-8 文本，或 `{encoding:"base64",data:...}` 二进制对象；目录递归包含实际数据文件，不包含锁、日志与临时文件。嵌入模型不属于可写数据资源。SQLite 快照使用数据库备份接口纳入已提交 WAL 页；恢复、复制和节点锁回滚都使用同一资源格式。
