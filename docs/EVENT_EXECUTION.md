# 可配置模块执行图

普通模块用 `execute(ctx, activation)` 响应显式调用或清单声明的信号。需要把已有操作组合成流程时，可装配通用 `modules.executor`；组件为 `capabilities/module_graph`，依赖 `capabilities/langgraph_backend`，核心不导入 LangGraph。

模块配置包含 operations、graphs、可选 default_graph 和 on_signal。operations 为受授权的目标节点、模块、操作及频道；graphs 描述 sequence、parallel、branch 和 call。普通调用使用 run(graph,input)；on_signal 按信号种类、频道和 where 条件选择图。完整 Schema 和示例见 [模块清单](../extensions/foundation/capabilities/module_graph/module.json)。

```json
{
  "operations": {
    "read": {"module":"records.store","operation":"read","channels":["records"]}
  },
  "graphs": {
    "main":{"type":"call","id":"read","operation":"read","arguments":{}}
  },
  "default_graph":"main"
}
```

sequence 依次执行，parallel 等全部子项完成，branch 根据 JSON Pointer 选择分支。call 的 id 唯一；引用只读取当前输入与已完成结果，不依赖尚未完成的并行兄弟。配置不执行任意 Python 代码或无限循环，需要反复触发时由显式信号或脉冲组织。

模块图调用仍经 `ctx.network.call` 检查频道和强度。默认下游错误会中止并上报；信号源不能借流程扩大接收者授权。不要为了减少模块数量把独立机制合并进一个复杂业务组件，能直接调用简单模块时无需增加执行图。
