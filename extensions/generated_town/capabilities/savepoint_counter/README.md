# savepoint.counter · 通用计数存档

挂在普通节点（`node`）上的通用计数器：每收到一个**新的** `world.tick` 信号计数一次，每累计 `interval` 次就请求一次全量存档。它不初始化整张网络，也不处理 NPC 收尾。

## 装配

- 组件 ID：`savepoint.counter`
- 可挂载节点类型：`node`
- 依赖：无
- 状态：`count`（累计计数）、`last_signal`（最近一次计入的 `signal_id`）、`recent_signals`（最近计入的信号 ID 列表，最多 128 条，用于识别非连续重复）

## config

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `interval` | 正整数 | `5` | 每计数多少次请求一次全量存档。 |

示例：

```json
{"interval": 5}
```

## signals

响应频道：`world.tick`。

核心每把该频道的信号投递到本节点，就会调用一次响应入口：

- 用 `context.signal.signal_id` 判断是否为新信号；已在 `last_signal` 或 `recent_signals` 中的信号不会重复计数，状态也不变。
- 新信号使 `count + 1`，并记录 `last_signal`。
- 当 `count` 能被 `interval` 整除时，调用 `backend.dispatch("save", {"full": true})` 请求全量存档。
- 返回值：`{"count": 当前计数, "full_snapshot": 本次是否请求了全量存档, "reused": 是否为重复信号}`。重复信号返回 `reused: true` 且不触发存档。

频道交集与到达强度由网络核心负责，组件本身不重复实现传播或强度检查。

## operations（内部操作）

其他可信组件通过 `backend.modules.call(node_id, "savepoint.counter", "get_count", {})` 读取当前计数。这些操作不会自动变成 Agent 工具。

| 名称 | 参数 | 返回 |
| --- | --- | --- |
| `get_count` | 无（`{}`） | `{"count": 整数, "last_signal": 字符串或 null, "interval": 当前间隔}` |

## tools

无。本组件不向 Agent 暴露工具；读取计数请使用上面的内部操作。

## 行为边界

- 只判断信号身份是否重复，不读取 `content`；相同内容的不同信号仍各计一次。
- 去重窗口为最近 128 个 `signal_id`。更早的 ID 再次到达时会被当作新信号（正常情况下核心不会重复投递同一信号给同一节点）。
- 存档请求只负责调用 `dispatch("save", {"full": true})`；快照的写入与失败处理由核心的存档流程负责。
- 收到同一信号时不会写状态，也不会重复请求存档。
