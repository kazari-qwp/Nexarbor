# resident.context · 居民上下文准备

挂在 Agent 节点上的内部准备组件：每次模型请求前，把人格、常识、地图和此刻的现场资料写进该 Agent 的四路输入。它**不启动 Agent、不移动人物、不生成信号**，只做 `prepare` 这一件事。

适合“每个居民在每次开口前都要知道自己是谁、在哪、身边有谁、还剩多少行动值”的场景。所有地点、人物和组件实例都来自配置与运行时的真实连接，组件里不写死任何节点 ID。

## 挂载与依赖

- 支持节点：`agent`（需要 Agent 的四路输入）。
- 模块 ID：`resident.context`，版本 `1.0.0`。
- `requires`：`entity.profile`、`action.points`、`time.text`。宿主按依赖顺序加载，但**不会自动挂载**；装配者需要把它们分别挂到对应节点。

典型接线：

- 本 Agent 节点：`entity.profile`（资料、金币、物品）与 `action.points`（行动值）。
- 时钟文本节点：`time.text`，并通过 `world.tick` 频道接世界脉冲。
- 本 Agent 节点的 `execution.prepare` 中调用本组件的 `prepare`：

```json
{
  "executor": "harness",
  "strength": 2,
  "prepare": [
    {"module": "resident.context", "operation": "prepare", "arguments": {}}
  ]
}
```

宿主会在每次模型请求前执行它，因此人物移动、别人来去之后，下一次请求看到的现场资料会重新计算。

## config

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `entity_component` | string | `"entity.profile"` | 本节点上提供 `read` 操作的实体资料组件 ID。 |
| `action_component` | string | `"action.points"` | 本节点上提供 `get_balance` 操作的行动值组件 ID。 |
| `clock_node` | string，必填 | — | 时钟组件所在节点 ID。 |
| `clock_component` | string | `"time.text"` | 时钟组件 ID；调用它的 `get_time` 操作。 |
| `persona_file` | string，必填 | — | 人格文件，相对 `backend.directory` 的路径。 |
| `common_sense_file` | string，必填 | — | 常识文件，相对 `backend.directory` 的路径。 |
| `map_file` | string，必填 | — | 地图文件，相对 `backend.directory` 的路径。 |
| `opening_line` | string，必填 | — | 一次性开场白；空串表示不投递开场白。 |
| `road_channels` | string 数组，至少 1 项 | — | 识别地点之间道路连接所使用的频道。 |
| `presence_channels` | string 数组，至少 1 项 | — | 识别场所与同场人物连接所使用的频道。 |

完整示例见 `example.json`。`entity.profile`、`action.points` 固定在**本节点**上，因此只需要组件 ID；时钟在别的节点上，所以节点 ID 单独配置。

文件路径必须是相对路径且不能离开 `backend.directory`，按 UTF-8（可带 BOM）读取，每次 `prepare` 都重新读文件。文件不存在、不可读、路径越界都会抛 `ValueError`，消息中带“人格/常识/地图文件”字样和具体相对路径。

## operations

### `prepare`

参数：无（`{}`）。

依次完成：

1. 读取人格、常识、地图文件。
2. 调用本节点 `entity.profile` 的 `read`，取得 `profile`、`coins`、`items`。
3. 调用本节点 `action.points` 的 `get_balance`。
4. 调用 `clock_node` 上 `clock_component` 的 `get_time`。
5. 用 `profile.place` 找到当前场所节点。
6. 按 `presence_channels` 找出真正连到该场所的 Agent（出边与指向场所的入边都算），只取姓名、性别、职业。
7. 按 `road_channels` 找出真正连到该场所的其他地点名称（出边与指向场所的入边都算）。
8. 重新写入四路输入。

返回示例：

```json
{
  "prepared": true,
  "opening_delivered": true,
  "delivered_opening": true,
  "place": "place/square",
  "people": ["北", "石子"],
  "adjacent": ["旅店", "磨坊"]
}
```

`delivered_opening` 表示**本次**是否投递了开场白；`opening_delivered` 是持久标记。开场白为空串时不会投递，但标记仍会置为 `true`。

## 四路输入

统一写到来源 `resident.context`：

| 输入面 | 内容 | 更新方式 |
| --- | --- | --- |
| `system_prompt` | 人格文件正文 + 空行 + 常识文件正文 | 每次 `prepare` 重读文件后覆盖。 |
| `context` | 恒为一条 `{"id":"map","text":地图文件正文}` | 每次覆盖；地图文档保证存在。 |
| `inputs` | 一条 `{"id":"opening","text":开场白}` | 只在 `opening_delivered` 为 `false` 时投递一次，之后不再追加。 |
| `tail` | 当前时间、自身资料、金币、物品、行动余额、本地场所、同场人物、相邻地点 | 每次整体重算并覆盖。 |

`tail` 的默认排版（一行一项，实际以数组形式写入）：

```text
当前时间：第2天-中午
自身资料：gender=女；name=阿岚；occupation=铁匠
金币：12
物品：面包×2
行动余额：7/10
本地场所：广场（中央广场）
同场人物：北（男，旅人）；石子（女，学徒）
相邻地点：旅店、磨坊
```

说明：

- 自身资料不重复显示 `place`，当前地点由“本地场所”表达。
- 没有物品、同场人物或相邻地点时写“无”。
- 时钟尚未开始时写“尚未开始”。
- 他人的资料读取失败时，退回该节点的 `name`，性别与职业写“未知”；不会因此中断整个准备。
- 远处人物不会被列出，即使他自己档案里的 `place` 与当前场所相同；判定只依据 `presence_channels` 上的真实连接。
- 不读取 `world.tick` 信号内容，也不扫描事件历史。

## state

```json
{"opening_delivered": true}
```

只有 `opening_delivered` 一个字段，随节点存档保存。`setup()` 只补缺失值，读档后保留原值；因此重新加载不会重发开场白。即使开场白已经写入输入面但尚未存档，再次 `prepare` 也只会用同一个事件 ID 写入相同内容，不会产生重复事件。

## tools 与 signals

- `tools` 为空：不占用 Agent 工具名，也没有需要声明的工具频道。
- `signals` 为空：不响应信号，不参与频道传播与强度计算。
- 组件内只观察 `node.interfaces` 上已有的连接元数据，不建立、修改或删除连接。

## 失败与边界

- 任一文件不可读、实体/行动值/时钟组件不可用、`profile.place` 缺失或指向不存在的节点，都会在写输入面之前抛 `ValueError`；开场白标记不会被误置。
- 只支持 `agent` 节点；没有 `inputs` 的节点会明确报错。
- 不写移动、交易、战斗等业务规则，不扣行动值，不启动模型。
- 地图文件是整体文档；相邻地点名称来自连接，不解析地图文件内容。
- 依赖宿主自带的 `datanet` 运行时和 `jsonschema`，不需要新增依赖，不访问网络或系统凭据。
