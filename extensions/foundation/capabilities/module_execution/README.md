# 模块执行器

按配置执行模块，支持顺序、分支、并行和汇合。

复用官方 LangGraph，不自行实现图调度器。结构化配置包含 call/sequence/parallel/branch，支持嵌套；parallel 在全部已启动子图完成后汇合。branch 只选择一个子图，不等待未选择的分支。

节点模块 `modules.executor` 与运行时程序接口提供相同执行能力。只能运行宿主授予的操作，状态按调用隔离，模块自身状态继续保存在节点上。详见 [执行图接口](../../../../docs/EVENT_EXECUTION.md)。
