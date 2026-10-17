# agent.activity · Agent 活动组件

挂在 **Agent 节点**上。每当节点收到 `world.tick`，组件把配置的提示语交给框架原生 Agent 执行端口 `backend.execute_agent(node_id, message=...)`，并等待这次执行正常结束。

组件本身不实现模型循环、工具装配或任何角色/场所逻辑；工具可达性、频道交集与信号强度都由网络和核心负责。提示语、Agent 的人格与四路输入、工具权限全部来自节点配置和现有输入通道。

## 挂载前置条件

- 节点类型必须是 `agent`。
- 节点需配置原生执行器，例如：
  ```json
  "execution": {"executor": "harness", "strength": 2, "max_steps": 12, "timeout_seconds": 90}
  ```
  未配置 `executor: harness` 时，执行端口会报错，本组件不会登记这次信号。
- 网络必须把 `world.tick` 以足够强度送到该节点；本组件不建立连接、不改频道、不做传播。

## config

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string（非空） | 是 | 每次触发时发给原生 Agent 执行端口的提示语。 |
| `max_history` | integer ≥ 1 | 否 | 保留多少个最近成功处理的 `signal_id` 用于去重，默认 `256`。 |

示例配置见 `example.json`；它只包含本组件自身配置，不包含节点或整张网络。

## signals

- `world.tick`：响应入口。只有信号频道与 `world.tick` 有交集时才会调用 `on_signal`。

## tools / operations

- tools：无。本组件不向 Agent 暴露任何工具。
- operations：无。其他组件不需要调用本组件。

## state

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `processed_signal_ids` | string 数组 | 最近成功执行过的 `signal_id`，从旧到新，最多保留 `max_history` 个。 |
| `last_signal_id` | string 或 null | 最近一次成功执行对应的 `signal_id`；从未成功时为 `null`。 |
| `completed_count` | integer ≥ 0 | 累计成功执行次数。 |

`setup()` 只在状态缺失时补齐上述字段，不覆盖已有存档。

## 行为与返回值

1. 读取 `context.signal.signal_id`。
2. 如果该 `signal_id` 已在 `processed_signal_ids` 中，直接返回
   `{"status": "duplicate", "signal_id": ...}`，不调用执行端口，也不改动状态。
3. 否则 `await backend.execute_agent(self.node.node_id, message=配置的 message)`。
4. 执行端口正常返回后，登记 `signal_id`、更新 `last_signal_id` 和 `completed_count`，返回
   `{"status": "completed", "signal_id": ..., "completed_count": ...}`。

只有执行端口正常结束才算完成；没有工具调用、Agent 正常收尾同样计为完成。执行端口抛出的异常原样交给框架：这次信号不会登记为成功，状态保持触发前的值，下一次同一 `signal_id` 仍会重试执行。

## 限制

- 只对 `world.tick` 作出响应，不处理其他频道。
- 提示语按配置原样发送，不做占位符替换；需要动态现场资料时，请用节点的四路输入或 `execution.prepare` 刷新。
- 去重只记住最近 `max_history` 个成功信号；早于该窗口的旧 `signal_id` 不再拦截。
- 组件不创建节点、不建立连接、不实现 NPC 行为，也不使用 submit 一类工具。
