# 框架与组件接口

Python 本体位于 `python/datanet/core`。图、节点协议、权限预算、管理树、序列化、检查点、组件服务装配和应用事件分发都在这里。业务实现位于 `components` 下的 Python 模块，提示词与指南由组件清单定位。Python 本体和业务组件均不导入 Harness 适配层。

## Harness 边界

`adapters/harness/framework/adapter.js` 保存原生 Agent、Session、工具执行句柄，提供通信端口。其余 JS 文件处理官方工具挂载、文档历史消息、工具注册与权限、原生输出状态转换。`adapters/harness/backend` 只有 Python 路径引导、stdio 入口及双向 JSON-RPC。`adapters/harness/runtime/agent-loop` 是原生循环及请求尾部兼容扩展。

端口操作包括创建/恢复/检查/运行/销毁原生 Agent、消息插话、结束工具回合、装配官方能力、注册工具、更新上下文片段、查询或注入历史文档。请求携带节点 ID，Python 不持有原生 SDK 对象。反向 RPC 使用独立请求 ID；stdio 接收线程持续处理回复，工作线程执行应用调用，等待模型期间不占用图事务锁。

## 组件清单

每个组件由 `component.json` 声明 `id`、`kind`、`enabled`、`requires`，使用以下 Python 入口：

| 字段 | 用途 |
|---|---|
| `python.path` | 组件 Python 命名空间目录 |
| `python.node_codecs` | 具体节点编解码注册 |
| `python.toolbox_installers` | 节点本地工具箱装配 |
| `python.services` | 图服务、RPC 路由、检查点扩展及恢复 |
| `python.runtime` | 应用组件的 `Plugin` 类 |
| `toolDefinitions` | 工具描述和 JSON Schema 文件 |
| `toolPolicies` | 工具授权选项及合并规则 |
| `box`、`agentPreset` | 工具箱组合、角色提示词和默认装配 |
| `agentPolicy`、`agentDefaults` | 默认能力声明 |

应用组件通过 `on(event, handler)` 订阅事件，通过 `rpc` 调用图服务，通过 `host` 使用原生通信端口。框架按启用依赖加载组件，不包含讨论、经验、排障、报告或消息流程的实现分支。

## 事件

| Harness 原生事件 | Python 事件/动作 |
|---|---|
| `agent/created` | 绑定根节点，恢复已保存的节点会话 |
| `agent/prepare-context` | `context/prepare`，组件同步当前文本连接 |
| `agent/request-tail` | `context/tail`，Python 返回最新常驻文本 |
| `agent/pre-step`、`agent/request` | 同名转发，预算和执行记录订阅 |
| `tools/pre-execute`、`tools/result` | 工具执行许可检查及 `tool/native-before`、`tool/result` |
| `agent/status`、`agent/error`、`agent/turn-stopping` | 同名转发，业务组件管理执行状态 |
| `agent/inbox/discarded` | `message/discarded`，更新消息回执 |
| `session/event: compaction/end` | 原生历史适配清除已压缩的文档标记 |

Python 内部事件包括 `agent/bound`、`tool/before`、`tool/after`、`tool/error`、`graph/changed`、`network/before-create`、`network/created`、`discussion/member-start`。组件据此管理通道、报告、排障和文本加载；原生适配不推导业务触发条件。

## 数据与上下文

角色提示词从组件资源读取。Leader、Recorder、Member 各只有一份 `prompt.md`；Python 配置包引用同一文件。运行时替换节点占位符，源文件正文保持不变。

通道指南是普通历史消息：进入时未加载才加入，压缩后再次进入重新加载。工具定义由 Harness 管理；停用时定义保留、执行许可撤销。当前模型路线使用 `addition-only`，`in-history.patch.yml` 保留为可选配置。

公共笔记等常驻文本仅进入本次请求尾部，不进入历史或压缩摘要；请求快照另行保存。项目说明使用查询文本，小组可引用多个已有节点。

`scripts/components.py enable/disable <ID>` 修改组件 profile，重启时应用。运行中 `datanetComponents.disable(id)` 请求 Python 移除该组件及依赖组件，撤销工具执行许可和上下文片段；持久数据保留，重新启用由原组件恢复。
