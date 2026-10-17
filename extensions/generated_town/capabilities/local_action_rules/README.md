# local.action_rules · 配置驱动的本地行动规则

挂在**业务地址节点**上的通用行动入口，只公开一个 `act(action, quantity=1)` 工具。
挖矿、砍树、修理、休息、商店交易、酒馆消费等具体业务全部写在实例的 `rules` 配置里；
组件代码不写死任何 NPC、场所、动作或应用节点 ID，也不包含移动、家庭或模型循环逻辑。

- 模块 ID：`local.action_rules`
- 支持节点：`node`（普通业务节点）
- 依赖：`entity.profile`（资料、金币、物品）、`action.points`（行动值）
- 公开工具：`act`
- 信号：无
- operations：无

频道的交集与强度由网络核心负责，本组件不重新实现传播；组件只检查自己负责的业务前提。

## 接线方式

```python
# 1) 业务地址节点挂本组件
backend.modules.mount('place/square', 'local.action_rules', {
    'address': 'place/square',
    'channels': ['act.local'],
    'entity_module': 'entity.profile',
    'action_module': 'action.points',
    'rules': {
        'mine': {
            'description': '在矿脉挖掘铁矿石',
            'cost': 1,
            'requires_items': {'镐': 1},
            'requires_profile': {'adult': True},
            'actor': {'items': {'铁矿石': 2}},
            'place': {'items': {'矿脉': -1}},
        },
    },
})

# 2) 人物节点挂资料与行动值
backend.modules.mount('agent/alan', 'entity.profile', {
    'profile': {'name': '阿岚', 'adult': True, 'home': 'place/home'},
    'coins': 10,
    'items': {'镐': 1},
})
backend.modules.mount('agent/alan', 'action.points', {'max': 10})

# 3) 人物与业务地址之间建立**双向**、共用同一行动频道的在场连接
backend.network.nodes['agent/alan'].connect(
    'place/square', channels=['act.local'], threshold=1
)
backend.network.nodes['place/square'].connect(
    'agent/alan', channels=['act.local'], threshold=1
)
```

`example.json` 是一份完整示例配置，演示挖矿、砍树、修理、在自己家休息、商店买面包与酒馆消费。

## config

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `address` | string，非空 | 是 | — | 这个业务所在地址的节点 ID。执行者的变化写到调用者节点，地点变化写到该地址节点。 |
| `channels` | string[]，非空 | 是 | — | `act` 工具的访问频道，同时也是双向在场连接必须共用的行动频道。 |
| `entity_module` | string，非空 | 否 | `entity.profile` | 实体资料与物品组件 ID。 |
| `action_module` | string，非空 | 否 | `action.points` | 行动值组件 ID。 |
| `rules` | object，非空 | 是 | — | 动作名到规则定义；键就是 `act` 的 `action`。 |
| `events_ref` | object | 否 | — | `{node, module}`：成功动作后抽取概率事件的组件实例。 |

### rule

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `description` | string，非空 | 是 | 简短说明，会进入工具描述的动作菜单。 |
| `cost` | integer ≥ 0 | 是 | 行动消耗基数。默认整单只按一次 `cost` 计费；`cost_per_unit=true` 时表示每单位消耗。 |
| `cost_per_unit` | boolean | 否 | 默认 `false`：交易整单只扣一次 `cost`；`true`：实际消耗 `cost × quantity`。 |
| `requires_items` | object：物品名 → integer ≥ 0 | 否 | **每单位最低持有量**；本次共需 `每单位最低持有量 × quantity`，检查执行者物品。 |
| `requires_profile` | object | 否 | 执行者资料字段的**等值**检查。用于“仅成年人工作”“只能在自己家休息”等前提。 |
| `actor` | effects | 否 | 执行者的金币、物品与资料变化。 |
| `place` | effects | 否 | 业务地址的库存、金币与资料变化。 |
| `event_trigger` | string，非空 | 否 | 成功后传给概率事件 `draw` 的触发名；省略时取 `action`。 |

`effects` 使用 `entity.profile.adjust` 的 `coins` / `items` / `fields` 结构：

```json
{"coins": -2, "items": {"面包": 1}, "fields": {"mood": "满足"}}
```

- `coins` 与每个 `items` 增量可以是负数，按 `quantity` **倍增**；
- `fields` 不倍增、不转换，原样合并写入资料；
- 先检查执行者与地点的金币/物品够不够扣，任何一项不足都不会改一半；
- `requires_items` 只检查执行者，不检查地点库存；地点扣减不足由 `place` 的金币/物品检查拒绝。
- 行动消耗由 `cost_per_unit` 决定：默认按整单 `cost` 计费，适合交易一次买多份仍只收一次手续；
  设为 `true` 时按 `cost × quantity` 计费，适合挖矿、砍树等按件计酬。实际消耗会用于余额检查、
  扣费、成功返回的 `cost`、以及不足时的拒绝说明。

## 调用者与在场前提

- 调用者身份取自 `datanet.core.access_budget.current_agent_id()`，**不是**模型可填的参数。
  没有可信调用者时直接拒绝。
- 调用者必须真实在 `address`：调用者 → 地址、地址 → 调用者两个方向都必须存在直接连接，
  且两个方向的连接与配置 `channels` 至少共用一个频道。只有单向连接、频道不一致或跨地点都会拒绝。
- 在 `entity.profile` / `action.points` 中读取不到执行者或地点资料时拒绝，不改任何状态。
- 本组件不判断频道强度，也不沿多跳路径推断在场；在场只看直接双向连接。

## 执行顺序与原子性

1. 校验 `action` 是否在 `rules` 中，`quantity` 是否为 1 到 100 的整数。
2. 校验调用者身份、双向在场与共用频道。
3. 读取执行者与地址的资料/金币/物品，检查 `requires_profile`、`requires_items`。
4. 计算 `actor` / `place` 两组变化（金币、物品按数量倍增），检查扣减后都不为负。
5. 按规则计算实际行动消耗（`cost_per_unit=false` 时为 `cost`，为 `true` 时为 `cost × quantity`）；
   检查执行者行动值是否够扣；不足直接拒绝，不进入事务。
6. 在 `backend.modules.transaction(调用者, 地址, 事件节点)` 中：扣行动值、写执行者变化、
   写地点变化；如果配置了 `events_ref`，再抽取概率事件并结算事件效果。
7. 任何一步抛错都会回滚调用者、地址与事件节点的模块状态（包括已扣行动值和事件命中计数），
   返回 `ok=false`，不会“改一半”。

## 概率事件（可选）

配置 `events_ref: {"node": "place/square", "module": "chance.events"}` 后，成功动作会调用：

```python
backend.modules.call(events_node, events_module, 'draw', {
    'trigger': rule.get('event_trigger') or action,
    'context': {'action': action, 'quantity': quantity,
                'actor': caller, 'address': address},
})
```

- 返回的 `events` 会原样放进工具结果的 `events`，其中的 `message` 也会拼进主 `message`。
- 事件 `effects` 若含 `coins` / `items` / `fields`，会按同样结构通过 `entity.profile.adjust`
  应用到**执行者**（不按动作数量倍增）；没有这三类键的事件视为纯传闻，只返回文字。
- 事件组件的命中计数也在同一个短事务里；后续结算失败会连计数一起回滚。
- 没有配置 `events_ref` 时不抽取任何事件。

## tools

| 名称 | 频道 | 参数 | 说明 |
| --- | --- | --- | --- |
| `act` | 配置字段 `channels` | `action`（string，必填）、`quantity`（integer，1–100，默认 1） | 在本地址执行一条配置好的动作。 |

工具描述在安装时根据本实例 `rules` 生成动作菜单，包含每个动作的说明、行动消耗、
每单位物品要求与资料要求，NPC 不需要额外查询动作表。

### 成功返回

```json
{
  "ok": true,
  "reason": null,
  "message": "「mine」已完成 ×2，消耗 1 点行动值，剩余 7 点。",
  "remaining": 7,
  "action": "mine",
  "quantity": 2,
  "cost": 1,
  "events": [],
  "changes": {
    "actor": {"coins": 0, "items": {"铁矿石": 4}, "fields": {}},
    "place": {"coins": 0, "items": {"矿脉": -2}, "fields": {}}
  }
}
```

`changes` 是本次执行者与地点实际变化的简明汇总；`remaining` 是扣除后的行动值，
`cost` 是本次实际扣除的行动值（启用 `cost_per_unit` 时已乘以 `quantity`）。

### 失败返回

```json
{
  "ok": false,
  "reason": "insufficient_items",
  "message": "物品不足：每单位需要「镐」×1，本次共需 2，当前持有 1。",
  "remaining": 8,
  "action": "mine",
  "quantity": 2,
  "events": [],
  "changes": {}
}
```

失败时 `message` 明确说明原因与当前行动值余额；`remaining` 在无法读取行动值时是 `null`。
常见 `reason`：`no_caller`、`invalid_quantity`、`invalid_action`、`unknown_action`、
`not_present`、`profile_requirement`、`insufficient_items`、`insufficient_coins`、
`insufficient_action`、`entity_unavailable`、`action_unavailable`、
`event_unavailable`、`event_effect_failed`、`internal_error`。

## signals / operations

- `signals` 为空：本组件不响应、不生成信号，也不修改信号传播。
- `operations` 为空：不向其他组件暴露操作；依赖组件的公开操作由装配者直接使用。
- `state` 是空对象：业务状态都在 `entity.profile`、`action.points` 与事件组件里，重挂载或读档不会重置。

## 示例配置覆盖的业务

`example.json` 的 `place/square` 配置演示了：

- `mine`：需要镐与成年资料，执行者得铁矿石，地点矿脉减少；
- `chop`：需要斧头与成年资料，执行者得木材，地点林木减少；
- `repair`：需要木材与工匠资料，执行者消耗木材、得到修好的工具；
- `rest`：要求 `profile.home` 等于配置的家地址，资料写入休息状态；
- `buy_bread`：执行者付金币得面包，地点收金币减库存；
- `tavern_drink`：执行者付金币、资料写入微醺，地点收金币，并通过 `event_trigger` 抽取酒馆传闻。

这些只是装配演示；实际业务通过修改 `rules` 配置完成，不需要改组件代码。

## 限制

- 不实现移动、寻路、家庭关系、模型循环或 Agent 调度；只负责一次本地动作的校验与结算。
- 不恢复行动值；行动值由 `action.points` 的 `world.tick` 逻辑管理。
- 不做多跳可达性判断；在场只认调用者与业务地址之间的直接双向连接。
- 不检查“这个调用者是否应该拥有这个工具”；工具可达性由宿主的频道与权限决定，业务前提由本组件检查。
- 事件效果只认 `coins` / `items` / `fields` 三种键；其他形状按纯传闻处理，不落地资源变化。

## 测试

`tests/test_action_rules.py` 使用假的资料、行动值与事件依赖覆盖：成功按数量倍增、
默认整单行动消耗不倍增、`cost_per_unit=true` 时按实际 `cost × quantity` 检查/扣费/返回、
缺钱/缺货、行动值不足、负数量与超范围数量、跨地点与单向连接、
仅自己家休息的资料等值检查、地点库存不足时的原子回滚、事件效果结算与事件计数回滚。
