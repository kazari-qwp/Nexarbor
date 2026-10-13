# 框架与组件接口

`python/datanet/core` 负责图、节点协议、读写连接、管理树、访问预算、序列化和配置包装配。具体数据节点通过 `NodeCodec` 注册，节点工具箱通过 `register_toolbox` 注册。

`adapters/harness/framework` 连接原生 Agent、Session、工具权限、文档历史和组件生命周期。`adapters/harness/backend` 提供 stdio RPC 与持久检查点，业务路由从组件清单加载。`adapters/harness/runtime/agent-loop` 包含官方运行时及请求尾部扩展。Python 本体不导入这个适配层。

## 清单

每个组件声明 `id`、`kind`、`enabled`、`requires`。JavaScript 入口 `entry` 可提供 `fallback(r)`、`define(r)`、初始化 `steps`、`install(r)`、`uninstall(r)`。框架先准备缺省端口，建立所有启用组件，再执行初始化和订阅。

工具由 `tools` 或 `toolPatterns` 声明归属，权限与启用状态共同决定能否执行。`toolPolicies` 声明工具选项；工具箱通过 `box` 指向组合清单；Agent 预设通过 `agentPreset` 指向自己的提示词和默认工具箱。共享的默认装配规则通过 `agentPolicy` 和 `agentDefaults` 声明。

Python 入口在 `python.path`、`python.node_codecs`、`python.toolbox_installers` 中声明。Harness 的 RPC 入口在 `harness.python_path`、`harness.services` 中声明。它们分别装入 Python 本体的命名空间和 Harness 适配层命名空间。

## 原生事件

| 事件 | 触发位置 | 组件动作 |
|---|---|---|
| `agent/created` | Harness 创建 Agent | 绑定项目根 Agent |
| `datanet/agent-configure` | 创建或恢复节点 Agent | 组件补充自己的配置和持久元数据 |
| `datanet/agent-capabilities` | 初始化或补充能力 | 经验视图、排障权限准备 |
| `datanet/agent-bound` | 绑定独立 Agent 上下文 | 文档生命周期、文本工具、执行记录绑定 |
| `datanet/agent-tools` | 装配获准工具 | 各工具组件登记自己的能力 |
| `datanet/agent-tools-ready` | 工具装配完成 | 恢复已授权的 Skill |
| `datanet/agent-ready` | 节点 Agent 可用 | 接入管理通讯树 |
| `datanet/root-role` | 根 Agent 绑定 | 项目根预设补充角色说明 |
| `datanet/restore-agents` | 检查点恢复 | 网络预设恢复成员会话 |
| `datanet/channel-enter` | 进入工具通道 | 首次或压缩后注入对应指南 |
| `datanet/feedback-received` | 真实 `datanet_feedback` 已持久记录 | 管理者获得修复入口及指南 |
| `datanet/delegated` | 委托已登记 | 委托者获得报告查询入口 |
| `datanet/report-channel-enter` | 进入报告查询 | 注入索引指南和读取工具 |
| `datanet/message-received` | 消息已接收 | 接收者获得该消息的一次性回复工具 |
| `datanet/graph-changed` | 网络装配或连接变化 | 更新绑定文本与工具 |
| `datanet/discussion-member-start` | 小组开始处理任务 | 首次加载项目查询文本 |
| `agent/prepare-context` | 模型请求组装前 | 同步当前文本连接 |
| `agent/request-tail` | 模型请求组装末尾 | 加入最新常驻文本 |
| `session/event` 的 `compaction/end` | Harness 成功压缩历史 | 清理已不在历史中的文档加载标记 |

这些事件使用原生 Cordis 的 `on`、`serial`、`waterfall` 调度。订阅、提示词片段和工具权限由组件生命周期集中回收。

## 数据和上下文

指南是普通历史消息：进入通道时需要才加载，压缩后再次进入再加载。工具定义由 Harness 管理；框架停用工具时保留定义并拒绝执行，恢复时重新开放权限。当前服务端路线使用 `addition-only`，原 `in-history.patch.yml` 留作可选实验配置。

公共笔记使用常驻文本，只参与当前模型请求尾部；历史记录与请求尾部快照分别保留。项目说明使用查询文本，小组可复用多个已有文本节点。关闭组件后，其检查点数据作为不透明数据保留，重新开启时由组件恢复。

配置式启停在重启 Harness 时应用。运行时的 `ComponentRuntime.disable(id)` 可以撤销组件的订阅、工具执行权限和上下文片段；客户端重新加载时采用清单配置。
