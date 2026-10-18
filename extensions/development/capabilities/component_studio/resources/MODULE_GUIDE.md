# Fixed component protocol v3

Entry: `async def execute(ctx, activation) -> ComponentResult`. No extra parameters/defaults. Manifest entry is `module.py:execute`, format `nexarbor-module/v3`. Declare operations with name, channels, parameters (object JSON Schema), result (data JSON Schema); declare signal channels separately. Config/state schemas are checked at mount and after execution.

Activation has kind (`access`/`signal`), operation, immutable parameters, core-bound source and request_id; signal activations also have immutable signal/delivery. Parameter values are data, never permission. Return `ComponentResult(data=...)` or `ComponentResult(status='error', error='...')`. No arbitrary callbacks or direct backend/node objects.

`ctx.config`, `ctx.state`, `ctx.metadata()`, `ctx.read(request)`, `ctx.write(key,value)`, `ctx.publish_metadata(fields)`, `ctx.update_inputs(patch)` are local. Document paths cannot be loaded by ordinary modules.

`ctx.network.nodes(channels=..., strength=...)`, `.metadata(target,...)`, `.visit(target,...)`, `.tools(target,...)` follow graph paths. `.call(target,module,operation,arguments,...)` and `.invoke(target,tool,arguments,...)` schedule independent tasks immediately; await required results. The callback joins all its access tasks before completion. Same-node calls cost zero hops. Forwarding is allowed; the callee uses its own mount grant, not the caller's remaining strength. Source identity cannot be supplied through arguments. Do not recursively call without a termination condition.

`.emit(channels=...,strength=...,content=...,kind=...)` returns a signal receipt immediately. `.signal_status(id)`, `await .wait_signal(id)`, `await .cancel_signal(id)` manage own-node signals. Do not wait for a signal that needs the current receiver to finish. Signals retain their channels, process each breadth-first layer concurrently, then wait for every receiver before continuing. Emitted signals survive the caller's completion/cancellation while the core is running.

Node offered_tools are registered external tool references, separate from component operations. An Agent visit acquires them; execution rechecks current graph access. Terminal tools are explicit host capabilities, not ordinary local modules.

An explicit `tool_provider` manifest entry maps `list` and `invoke` to declared operations. `list({})` returns descriptors with id/name/description/parameters; `invoke({tool_id,arguments})` executes through the component's own network authority. The Agent adapter installs only these explicitly provided tools. `ctx.network.tool_sources(target,...)` discovers accessible providers without exposing instances. `network.tools` is a read-only query; it does not install tools. The standard `tools.collector` demonstrates chaining and origin-based deduplication; it currently adds no collector cycle detection.

Module code is trusted Python. Contract checks and API locality do not create an OS sandbox. Missing authority is reported, never bypassed with filesystem/import/process tricks.

模块清单的 signals 还可使用 `{"config":"signal_channels"}`：框架从本实例 config 的对应字段读取频道数组，在装配时绑定。空数组表示只通过访问激活。不要把信号中携带的频道当成模块的新访问授权。标准模块 `modules.executor` 演示调用/信号双入口以及通过已有 LangGraph 后端运行配置化流程；模块步骤仍使用 network.call，不能接受任意 Python 函数或表达式。
