# 访问、信号与组件协议 v3

2026-10-18。当前组件协议为 `nexarbor-module/v3`，网络配置为 v8。旧应用、旧生成组件及旧网络配置没有自动迁移。新版工作台默认使用独立的 `build/workbench-v3`。

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

## 普通组件能力

装配项包含 `config`、`state`、`access`：

```json
{"config":{},"state":{},"access":{"strength":2,"channels":["town.local"]}}
```

装配者授予权限，组件不能自授。直接 mount 省略 access 时为零强度、空频道。配置只读，状态属于本实例。

| 接口 | 行为 |
|---|---|
| `ctx.metadata/read/write` | 本节点元数据和本地数据 |
| `ctx.publish_metadata(fields)` | 在本节点、本模块 ID 下发布字段；卸载撤销 |
| `ctx.update_inputs(patch)` | 更新所在 Agent 的四路输入；不加载任意文件路径 |
| `ctx.network.nodes/metadata` | 从本节点按频道和强度取得可达信息快照 |
| `ctx.network.visit/tools` | 访问可达节点，取得其提供的已登记工具引用 |
| `ctx.network.call/invoke` | 立即启动可等待的组件／工具调用 |
| `ctx.network.emit` | 交付核心持有的波，返回回执 |
| `signal_status/wait_signal/cancel_signal` | 查询、等待、取消本节点发出的信号 |

没有 Backend、原始 Network/Node、任意起点、全局扫描、其他组件 state 或任意宿主 RPC。接口只能在本组件的有效回调中使用；卸载、禁用、重装使旧授权失效。长业务不应私自启动脱离回调的后台任务，独立传播交给核心信号。

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

## 验证范围

新协议、频道、信号、Agent 输入和存档的定向核心回归，加上前端布局测试与真实桌面端到端验证。桌面验证涵盖工具目录与装配、访问后取得并调用官方 read、断开路径后拒绝、v3 组件验证发布挂载、关闭后重新恢复。未运行付费模型；旧应用和旧协议测试不属于本轮兼容性验收。
