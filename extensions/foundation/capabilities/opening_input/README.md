# 一次性开场输入

将 `input.opening` 装配在 Agent 节点上，配置 `{"text":"初始处境"}`；text 也可使用核心输入支持的绝对文件引用。复用 agent_runtime 的首次执行入口，将正文与第一次任务合并为一个原生输入事件。装配、读取和打开会话不投递、不唤醒模型。

`opening_input_prepare` 将模块 prepared 标记与完整待投递事件在同一核心事务中提交。原生输入通道以来源和事件 ID 去重，确认后标记 delivered。重启不会重发开场，不因上下文压缩补回短期动机；需要长期保留的信息由 Agent 写入私人记忆。

此模块不依赖 NPC、信号或提示词装配器。不提供 Agent 工具。agent_runtime 只发出通用 `agent/execution-input` 钩子，未装配的节点不改变输入。
