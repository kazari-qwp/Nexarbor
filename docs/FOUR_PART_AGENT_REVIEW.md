# 本次 Agent 可见内容变更

原有角色提示词与指南正文保持原意，移动到 `extensions/multi_agent/`，资源路径按新布局调整。角色提示词位于 `nodes/agent_*/`，网络指南位于 `network_presets/*/AGENTS.md`。节点类型、工具名称和现有业务流程未因目录拆分而改写。

核心 Agent 节点新增私有工具描述原文：

- `memory_read`：读取自己的记忆文件。
- `memory_write`：更新自己的记忆文件。

扩展文本节点的本地工具描述原文：

- `read`：读取本节点文本。
- `get_schema`：查看文本节点结构。

可选执行器的默认职责原文：`Complete the requested task using the available tools.`

可选执行器的请求尾部提示原文：`当前请求次数：{request_number}/{max_rounds}。这是本次任务的模型请求上限。` 有完成判据时追加 `请在额度内使用提供的工具完成任务。`；完成判据未满足时追加普通消息 `任务要求尚未完成，请使用提供的工具完成。`

这些执行预算提示仅用于可选 Python 执行器。Harness 路径继续由 Harness 循环与协作能力提供上下文。


原数字委托示例已改为 Agent 节点连接独立数据节点。其 worker 提示词原文：

> 你是数字处理 Agent，负责读取数据节点 {{node:worker_data}} 的数字并报告来源。
> 先用 list_tools 查看该节点的 read 工具，再用 invoke_tool 读取 value；两次访问均使用 strength=1。不猜测或修改数据。父 Agent 的消息是本次任务输入。

路径：`extensions/multi_agent/nodes/agent_number_worker/python/datanet/components/agents/number_worker/prompt.md`。

相应描述原文：`数字处理者：读取所负责的数据节点并报告来源。`；示例 Agent 节点描述：`负责读取数字数据并回复委托。`；数据节点描述：`保存模拟数字42。`。
