# 请求尾部与工具控制

prepare 模块返回 `nexarbor-context/v1` 的 `patch.tail` 文本。Harness 适配器仅在请求尾部将明确写出的 `{{request.count}}`、`{{request.limit}}` 替换为当前本次执行的模型请求次数、执行绑定的 max_steps。普通文本不变；不注入轮次、时钟或业务提示。请求计数先增加，再渲染尾部；新一次 agent_run 重置计数。

工具可返回 `{"format":"nexarbor-tool-control/v1","conclude":true,"data":...}`，适配器结束本次原生 turn，并将 data 呈现为工具结果。讨论的提交/跳过、协作的提出/批准候选由各自项目模块选择使用；核心不包含这些业务规则。
