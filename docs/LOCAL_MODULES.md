# 局部模块核心与官方网关

2026-10-18。本轮建立新的核心接口和 `nexarbor-module/v2` 契约。**不兼容旧构造器、v1 标准模块或缺少 access 的模块存档。旧小镇、旧应用组件与既有发布产物未迁移，不能把本轮核心测试当作应用复测。**

## 普通模块

构造器只接收 `ModuleContext`。没有 Backend、Network、Node、Application、Harness、宿主目录、全局节点列表、跨实例原始状态或任意 RPC 接口。

```json
{
  "counter": {
    "config": {},
    "state": {},
    "access": {"strength": 2, "channels": ["town.local"]}
  }
}
```

access 由宿主装配者指定，模块清单不能自授。直接调用宿主 mount 时省略 access 等价于 0 强度、空频道；保存后的模块项必须显式包含 access。更改授权要重新装配。

| 接口 | 范围与返回 |
|---|---|
| `config` / `state` | 本实例不可变配置 / 可持久化的本实例状态 |
| `node_id` / `module_id` / `caller_id` | 框架绑定的身份数据，调用者不能通过业务参数覆盖 |
| `metadata()` | 所在节点统一元数据副本 |
| `publish_metadata(fields)` | 仅以本模块 ID 为命名空间发布本节点字段，卸载撤销；setup 从持久状态重建 |
| `read(request)` / `write(key,value)` | 仅操作本节点提供的本地数据能力，返回 JSON |
| `update_inputs(patch)` | 只更新所在 Agent 的 `module:模块ID` 四路输入源；只接受文本，不解析文件路径 |
| `network.nodes/metadata/tools` | 从本节点按频道、强度遍历后获得的数据副本，无入边扫描或任意起点 |
| `await network.call(target,module,operation,args)` | 调用可达节点的公开组件操作 |
| `await network.invoke(target,tool,args)` | 调用可达节点实际暴露的工具 |
| `await network.emit(...)` | 以本节点为起点发出授权范围内的信号；只返回源端回执，不返回全网投递表 |
| `receive(channels,handler)` | 收到频道重叠的信号后响应，完成返回就是就绪 |

自定义核心模块继承 `NodeModule`，在 install 内调用 `operation`、`tool`、`receive` 注册能力。标准模块继承 `StudioModule`，由 v2 清单统一注册并校验 Schema。模块之间不拿彼此的实例或 state 引用；参数和返回值均为 JSON 副本。

操作和工具声明自己的频道。远端调用要求请求已获授的频道与接口声明有交集，且这些频道实际存在可达路径；空频道操作只允许本节点调用。不能用无关频道先找到目标，再调用另一频道的操作。

嵌套调用同时受接收组件装配授权、当前调用剩余强度和频道限制。不能换起点、重新充满强度或扩大频道。请求可以主动缩小强度。祖先节点不可递归回访，但调用返回后可以再次调用同一端点。

## 信号与异步

普通模块收到 `ModuleSignalContext(signal,delivery)`，其中没有 network。信号频道保持原样；收到信号不会授予其中的频道。响应代码使用自己的装配授权。网络仍逐层广度传播，同层节点并行，同节点模块按装配顺序执行，整层完成后才传播下一层。

每次回调的接口授权在返回时失效。后台任务不能在回调结束后继续访问网络；卸载、禁用、原位重装也使旧工具、上下文和未完成调用失效。模块代码中不要启动脱离回调生命周期的业务任务。

宿主可使用 `NodeModules.call` 作为可信执行入口；该入口不会传给模块。同步宿主可调用 `invoke_tool` 等待异步工具完成；异步宿主使用 `await invoke_tool_async`。不要在事件循环里用同步工具入口执行异步工具。

## 可选官方 network.gateway

组件为 `capabilities/network_gateway`，位于 foundation，但默认选择为空，不会自动加载、挂载或授权。它不返回原始网络对象，只提供六种明确操作：`nodes`、`metadata`、`incoming`、`interfaces`、`connect`、`disconnect`。

```json
{
  "network.gateway": {
    "config": {"channels": ["network.extended"]},
    "state": {},
    "access": {
      "strength": 0,
      "channels": ["network.extended"],
      "extension": {
        "operations": ["metadata", "incoming"],
        "targets": ["place/mine", "npc/miner"]
      }
    }
  }
}
```

其他模块需被授予 `network.extended` 并实际可达网关，再显式调用它。网关只返回目标白名单范围内的节点、入边来源和连接；编辑连接要求两端都在白名单。`targets:["*"]` 明确表示全局授权，绝不是默认值。connect/disconnect 会提交核心存档；删除只移除指定频道，保留其他频道。

扩展通道由宿主把**具体工厂与处理器绑定注册**。普通 v2 清单没有声明扩展权限的字段；普通模块带 extension 装配授权会被拒绝，替换同名普通工厂也不能冒充官方模块。已装网关如果没给 extension，所有扩展操作仍拒绝。

这是一套框架接口边界，**不是恶意 Python 的执行沙箱**。组件源码、Python 服务入口仍属于可信宿主代码；同进程 Python 的反射、任意 import、文件/系统调用需要另外的进程与操作系统权限隔离。安装宿主级扩展与装配普通组件是不同的信任边界。

## 本轮验收

82 项相关测试全部通过，检查局部默认值、频道/强度、不相关路径、转调不扩权、JSON 副本、公开异步工具、信号层屏障、授权过期、卸载重装、官方网关白名单与工厂身份、真实 Backend 全量存档重开，以及 v1 提前拒绝。没有调用付费模型，也没有迁移或重跑旧小镇。
