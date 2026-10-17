# social.same_place · 通用同场所交流

挂在每个 Agent 上的“同场所说话”端点：每个实例暴露一个 `talk` 工具，代表**本节点这位收话者**。
其他可信 Agent 在同一个场所时，可以通过同场交互频道调用它；组件会校验双方 `profile.place`，
扣除发送者行动值，并把带发送者姓名与唯一消息 ID 的话写进收话者 Agent 的四路输入之一
`inputs`，由框架在收话者下一次模型请求时交给它自行处理。

本组件不启动收话者、不自动回复、不生成信号，也不实现频道交集或强度判断——这些都交给网络与执行器。

- 模块 ID：`social.same_place`
- 版本：`1.0.2`
- 支持节点：`agent`
- 依赖：`entity.profile`（读资料与 `place`）、`action.points`（扣行动值）
- 公开工具：`talk`（参数只有 `message`）
- 信号：无

## 接线方式

对网络里的每一个 Agent 都挂三件事：资料、行动值和本组件。

```python
backend.modules.mount('agent/alice', 'entity.profile', {
    'profile': {'name': '爱丽丝', 'place': '广场'},
})
backend.modules.mount('agent/alice', 'action.points', {'max': 10})
backend.modules.mount('agent/alice', 'social.same_place', {
    'channels': ['social.same_place'],
    'display_name': '爱丽丝',
})

backend.modules.mount('agent/bob', 'entity.profile', {
    'profile': {'name': '鲍勃', 'place': '广场'},
})
backend.modules.mount('agent/bob', 'action.points', {'max': 10})
backend.modules.mount('agent/bob', 'social.same_place', {
    'channels': ['social.same_place'],
    'display_name': '鲍勃',
})
```

再用同场交互频道把允许互相说话的 Agent 连起来（方向、阈值和强度按你的网络配置）：

```python
backend.network.nodes['agent/alice'].connect(
    'agent/bob', channels=['social.same_place'], threshold=1
)
backend.network.nodes['agent/bob'].connect(
    'agent/alice', channels=['social.same_place'], threshold=1
)
```

- 每个实例的 `talk` 工具只在配置的 `channels` 上可达；频道名必须与连接时使用的频道一致。
- 只有通过该频道可达的 Agent 才能发现并调用对方的 `talk`；跨场所的连接不要授予这个频道。
- `place` 以 `entity.profile` 的 `profile.place` 为准；移动组件改写这个字段即可“离开/到达”，
  本组件不追人、不移动。

## config

`example.json` 是一份可直接运行的配置。

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `channels` | string[]（≥1） | 是 | — | 同场交互频道列表；工具声明为 `{"config":"channels"}`，由宿主编译成 `access_channels`。 |
| `action_cost` | integer ≥ 0 | 否 | `1` | 每句话扣除发送者多少行动值；`0` 表示免费说话。 |
| `profile_module` | string | 否 | `entity.profile` | 读取 `profile` 的依赖组件 ID。 |
| `action_module` | string | 否 | `action.points` | 扣除行动值的依赖组件 ID。 |
| `place_field` | string | 否 | `place` | `profile` 中表示所在场所的字段名。 |
| `display_name` | string | 否 | — | 可选收话者姓名；只在挂载时还读不到对方 `profile.name` 时用于工具描述。 |

依赖调用与组件实例全部由配置/节点决定，代码里没有写死任何 NPC、场所或应用节点 ID。

## tools

| 名称 | 频道 | 参数 | 返回 |
| --- | --- | --- | --- |
| `talk` | 配置字段 `channels` | `message`（string，必填） | 见下 |

### 公开描述

工具描述在安装时生成，会写成“和**收话者姓名**说一句话……”。姓名优先取收话者当前
`profile.name`；如果 `social.same_place` 比 `entity.profile` 先挂载，则回退到 `display_name`，
再回退到节点名。描述用于调用方模型理解“这个工具是在和谁说话”。

### 调用者身份

发送者身份取自 `datanet.core.access_budget.current_agent_id()`，不通过参数传入，模型也不能填写。
所以这个工具只应在可信工具调用上下文里使用；没有调用者时会被拒绝。

### 成功返回

```json
{
  "ok": true,
  "sent": true,
  "reason": null,
  "message": "消息已发给鲍勃，剩余行动值 4/10。",
  "receiver": "鲍勃",
  "receiver_id": "agent/bob",
  "input_id": "6f1c……",
  "remaining": 4,
  "max": 10
}
```

`remaining` 是发送者扣除后的行动值，`max` 是行动值上限；`input_id` 是本次投递的唯一消息 ID。

### 失败返回

失败统一返回 `{"ok": false, "sent": false, "reason": ..., "message": ...}`，不会写入对方输入：

| `reason` | 场景 | `message` |
| --- | --- | --- |
| `receiver_not_present` | 对方 `place` 与发送者不同、缺少 `place`，或读不到对方资料 | `他好像已经去了某地点，已经不在这里了` |
| `insufficient_action` | 行动值不够 `action_cost` | 沿用 `action.points` 的拒绝说明，例如“行动值不足：需要 1，剩余 0/10，未扣除。” |
| `sender_not_present` | 发送者没有非空的 `place` | “你当前不在任何场所，没有发送。” |
| `sender_profile_unavailable` | 读不到发送者资料 | “无法确认你的所在场所，没有发送。” |
| `action_unavailable` | 调用行动值组件失败 | “无法扣除行动值，没有发送。” |
| `self_talk` | 调用者是收话者自己 | “你不能把这句话说给自己听。” |
| `no_caller` | 不在可信 Agent 调用上下文 | “这个工具只能由可信的 Agent 调用发起。” |
| `empty_message` | `message` 为空白 | “要说的话不能为空，没有发送。” |
| `delivery_failed` | 写入输入失败（少见） | “话没有送进对方输入。” |

“对方已离开”不会自动追过去、不会改变任何人的位置，也不会替发送者重试。

## 工具已不可达时的解释（on_tool_denied）

发送者曾经发现过某位收话者的 `talk`，随后对方移动导致该工具不再可达时，原生宿主不会执行
`talk`，而是调用组件覆写的 `on_tool_denied(name, actor, reason)` 生成拒绝说明：

- 只处理 `name == "talk"`；其他工具原样返回 `reason`。
- 读取 `actor`（发送者）与收话者**当前**的 `profile.place`：
  - 双方都有非空场所且不同：返回 `鲍勃好像已经去了「居民楼1」，已经不在这里了`。
    姓名取收话者当前 `profile.name`；地点取收话者当前 `profile.place`，若它是节点 ID
    则解析为 `backend.network.nodes[receiver_place].name`，节点不存在时回退显示原 ID。
  - 读不到任一方资料/场所、双方场所相同、`actor` 缺失或就是收话者自己：原样返回 `reason`。
- 该回调只做解释：不扣行动值、不写 `inputs`、不发信号、不修改 `state`，也不会执行 `talk`。

因此移动后调用方模型看到的是带真实地点名的说明，而不是框架的通用拒绝文本。

## 投递内容与框架处理

- 以固定 source（本组件 ID `social.same_place`）调用 `self.node.inputs.update`，只写 `inputs` 这一路。
- 每条事件：

```json
{
  "id": "唯一消息ID",
  "text": "爱丽丝（agent/alice）对你说：你好",
  "status": "pending"
}
```

  事件 ID 是每次投递新生成的 UUID；文字里带发送者姓名和发送者节点 ID。
- 事件保持 `pending`，直到收话者 Agent 下一次模型请求把输入交给执行器；执行成功完成后由框架
  acknowledge。本组件不调用 `backend.execute_agent`、不产生信号、不触发自动回复，避免双方互相唤醒。

## 依赖操作

只通过 `backend.modules.call` 调用清单里声明的依赖，不直接读写别的组件状态：

| 依赖 | 操作 | 用途 |
| --- | --- | --- |
| `entity.profile`（或 `profile_module`） | `read` | 读取发送者/收话者的 `profile`，比较 `place_field` 字段并取姓名。 |
| `action.points`（或 `action_module`） | `spend` | 先校验再扣除发送者行动值；返回 `ok=false` 时消息不发送。 |

本组件自身没有 `operations`、没有 `signals`，也不向其他组件暴露操作。

## state

`state_schema` 是空对象：本组件不需要持久状态，消息内容在框架的 Agent 输入里，行动值在
`action.points` 里。重挂载或读档不会重置这些数据。

## 行为顺序

1. 校验消息非空、调用者存在、不是自己对自己说。
2. 读取发送者资料与 `place`，必须非空。
3. 读取收话者资料与 `place`，必须与发送者完全相同；否则返回“他好像已经去了……”。
4. 调用 `action.points.spend` 扣除 `action_cost`；余额不足立即拒绝，不写入输入。
5. 生成唯一消息 ID，把带发送者姓名与 ID 的文字写进收话者 `inputs`。
6. 返回发送成功、收话者姓名、剩余行动值与上限。

## 限制

- 场所判断只依据 `entity.profile.profile.place` 的非空字符串相等；没有额外的“在场”标记，
  也不感知地图节点本身。
- 工具描述在安装时固定；之后对方改名不会自动刷新描述（消息正文始终使用调用时读到的姓名）。
- 一次调用只送到当前实例所在的这一个收话者，不做群发/广播；要通知多人就分别调用各自节点。
- 先扣行动值再写输入：若写入输入极少数失败，行动值已经扣除，返回的 `delivery_failed` 会带余额。
- 不校验调用方是否“应该”说话；可信调用链由宿主工具权限与频道保证，业务前提在本组件内检查。
- `on_tool_denied` 只读取资料并返回一段说明；如果移动后连双方资料/场所都无法读取，它只能沿用
  框架的通用 `reason`，无法给出真实地点名。
- 测试见 `tests/test_module.py`，覆盖成功投递、跨场所拒绝、行动值不足、发送者不在场、
  自己对自己说、无调用者、重复发送、配置化频道/场所字段/依赖 ID，以及工具不可达时按当前
  `profile.place` 解释拒绝且不扣费、不投递、不改状态等场景。
