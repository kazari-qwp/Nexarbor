# action.points — 通用行动值

挂在 Agent 节点上的通用行动值余额。每个新时刻恢复到配置上限，其他组件可以先用内部操作检查余额，再扣除指定消耗；余额不足时明确拒绝且不扣。组件本身不含移动、挖矿或任何具体业务。

## 挂载与配置

- 模块 ID：`action.points`
- 支持节点：`agent`
- 配置字段：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `max` | integer ≥ 0 | `10` | 每个新时刻恢复到的行动值上限，也是新挂载实例的初始余额。 |

示例配置（见 `example.json`）：

```json
{"max": 10}
```

首次挂载（状态为空）时余额直接按上限初始化；恢复已有状态时保留余额。`max` 为 `0` 时该 Agent 永远没有可扣除的行动值。

## 信号与“时刻”

- 响应频道：`world.tick`。
- 收到一条新的 `world.tick` 信号（`signal_id` 与上一条不同）时，`remaining` 恢复为 `max`，并记录该 `signal_id`。
- 同一 `signal_id` 重复投递不会重置、不会改变状态，返回 `changed=false`；这覆盖核心重投或重复回调的情况。
- 新信号即使 `content` 与上一条相同，也按新时刻处理；时刻身份以核心提供的 `signal_id` 为准，不按消息内容去重。
- 频道交集与强度由网络核心检查，本组件不实现传播或强度判断，也不主动生成信号。装配时需要把产生新时刻的时钟/脉冲节点的 `world.tick` 频道以足够强度接到该 Agent 节点，组件才会收到时刻信号。

`on_signal` 的返回值形如：

```json
{"changed": true, "remaining": 10, "max": 10, "message": "新时刻，行动值恢复为 10/10。"}
```

重复同一信号时 `changed` 为 `false`，`message` 形如 `重复时刻，行动值保持 3/5。`

## 内部操作

这些操作只供可信组件通过 `backend.modules.call` 调用，不会自动变成 Agent 工具。所有返回值都是可 JSON 序列化的对象，且都带 `remaining`、`max` 和一句包含“剩余多少”的 `message`，调用方可以直接把 `message` 放进自己的提示或拒绝回复。

| 操作 | 参数 | 成功返回 | 说明 |
| --- | --- | --- | --- |
| `get_balance` | 无 | `{ok, remaining, max, message}` | 查看当前余额。 |
| `check` | `amount`：integer ≥ 0 | `{ok, amount, remaining, max, message}` | 只检查是否够扣，不改变状态；`ok=false` 表示不足。 |
| `spend` | `amount`：integer ≥ 0 | 成功：`{ok:true, amount, spent, remaining, max, message}`；不足：`{ok:false, reason:"insufficient", amount, spent:0, remaining, max, message}` | 先校验再扣除。余额不足时明确拒绝且不扣；`spent=0` 表示本次没有扣除。 |

补充：

- `amount` 由 JSON Schema 限制为大于等于 0 的整数；负数、非整数或多余参数会在进入方法前被拒绝。
- `amount=0` 的 `check`/`spend` 是安全的空操作。
- `spend` 在同一次调用内完成“检查 + 扣除”，是权威判断；`check` 的结果可能被同一时刻后续的扣除改变，调用方应以 `spend` 的返回为准。
- 返回中的 `remaining` 是扣除后的余额；失败时是未变的余额。

### 调用示例

```python
# agent_id 由装配者按网络配置传入，组件不写死任何节点 ID。
balance = backend.modules.call(agent_id, 'action.points', 'get_balance', {})
checked = backend.modules.call(agent_id, 'action.points', 'check', {'amount': 3})
if not checked['ok']:
    return checked['message']  # 例如：行动值不足：需要 3，剩余 2/10。

result = backend.modules.call(agent_id, 'action.points', 'spend', {'amount': 3})
if not result['ok']:
    return result['message']  # 例如：行动值不足：需要 3，剩余 2/10，未扣除。
```

## 工具

`tools` 为空。本组件不占用 Agent 的公开工具名，也不新增远端工具频道；余额的查看与消耗统一走上面的内部操作，由其他组件把返回的 `message`/`remaining` 带入自己的提示。如果装配者需要一个由 Agent 自己调用的工具，应在应用层另行决定，不应把节点 ID 或业务规则写进本组件。

## 状态

`state_schema` 只有两个字段：

| 字段 | 说明 |
| --- | --- |
| `remaining` | 当前剩余行动值，整数 ≥ 0。 |
| `last_signal_id` | 最近计入的新时刻信号身份，字符串或 `null`；用于忽略同一信号的重复投递。 |

状态随节点模块一起持久化。恢复时保留已存余额；如果恢复时的 `max` 比余额小，余额会被裁剪到新的上限，避免出现超过上限的余额。`last_signal_id` 也会恢复，因此重启后重投同一条信号仍不会重复重置。

## 限制

- 只有 `world.tick` 会触发恢复。若应用使用别的时刻频道，需要让产生新时刻的时钟/脉冲节点发射 `world.tick`；组件不会自行计时，也不接受按配置改信号频道（清单中的 `signals` 是静态声明）。
- 组件不生成时刻、不传播信号，也不判断频道交集或强度。
- 所有实例差异通过 `max` 配置；组件不感知具体 NPC、场所或应用节点 ID。
- 不包含移动、挖矿等业务；何时扣除、扣多少由调用组件决定。
