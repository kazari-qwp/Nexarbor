# Nexarbor 组件开发规范 v3

你编写的是挂载到单个节点上的功能组件。只实现组件职责；装配者决定节点、连线、频道和强度。说明、字段标题、错误提示和页面文案使用中文；Python 标识符与协议字段使用规定名称。

## 入口、清单与数据

清单格式为 nexarbor-module/v3，entry 固定为 module.py:execute。入口必须恰好是：

```python
from datanet.core.module_protocol import ComponentResult

async def execute(ctx, activation):
    return ComponentResult(data={"完成": True})
```

不接受额外形参、默认形参、旧 Module 类或构造器。返回必须是 ComponentResult(data=...) 或 ComponentResult(status='error', error='中文原因')。清单声明 id、version、node_types、requires、config_schema、state_schema、operations、signals；可选 tool_provider 和 frontend。operations 每项包含 name、channels、parameters、result，后两项分别是输入对象和返回 data 的 JSON Schema。装配及每次执行后检查状态；成功返回时检查结果。

activation.kind 是 access 或 signal。operation 为操作名；parameters 是不可变参数对象；source 和 request_id 由核心绑定，不能用参数伪造。信号响应额外包含 signal、delivery。参数里的节点 ID 只是数据，不是访问凭证。state 属于本实例，config 是不可变的装配配置，不能藏入原始对象或回调。

config、parameters、信号 content 和 ComponentResult.data 都使用冻结 JSON：对象是 FrozenDict，数组是 tuple。需要可修改副本或 JSON 原生列表时，使用 from datanet.core.json_values import thaw，再调用 thaw(value)；不要以为 deepcopy 会把冻结值变回可变对象。跨模块返回的访问结果已经是 JSON 副本。

## 本地能力

| 接口 | 用途 |
|---|---|
| ctx.config / ctx.state | 本实例的不可变配置与可持久化状态 |
| ctx.metadata() | 核心元数据与已登记扩展字段的统一视图 |
| ctx.read(request) / ctx.write(key, value, mode='upsert') | 所在节点的数据接口 |
| ctx.publish_metadata(fields) | 在本节点的 extensions[模块 ID] 下发布 JSON 字段；卸载后撤销 |
| ctx.update_inputs(patch) | 更新所在 Agent 的四路输入；普通模块不能传入任意文件路径 |

四路输入分别是 system_prompt（字符串）、context（含 id/text 的文档列表）、inputs（含唯一 id/text 和可选 delivery 的事件列表）、tail（字符串列表）。inputs 的 delivery 为 followup 或 steer；相同 ID 不重复投递，也不能改成另一份内容。context 用于保证存在的文档；tail 用于当前状态等每次请求的底部信息。只有 Agent 节点支持输入更新。

## 访问：沿网络伸出去的一只手

查询都需要 await：

```python
nodes = await ctx.network.nodes(channels=["资料"], strength=2)
metadata = await ctx.network.metadata("目标", channels=["资料"])
tools = await ctx.network.tools("目标")
visit = await ctx.network.visit("目标")
providers = await ctx.network.tool_sources("目标")
```

查询从所在节点出发，受本实例装配授权约束；遇到锁定节点会等待。nodes 返回带 metadata、path、strength 的条目。tools 查询已登记的工具，不把任意 JSON 描述变成工具。

call(target, module, operation, arguments, ...) 与 invoke(target, tool, arguments, ...) 一经调用就立即启动独立任务，可以并行后再等待：

```python
first = ctx.network.call("甲", "资料读取", "读取", {})
second = ctx.network.call("乙", "资料读取", "读取", {})
a, b = await first, await second
```

检查每次调用的 status，失败时按业务返回错误或抛出异常。回调返回前核心会汇合它发起的访问任务。同节点调用不消耗跳数。允许组件继续转调；被调用组件使用自己的装配授权，不继承调用者剩余强度或频道。每次请求都检查实际路径，不能自授频道、强度、任意起点或读取其他实例 state。不要私自启动脱离回调的后台任务。

## 信号：由核心持有的一道波

ctx.network.emit(channels=..., strength=..., content=..., kind=...) 立即返回回执。signal_status(id)、await wait_signal(id)、await cancel_signal(id) 管理本节点发出的信号。发出者正常结束、取消，或等待者取消，不取消已经交给核心的波；显式取消或关闭核心才停止。

信号频道集合保持原样，连接有任意频道重叠且强度符合门槛就可通过。核心广度逐层传播，同层并行，等本层所有响应及其必要访问结束后再进入下一层。响应组件仍使用自己的授权，不因收到信号获得额外权限。不要等待需要自己先完成才能继续的波。

activation.signal 是真实 Signal 对象，不是频道字符串。用 activation.signal.channels 读取频道集合，kind 读取请求种类，content 读取载荷，origin 读取源节点，signal_id 读取信号 ID。匹配频道使用 "metadata.refresh" in activation.signal.channels；不要把整个 signal 与字符串比较。delivery 提供 node_id、depth、strength、path、parents。

signals 可以是固定频道数组，也可以是 {"config":"signal_channels"}，由配置中的对应数组决定响应频道。空数组表示只接受访问激活。需要顺序、分支、并行及汇合时，优先复用 modules.executor 的配置化执行图，不接受任意 Python 表达式或函数。

## 节点锁与持久化

```python
async with ctx.network.lock_nodes([ctx.node_id, "目标"], timeout=30):
    result = await ctx.network.call("目标", "业务模块", "修改", {})
    if result["status"] != "ok":
        raise RuntimeError(result["error"])
```

所有执行模块或修改本地状态的节点都要包含在锁集合中。锁申请受当前可达范围限制，不赋予改边或其他权限。已有访问先结束，再整体获取锁、持久化旧记录，然后进入业务。正常退出整体增量提交；异常或取消恢复内部状态。支持 lock = await ... 后 await lock.commit() / await lock.rollback()；优先使用 async with，避免遗漏关闭。

在 with 内返回 error 对象仍是正常退出，会提交；业务失败要抛出异常或显式回滚。嵌套只能重入已有集合，不能扩大。持锁者发起的调用继承事务，其他访问和信号等待。持锁期间不要等待独立信号完成。timeout 限制获取锁和准备阶段，业务期限由调用者或执行图控制。

节点记录包括出边、模块状态、元数据发布、资源文件、Agent 输入及日志游标。旧记录按节点拼接，不递归备份链接目标；加载时删除目标已不存在的接口。外部工具产生的效果不回滚，不恢复半截模型思考。持久化由核心负责，不自行写快照或越过 ctx 读日志。

## Agent 工具与组件前端

节点的 modules 与 offered_tools 是两份列表。offered_tools 引用宿主已登记的外部工具；Agent 访问后由适配器装配，执行时重新检查来源、路径和授权。终端能力属于显式宿主工具，不是普通模块的默认能力。

需要提供 Agent 工具列表时，在清单声明 tool_provider:{"list":"收集操作","invoke":"执行操作"}，两个值都必须是已声明操作。list({}) 返回含 id/name/description/parameters 的数组；invoke 接收 tool_id 和 arguments。用 tools.collector 复用收集、串联和来源去重。仅声明 operations 不会自动成为 Agent 工具。

模块可以在清单可选声明 frontend:{"entry":"ui.html","title":"中文标题","height":320}。开发方式及页面通道见 FRONTEND_GUIDE.md。无前端时客户端使用通用配置表单；前端不改变组件的运行权限。

## 验收边界

宿主检查语法、清单、固定入口、装配、声明、已配置的信号响应、状态和组件测试。通用验收不穷举所有业务操作，必须补充针对需求的测试。普通组件拿不到 Backend、原始 Network/Node、全局扫描或任意宿主 RPC。仅已登记的官方模块可以拥有额外能力；缺少能力时报告，不使用文件、导入、进程或反射绕过。

测试写在 tests/test_*.py，使用 unittest.TestCase 或 unittest.IsolatedAsyncioTestCase；宿主不运行独立的 pytest 测试函数，发现测试文件但收集数为零会失败。优先通过真实 NodeModules 装配和调用来验证，或使用真实 Activation、Signal、ComponentResult 与 freeze/thaw。不要用字符串或 SimpleNamespace 替代信号对象，也不要通过改变模拟类型来让错误实现通过。框架成功处理一个信号封套，不代表业务返回 status='ok'，测试须检查业务结果。

这些是可信 Python 的 API 与契约边界，不是操作系统沙箱。不要把不可信代码隔离能力写成已实现的功能。
