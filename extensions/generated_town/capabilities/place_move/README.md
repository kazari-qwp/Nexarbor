# place.move · 通用地点移动

挂在**地址节点**上的通用移动入口，公开一个**不带参数**的 `move_here` 工具：人物调用它就表示
“移动到本地点”。移动的前提、花费、在场连接迁移和可选的到达见闻都在本组件内完成，
不包含商店、场所业务或整张地图。当前版本 `1.0.1`。

## 挂载与依赖

- 模块 ID：`place.move`
- 支持节点：`node`（普通地址/场所节点）
- 依赖（`requires`，需装配者先加载；`entity.profile`、`action.points` 挂到人物节点，
  `chance.events` 只在配置了 `events_ref` 时需要挂到被引用的节点）：`entity.profile`、`action.points`、`chance.events`
- 每个地点节点各挂一个实例；人物身份由 `current_agent_id()` 决定，不是模型可填的参数。

```python
backend.modules.mount('place/广场', 'place.move', {
    'place_name': '中央广场',
    'cost': 3,
    'channels': ['move.access'],
    'road_channels': ['road'],
    'presence_channel': 'presence',
    'entity_module': 'entity.profile',
    'action_module': 'action.points',
    'events_ref': {'node': 'events/广场', 'module': 'chance.events'},  # 可省略
})
```

可运行配置见 `example.json`（其中未启用可选的 `events_ref`，因此默认行为与未加事件时一致）；
需要到达见闻时，在 config 里补上 `events_ref` 并按上例挂好事件组件即可。

## config

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `channels` | string 数组，非空 | 必填 | `move_here` 工具的访问频道；只在此声明，频道交集与强度由网络核心检查。 |
| `place_name` | string，非空 | 挂载节点名称 | 工具描述与移动结果中显示的本地点名称。 |
| `cost` | integer ≥ 0 | `3` | 移动到本地点消耗的行动值。 |
| `road_channels` | string 数组，非空 | `["road"]` | 哪些连接频道算“道路”；只有带这些频道之一的直接连接才允许移动。 |
| `presence_channel` | string，非空 | `"presence"` | 地点与人物之间的“在场”频道；移动只增删这个频道。 |
| `entity_module` | string，非空 | `"entity.profile"` | 人物资料组件 ID；当前位置读写在它的 `profile.place`，事件效果也调整到它。 |
| `action_module` | string，非空 | `"action.points"` | 行动值组件 ID；余额不足时拒绝移动。 |
| `events_ref` | object `{node, module}` | 无（不抽事件） | 可选的到达事件组件引用：`node` 是挂载事件组件的节点 ID，`module` 是事件组件 ID（通常 `"chance.events"`）。两个字段都必填。 |

所有实例差异都通过配置传入，组件里不写死任何人物、场所或应用节点 ID。

## state

空对象 `{}`：移动是即时的图与档案变更，本组件不保存额外业务状态，`state_schema` 只允许空对象。
`profile.place`、行动值余额与事件命中次数分别存在依赖组件的状态里，随节点存档持久化。

## tools（Agent 可见）

| 名称 | 频道 | 参数 | 返回 |
| --- | --- | --- | --- |
| `move_here` | `channels` 配置的频道列表 | 无（`parameters` 为空的 object） | 见下方结果字段 |

工具描述由实例配置生成，例如：`移动到「中央广场」（花费 3 点行动值）。`

调用时人物身份取 `current_agent_id()`；模型不能指定别人或别的地点。当前所在地点读
`entity.profile` 状态中的 `profile.place`（存地点节点 ID）。

### 移动规则

1. 人物资料里必须已有真实的 `profile.place`，且该节点存在于 `backend.network.nodes`。
2. 当前地点必须与本地点**直接相邻**：两节点之间存在任一方向的直接连接，且连接频道与
   `road_channels` 有交集。没有道路连接则拒绝，不扣费。
3. 人物的当前地点就是本地点时：位置不变、不扣行动值、不抽到达事件，返回 `moved=false`。
4. 需要移动时，在**同一个核心模块事务**内依次完成：通过 `action.points.spend` 扣 `cost`、
   调用 `events_ref` 的 `draw` 并应用事件效果、把 `profile.place` 改为本地点节点 ID。
   余额不足时直接返回 `ok=false`，不移动、不扣费、不抽事件。
5. 事务成功后才迁移在场接口（见下节）。因此事件抽取、行动费、实体状态、人物位置要么一起成功，
   要么一起保持原样；接口只在所有可能失败的步骤成功后才改动。

### 到达事件（可选）

配置了 `events_ref` 时，移动成功过程中会调用：

```python
backend.modules.call(events_ref.node, events_ref.module, 'draw', {
    'trigger': 'arrive',
    'context': {'actor': 人物节点 ID, 'place': 本地点节点 ID},
})
```

- 返回的 `events` 只用于本组件：每个事件的 `message` 会附在移动结果的 `message` 里，
  作为“到达时见闻”返回给 NPC，例如：

  ```text
  你从「集市」沿道路来到「中央广场」，消耗 3 点行动值，剩余 7 点。
  到达时见闻：
  细雨落下。
  你捡到两枚硬币。
  你可以继续行动。
  ```

- 事件的 `effects` 若是对象，且包含 `coins`、`items`、`fields` 中的一个或多个，就把这些键
  （只传这些键，忽略其他键）作为参数调用 `entity.profile.adjust`，应用到执行移动的人物；
  其他形状的 `effects` 不落地。事件本身的其他业务含义由装配者另行处理。
- 事件组件缺失、`draw` 报错、返回格式不对、`adjust` 拒绝（例如金币/物品不足）都会让整次移动失败：
  行动值、`profile.place`、金币/物品/资料、事件命中次数全部回滚，在场接口保持原状，
  工具返回 `ok=false` 的说明。
- 没有配置 `events_ref` 时完全保持原行为：不调用事件组件，返回值也不含 `events` 字段。

### 在场连接迁移

- 旧地点 ↔ 人物、新地点 ↔ 人物两个方向都处理。
- 只从连接上移除 `presence_channel`；该连接若还带脉冲等其他频道则保留这些频道，只有确实没有
  其他频道时才删除整条连接。
- 新地点的双向在场连接使用 `threshold=1`；本组件不改动既有道路的频道、门槛与节点散度，
  节点保持默认 `divergence=-1`，道路保持 `threshold=1`。

### 返回字段

```json
{
  "ok": true,
  "moved": true,
  "place": "place/广场",
  "place_name": "中央广场",
  "cost": 3,
  "remaining": 7,
  "message": "你从「集市」沿道路来到「中央广场」，消耗 3 点行动值，剩余 7 点。\n到达时见闻：\n细雨落下。\n你可以继续行动。",
  "events": [
    {"id": "rain", "message": "细雨落下。"}
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `ok` | 本次调用是否成功；业务拒绝（无道路、余额不足、位置缺失、事件失败）为 `false`，不是异常。 |
| `moved` | 是否真的发生了移动；已在本地点时为 `false`。 |
| `place` | 本地点节点 ID。 |
| `place_name` | 本地点显示名称。 |
| `cost` | 本次实际扣除的行动值；未移动恒为 `0`。 |
| `remaining` | 扣除后的剩余行动值；组件不可用等无法读取时为 `null`。 |
| `message` | 一句给人物看的到达/拒绝说明，配置了 `events_ref` 时包含到达见闻。 |
| `events` | 只在配置了 `events_ref` 时出现：本次命中事件 `id` 与 `message` 的列表（不含 `effects`）。 |

典型拒绝消息：`行动值不足：前往「中央广场」需要 3 点，剩余 2 点，未移动。`、
`无法从「集市」移动到「中央广场」：两地之间没有直接相连的道路。`、
`人物资料里没有记录当前位置（profile.place），未移动。`、
`移动未完成，行动值、位置与资源均未改变：金币不足`。

## operations

无。本组件只提供 Agent 工具，不对外暴露组件间操作；依赖组件自身的 operations 由装配者直接调用。

## signals

无（`signals` 为空）。本组件不响应信号，也不生成或传播信号；何时发起移动由人物决定。

## 限制与装配注意

- 需要装配者把地点之间用 `road_channels` 中的频道连成道路（建议双向各建一条），并在初始人物
  资料里写入 `profile.place`；否则第一次移动会被拒绝。
- 依赖的 `entity.profile`、`action.points` 必须挂在人物节点上；配置了 `events_ref` 时还要在
  `events_ref.node` 上挂好事件组件。缺失或不可用时返回 `ok=false`，不会悄悄跳过事件。
- 事件效果只处理 `{coins, items, fields}` 形状；事件的具体内容、概率与上限都由 `chance.events`
  的实例配置决定，本组件不硬编码任何事件。
- 工具是否可达由网络按 `channels` 做频道交集与强度检查；本组件不重复实现传播或强度判断。
- 不验证“这个人物是否真的有移动许可”、不做 NPC/场所专属规则，也不维护整张地图。
