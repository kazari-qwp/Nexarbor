# 本次可见文本审阅

没有修改 NPC、根节点、全体 Agent 的提示词，没有新增 Agent 可调用工具或修改现有工具描述。执行报告从 responders/steps 改为 executions/results，具体结构见执行图接口文档。

新组件 manifest 的 description 原文如下（用于组件功能判断）：

- langgraph_backend：LangGraph 执行图后端，供事件触发器和模块执行器复用。
- event_trigger：匹配事件，选择要启动的执行图。
- module_execution：按配置执行模块，支持顺序、分支、并行和汇合。

开发文档：docs/EVENT_EXECUTION.md、docs/CORE_SIGNALS.md、docs/NODE_MODULES.md、docs/COMPONENT_MAP.md、docs/THIRD_PARTY_COMPONENTS.md，三个新组件 README 与 node_savepoint README，以及 NPC README 的模块表。它们用于开发与装配，不自动注入 NPC 上下文。
