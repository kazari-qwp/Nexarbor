# social.give · 通用同场赠送

挂在每个 Agent 上的“同场赠送”端点：每个实例公开一个 `give` 工具，代表**本节点这位收礼者**。
同场的其他可信 Agent 通过配置的赠送频道调用它，把**自己**的金币或物品转给这位收礼者；
一次成功赠送按配置扣除发送者行动值。组件不实现聊天、商店、借贷或网络初始化。

- 模块 ID：`social.give`
- 支持节点：`agent`
- 依赖：`entity.profile`（资料、金币、物品）、`action.points`（行动值）
- 公开工具：`give`（参数只有 `coins`、`items`）
- signals：无
- operations：无
- state：空对象，不记录欠债或赠送历史

## 接线方式

每个 Agent 节点都需要挂上实体资料、行动值和本组件。`give` 的收礼者就是
**工具所在节点**，所以发送者要通过赠送频道调用收礼者节点上的 `give`：

```python
backend.modules.mount('agent/alice', 'entity.profile', {
    'profile': {'name': '爱丽丝', 'place': 'place/square'},
})
backend.modules.mount('agent/alice', 'action.points', {'max': 10})
backend.modules.mount('agent/alice', 'social.give', {
    'channels': ['social.give'],
    'presence_channel': 'place.presence',
    'display_name': '爱丽丝',
})

backend.modules.mount('agent/bob', 'entity.profile', {
    'profile': {'name': '鲍勃', 'place': 'place/square'},
})
backend.modules.mount('agent/bob', 'action.points', {'max': 10})
backend.modules.mount('agent/bob', 'social.give', {
    'channels': ['social.give'],
    'presence_channel': 'place.presence',
    'display_name': '鲍勃',
})
```

再建立两类连接：

1. **赠送频道**：允许互相赠送的 Agent 之间用 `social.give` 连接（建议双向各建一条）。
   工具的访问频道就来自 `channels` 配置，频道交集与强度由网络核心检查。
2. **在场频道**：两个 Agent 各自与共同场所节点之间要有**双向**的 `presence_channel` 连接
   （人物 → 场所、场所 → 人物）。这与 `place.move` 建立/迁移的在场连接一致。
   只有 `profile.place` 相同，并且双方都满足“真实双向在场”时，赠送才成立：
   默认要求两个人物都与该场所节点双向相连；如果应用没有使用场所节点在场连接，也可以把
   发送者与收礼者在配置的赠送频道上**双向直达**作为在场证据。两种拓扑满足其一即可。

```python
alice = backend.network.nodes['agent/alice']
bob = backend.network.nodes['agent/bob']
square = backend.network.nodes['place/square']

alice.connect('agent/bob', channels=['social.give'], threshold=1)
bob.connect('agent/alice', channels=['social.give'], threshold=1)

square.connect('agent/alice', channels=['place.presence'], threshold=1)
alice.connect('place/square', channels=['place.presence'], threshold=1)
square.connect('agent/bob', channels=['place.presence'], threshold=1)
bob.connect('place/square', channels=['place.presence'], threshold=1)
```

`profile.place` 存的是场所节点 ID；移动组件改写这个字段并迁移在场连接即可“离开/到达”，
本组件不追人、不移动、不建立或删除任何连接。

## config

`example.json` 是一份可直接运行的配置。

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `channels` | string[]（≥1，不重复） | 是 | — | 赠送频道列表；工具声明为 `{"config":"channels"}`，由宿主编译成访问频道。 |
| `presence_channel` | string，非空 | 否 | `"presence"` | 判断“真实双向在场”的连接频道；应与 `place.move` 的 `presence_channel` 一致。 |
| `action_cost` | integer ≥ 0 | 否 | `1` | 每次成功赠送扣除发送者多少行动值；`0` 表示免费。 |
| `entity_module` | string，非空 | 否 | `"entity.profile"` | 提供 `profile`、金币与物品的依赖组件 ID。 |
| `action_module` | string，非空 | 否 | `"action.points"` | 提供行动值的依赖组件 ID。 |
| `place_field` | string，非空 | 否 | `"place"` | `profile` 中表示所在场所的字段名。 |
| `display_name` | string，非空 | 否 | — | 可选收礼者姓名；只在挂载时还读不到 `profile.name` 时用于工具描述。 |

依赖调用与实例差异全部来自配置或节点本身，代码里没有写死任何 NPC、场所或应用节点 ID。

## tools

| 名称 | 频道 | 参数 | 说明 |
| --- | --- | --- | --- |
| `give` | 配置字段 `channels` | `coins`（integer ≥ 1，可选）、`items`（物品名 → integer ≥ 1，可选） | 把自己拥有的资源送给本节点这位收礼者；`coins` 与 `items` 至少给一项。 |

- 工具描述在安装时生成，会写明**收礼者姓名**：姓名优先取收礼者当前 `profile.name`；
  如果本组件比 `entity.profile` 先挂载，则回退到 `display_name`，再回退到节点名。
- 模型只能填要送出的金币和物品，**不能填发送者身份**。发送者由
  `datanet.core.access_budget.current_agent_id()` 取得；没有可信调用者时直接拒绝。
- `items` 允许一次送多种物品，例如 `{"items": {"面包": 2, "火把": 1}}`。
- 送出的只能是发送者自己的资源；收礼者的物品与金币只会增加，不会被读取成发送者的库存。
- 0、负数、非整数、空物品对象、以及金币物品都不填的调用都会被拒绝。工具参数 schema 已限制
  最小值为 1，方法内部再检查一次，防止远端调用绕过 schema。

### 成功返回

```json
{
  "ok": true,
  "given": true,
  "reason": null,
  "message": "你已把 4 金币 和 面包×2 送给鲍勃，消耗 1 点行动值，剩余行动值 4/10。",
  "receiver": "鲍勃",
  "receiver_id": "agent/bob",
  "coins": 4,
  "items": {"面包": 2},
  "cost": 1,
  "remaining": 4,
  "max": 10
}
```

`coins` 是实际送出的金币（没送金币时为 `0`），`items` 是实际送出的物品，`remaining` 是发送者
扣除后的行动值，`max` 是行动值上限。成功返回中的资源数量与发送者、收礼者的真实余额变化一致。

### 失败返回

失败统一返回 `{"ok": false, "given": false, "reason": ..., "message": ...}`，不会改变任何人的
金币、物品或行动值：

| `reason` | 场景 |
| --- | --- |
| `no_caller` | 不在可信 Agent 调用上下文，拿不到发送者身份。 |
| `self_gift` | 调用者就是本节点这位收礼者。 |
| `invalid_coins` | 金币不是正整数。 |
| `invalid_items` | 物品不是“物品名 → 正整数”的对象，或物品名为空。 |
| `empty_gift` | 金币和物品都没有给出。 |
| `sender_profile_unavailable` | 读不到发送者资料。 |
| `sender_not_present` | 发送者没有非空的 `profile.place`，或人物节点不在网络里。 |
| `receiver_profile_unavailable` | 读不到收礼者资料。 |
| `not_same_place` | 收礼者没有 `place`，或与发送者的 `place` 不同。 |
| `place_unavailable` | `profile.place` 指向的场所节点不在网络里。 |
| `network_unavailable` | 无法读取网络节点表，不能确认现场连接。 |
| `sender_not_really_present` | 发送者既没有与该场所双向的 `presence_channel` 连接，也没有与收礼者在赠送频道上双向直达。 |
| `receiver_not_really_present` | 收礼者既没有与该场所双向的 `presence_channel` 连接，也没有与发送者在赠送频道上双向直达。 |
| `entity_unavailable` | 读取发送者的金币/物品失败。 |
| `entity_invalid` | 发送者的金币记录不是有效的非负整数。 |
| `insufficient_coins` | 发送者金币不够。 |
| `insufficient_items` | 发送者某种物品数量不够。 |
| `insufficient_action` | 行动值不够 `action_cost`；消息沿用 `action.points` 的拒绝说明。 |
| `dependency_unavailable` | 实体资料或行动值组件不可用。 |
| `transfer_failed` | 资源调整失败（少见）；核心短事务会回滚，已取消本次赠送。 |

`insufficient_coins`、`insufficient_items` 等失败会带上 `receiver` / `receiver_id`，方便调用方
直接复述给模型。拒绝不会自动重试，也不会替发送者记账。

## 原子性

一次成功赠送在核心的短事务中完成：

1. 先校验双方资料、场所、真实在场，以及发送者的金币与物品是否足够；任何一项不满足都在
   改动前返回。
2. 进入 `backend.modules.transaction(sender_id, receiver_id)`。
3. 调用 `action.points.spend` 扣发送者行动值；不足则拒绝，不进入资源调整。
4. 调用 `entity.profile.adjust` 扣发送者金币/物品。
5. 调用 `entity.profile.adjust` 加收礼者金币/物品。

事务只包住这几步同步修改，不跨模型等待。任一步抛错时，发送者与收礼者节点上的模块状态
一起回滚，不会出现“行动值扣了但东西没送出去”或“只扣了发送者、没加到收礼者”的半成品。

## 依赖操作

只通过 `backend.modules.call` 调用清单中声明的依赖，不直接读写其他组件的状态：

| 依赖 | 操作 | 用途 |
| --- | --- | --- |
| `entity.profile`（或 `entity_module`） | `read` | 读取双方 `profile`、发送者金币与物品。 |
| `entity.profile`（或 `entity_module`） | `adjust` | 扣发送者资源、加收礼者资源；由依赖组件保证单次调用内不出现负库存。 |
| `action.points`（或 `action_module`） | `spend` | 先校验再扣除发送者行动值；返回 `ok=false` 时整个赠送取消。 |

本组件自身没有 `operations`，不向其他组件暴露操作。

## state 与 signals

- `state_schema` 是空对象：不保存欠债、赠送记录或冷却时间。余额和物品在依赖组件里，
  赠送历史可由应用层另行记录（本组件不做）。
- `signals` 为空：不响应 `world.tick` 等信号，不生成或传播信号；何时赠送完全由 Agent 决定。

## 借钱与聊天

本组件**不实现**借钱、赊账或自动欠债。需要借钱时，由一方通过聊天/消息组件提出请求，
另一方在愿意时主动调用 `give` 把金币送过来；是否归还、何时归还都由双方后续自行决定，
本组件只记录当次真实转移，不生成债务关系。

同理，本组件不实现聊天、商店、任务、移动或网络初始化。需要别的组件时，由装配者组合。

## 限制

- 在场判断依据两个条件：双方 `profile.place` 是相同的非空字符串，并且双方满足下面两种
  真实双向连接之一：各自与那个场所节点之间都有双向的 `presence_channel` 连接；或者双方
  在配置的赠送频道上互相直达。只改 `profile.place` 而没有真实连接，或只有单向连接，都会被拒绝。
- 工具描述在安装时固定；之后收礼者改名不会自动刷新描述（赠送结果里的姓名使用调用时读到的值）。
- 一次调用只送给当前实例所在节点的这一位收礼者，不做群发/广播；要送多人就分别调用各自节点。
- 先扣行动值再调整资源；若资源调整失败，核心事务会回滚已扣的行动值。
- 物品名按去掉首尾空白后的字符串匹配库存；送出的物品数量不能超过发送者持有量。
- 依赖的 `entity.profile`、`action.points` 必须挂在对应 Agent 节点上；缺失或不可用时返回
  `ok=false`，不会改一半。
- tests/test_module.py 使用 unittest 覆盖成功赠送金币/物品/两者、0 与负数、空赠送、给自己、
  不同场所、单向在场、资源不足、行动值不足、事务回滚、配置化频道/字段/依赖 ID 与描述回退等场景。
