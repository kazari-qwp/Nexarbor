# 模块图执行器

模块 ID：`modules.executor`；组件：`capabilities/module_graph`。使用当前 v3 固定入口。依赖并复用已有 `capabilities/langgraph_backend`（官方 LangGraph 1.2.16），不加载旧的 module_execution/event_trigger 服务，也不迁移旧应用。

权限网络决定本组件能够调用哪些模块；组件内的 LangGraph 执行图决定按什么流程调用。每一步始终使用 `ctx.network.call`，没有原始宿主对象或任意函数引用。每次执行的中间结果独立，多个请求可以并发运行。

## 两种激活方式

**调用**：显式调用本模块的 `run` 操作，例如 `await ctx.network.call("flow", "modules.executor", "run", {"graph":"main", "input":{"value":7}})`。框架检查图路径、频道和强度，然后给固定入口传入 `activation.kind="access"`。run 的公开频道为 workflow。省略 graph 时使用 default_graph，省略 input 时使用空对象。

**信号**：框架收到信号后，按本实例 `config.signal_channels` 匹配，被动进入同一 execute 入口，kind 为 signal。随后按 on_signal 规则的 kind、channels 和 where 匹配执行图。规则按配置顺序执行；流程全部结束后，本组件才算完成信号处理，核心才继续下一层传播。不轮询，也不额外发送 ready。

清单的 `signals:{"config":"signal_channels"}` 是通用的按实例配置响应频道机制；固定频道数组仍可使用。频道在装配时解析，更改后需重新应用网络。它只决定响应，不增加模块对外访问权限。

## 配置示例

下面两步调用同一个工具收集器。工具收集器需要先装在 flow 节点；差异完全由配置表达。

```json
{
  "config": {
    "operations": {
      "tools": {"module":"tools.collector", "operation":"collect"}
    },
    "graphs": {
      "main": {"type":"sequence", "steps":[
        {"type":"call", "id":"first", "operation":"tools", "arguments":{}},
        {"type":"call", "id":"second", "operation":"tools", "arguments":{}}
      ]}
    },
    "default_graph":"main",
    "signal_channels":["workflow"],
    "on_signal":[{"graph":"main", "kind":"workflow.run"}],
    "timeout_seconds":60
  },
  "state":{},
  "access":{"strength":2,"channels":["tools"]}
}
```

operations 是可执行操作的配置表，不接受函数或 Python 表达式。每项必须包含 module、operation，可选 node（省略为本节点）、channels、strength、require_success。指定 node 只是目标数据，仍需实际可达。收窄 channels/strength 可以，超过本实例装配授权会被拒绝。被调用模块进入后使用它自己的授权。

## 流程与数据

- call：执行一个操作别名。每个步骤 id 唯一；相同模块可以出现多次。
- sequence：依次执行 steps。
- parallel：同时执行 steps，所有已启动分支完成后汇合。
- branch：按 select 的结果选择 cases 中的一项，否则运行 default。未选择分支不执行、不参与汇合。字符串直接匹配，数字与 true/false/null 使用 JSON 写法。

四种执行块可以嵌套；顺序、分支和汇合使用真实 LangGraph StateGraph。客户端模块页复用已有“可视化执行图”编辑器。

`{"$ref":"/event/input/value"}` 引用当前输入；`{"$ref":"/results/first/value/data"}` 引用 first 步骤返回的 ComponentResult.data。遵循 JSON Pointer，支持数组下标和 ~0/~1 转义。纯数据引用，不执行表达式。

访问事件包含 kind/source/input/signal/delivery；访问的 signal/delivery 为 null。信号事件的 input 是信号 content，另外提供完整 signal 和 delivery。where 是 JSON Pointer 到期望值的相等匹配表，例如 `{"/input/enabled":true}`；缺少字段不匹配。

返回 ComponentResult.data：`{"matched":1,"executions":[{"graph":"main","results":{...}}]}`。每个步骤结果保留完整 ComponentResult 封套，便于分支判断 status 或读取 data。

默认 require_success=true，模块返回 error 时流程停止。设为 false 后可对 `/results/step/value/status` 分支处理。配置结构错误、重复步骤 ID、未声明的操作会在执行前拒绝；每一步仍实时检查网络权限。timeout_seconds 限制本次流程时间，超时取消相关异步访问。执行器不另建数据库或模型会话，沿用核心持久化；未实现从流程中途恢复。

## 验证

覆盖同模块重复调用、不同节点实例、输入与结果引用、条件默认分支、布尔/null 分支、真正并行与汇合、并发调用隔离、调用/信号入口、按实例配置频道、信号层等待、权限拒绝、错误分支与超时取消。

桌面实测通过“执行图→收集器→Harness 官方 read”；调用和脉冲两个入口均完成，并验证脉冲在执行图完成后闭环。客户端编辑器及组件工作副本验证也纳入验收。无付费模型调用。

后端依据：[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。

验收记录（2026-10-18）：89 项相关核心测试、11 项前端测试通过；真实桌面验证覆盖调用/信号入口、脉冲闭环、官方 read、可视化图编辑器及工作副本验证。结果：build/module-graph-1792299902557/verification.json。付费模型/API 调用为 0。
