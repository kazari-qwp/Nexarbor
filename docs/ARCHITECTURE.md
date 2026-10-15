# 四部分架构

本项目由核心、宿主适配层、可选执行器和 multi-agent 协作扩展包组成。核心与执行器均不导入 Harness 或协作包。

| 部分 | 目录 | 职责 |
|---|---|---|
| 核心 | `python/datanet/core/` | 普通节点、文本节点、Agent 节点，定向图、访问预算、管理关系、序列化、检查点、扩展注册与执行器接口 |
| Harness 适配层 | `adapters/harness/` | 双向 RPC、原生会话句柄、工具注册、历史文档与请求尾部、平台兼容，以及原生循环的请求扩展 |
| 可选执行器 | `executors/minimal/` | 独立的模型请求与工具循环、会话历史、消息投递、取消和执行预算；提供 MockExecutor 和 HTTPModelClient |
| multi-agent 扩展包 | `extensions/multi_agent/` | 讨论、协作、消息、队列、经验、排障、报告、文本呈现、驻留复用与终端策略 |

## 核心 Agent 节点

`AgentNode` 是核心类型，与普通 `Node`、`TextFileNode` 并列。它有稳定节点 ID、一份私人 Markdown 记忆，以及 `memory_read`、`memory_write` 两个私有工具。执行器可以绑定该节点，执行器种类和会话 ID 可随图保存；模型客户端、API 密钥与运行中的线程不序列化。

Agent 节点不内置协调者、讨论成员或执行组角色。这些角色由扩展节点配置及提示词装配。纯数据网络可以只创建普通节点和文本节点。

## 扩展包的四类组件

- `nodes/`：节点配置、Agent 角色配置、提示词与资源。
- `capabilities/`：工具、内部能力和事件服务的实现。业务 Python/JavaScript 只放这里；可声明模型可调用工具，也可只订阅事件。
- `toolboxes/`：工具 ID 列表及简短元数据。没有代码、嵌套工具箱或调度逻辑。
- `network_presets/`：网络拓扑、人数参数、资源引用与使用指南。

`component.json` 声明组件 ID、依赖、启停、资源和入口。能力可通过 `resources` 引用同扩展包里的节点、工具箱或网络预设资源。`tool-bindings.json` 定义工具 ID 对应的原生工具或扩展工具及授权配置，工具箱仅引用这些 ID。Skill 是能力提供的渐进式指南与授权入口，Agent 预设是节点配置。

未设置 `DATANET_COMPONENT_ROOT` 时，不加载协作包。启用方式：

```powershell
$env:PYTHONPATH = "$PWD/python"
$env:DATANET_COMPONENT_ROOT = "$PWD/extensions/multi_agent"
python scripts/components.py list
```

`profile.json` 保存组件开关，`DATANET_COMPONENT_PROFILE` 可覆盖；启用依赖不满足的组件不会运行。停用能力会撤销其工具执行权限及上下文片段，持久数据保留。

## 执行器接口

核心 `ExecutionRequest` / `ExecutionResult` 与 `Executor` 协议定义 `run`、`cancel`、`status`、`send`。`ExecutorRegistry` 将 Agent 节点、会话和允许工具显式绑定，拒绝跨节点共享同一执行器会话及未登记工具。绑定可保存后恢复；恢复前应注册执行器并重新装配相应工具实现。

可选的 `MinimalExecutor` 接收外部模型客户端；`HTTPModelClient` 接受 OpenAI 风格的 chat-completions 端点，`MockExecutor` 用于离线测试。通过 `DATANET_EXECUTORS=["minimal"]` 挂载其命名空间。它是轻量参考循环，没有 Harness 的压缩、原生沙箱和完整会话管理。取消在模型返回及工具边界检查，无法强制打断任意阻塞的 Python 工具；宿主工具应自带超时或进程终止能力。

Harness 路径使用其原生循环。适配器的原生 Agent 句柄通过端口提供 create/run/inspect/steer/cancel 等操作；`adapters/harness/executor.py` 提供同一执行协议的外观，工具应先由原生注册表装配。

## 事件与宿主边界

| Harness 原生事件 | 通用事件或操作 |
|---|---|
| `agent/created` | 建立宿主连接，发出 `session/root`；扩展决定根网络和角色装配 |
| `agent/prepare-context` | `context/prepare` |
| `agent/request-tail` | `context/admitted` 与 `context/tail` |
| `agent/pre-step`、`agent/request` | 同名事件转发 |
| `tools/pre-execute`、`tools/result` | 执行许可检查、`tool/native-before` 与 `tool/result` |
| `agent/status`、`agent/error`、`agent/turn-stopping` | 同名事件转发 |
| `agent/inbox/discarded` | `message/discarded` |
| `agent/request-error` | 由可选 `response_recovery` 能力通过原生扩展入口订阅 |

适配器不选择协调策略或排障策略。`component-extension` 是通用原生扩展装配端口；纠错重试次数、终端执行上限、结束后清理等策略由能力拥有。扩展目录由 `extensionRoot` 显式传入；顶层协作插件入口选择 multi-agent 包，通用适配器默认不加载业务包。

## 上下文与持久化

固定职责进入原生系统提示；通道指南按需进入普通历史，压缩后按需再加载。工具采用 Harness 动态注册与 addition-only 定义，停用时拒绝执行。公共笔记及短状态仅进入请求尾部；查询文本按需读取。这些策略的业务触发条件由相应能力订阅事件实现。

图结构、节点资源与扩展状态由 Python 检查点保存；Harness 保存原生会话事件。可选执行器把自身历史保存到执行器目录。进程内运行不能任意时刻完整快照：恢复后如何处理未完成委托由队列能力决定，框架不会无条件重放具有副作用的操作。

本次重构直接使用新的组件 ID 和路径，不保留旧导入、旧工具箱结构、旧节点迁移或旧工作区回退。旧状态已保存在本地备份提交中。
