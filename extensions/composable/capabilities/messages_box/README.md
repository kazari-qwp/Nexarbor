# 消息与讨论箱 messages.box

一个通用的本地消息组件，可挂在普通 `node`（如议事厅、公告板、任务板）或真实 `agent`（如 NPC 私人信箱）上。通过配置区分三种常见场所：

- NPC 私信：`read_policy: "self"`，只有信箱所在节点能读。
- 讨论小组公告：`read_policy: "reachable"`，合法可达的节点都能读。
- 协作组任务通信：开启发送费用，并从发送者记录仓的 `ap` 字段扣除行动点。

组件只使用 `ctx` 访问本地状态和网络，不读取其他业务源码。`requires` 保持为空；发送费用大于 0 时，才需要额外装配官方 `records.store`。

## 装配

```json
{
  "messages.box": {
    "config": {
      "read_policy": "self",
      "send_cost": 0,
      "max_messages": 200,
      "require_agent": true
    },
    "state": {},
    "access": {
      "strength": 2,
      "channels": ["chat", "records"]
    }
  }
}
```

操作频道固定为 `chat`。消息箱需要一条从发送者到消息箱的入边（`chat`），以及一条从消息箱回到发送者的出边（至少包含 `chat` 用于读取发送者公开元数据）。需要扣费时，消息箱的出边还要包含 `records`，并在发送者节点装配 `records.store`：

```json
{
  "records.store": {
    "config": {
      "initial": { "ap": 5 },
      "minimum": { "ap": 0 }
    },
    "state": {},
    "access": { "strength": 1, "channels": ["records"] }
  }
}
```

`minimum.ap` 是防止行动点透支的下限。若发送者未装配记录仓、路径或频道不足，发送会失败且不写入消息。

## 配置

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `read_policy` | `self` / `reachable` | `self` | `self` 仅允许消息箱所在节点读取；`reachable` 允许本操作合法可达者读取。 |
| `send_cost` | 非负整数 | `0` | 每条新消息从发送者 `records.store` 的 `ap` 字段扣除的行动点。 |
| `max_messages` | 正整数 | `200` | 本地只保留最近多少条消息，超出后删除最旧消息。 |
| `require_agent` | 布尔 | `true` | 开启时发送者核心元数据必须严格为 `node_type == "agent"`。 |

## 同一时刻回应

可选 notify_activity:true 在新消息投递后，经 activity 频道把 agents.activity.notify 排入当前信号层，不等待对方整轮模型。消息箱需该频道授权，收件节点需活动组件。普通讨论箱默认不通知。排队失败仍返回投递成功，在 notification 内记录错误，不冒充投递失败造成重复扣费。重复投递不重复通知。

## 操作

### send

频道：`chat`。参数：

```json
{ "text": "今晚在广场集合", "topic": "协作", "key": "任务-1" }
```

- `text`：必填非空字符串，最大 4000 字符。
- `topic`：可选字符串，默认空字符串。
- `key`：可选字符串，用于发送幂等。

返回：

```json
{
  "id": "消息ID",
  "from": "发送者节点ID",
  "to": "消息箱节点ID",
  "text": "今晚在广场集合",
  "topic": "协作",
  "duplicate": false,
  "ap": 4
}
```

发送者只来自 `ctx.requester_id`，参数不能指定或伪造发送者。`require_agent` 开启时通过 `ctx` 读取发送者公开元数据并严格检查 `node_type == "agent"`；无法确认发送者时直接拒绝。非零费用会在锁内先读取发送者的 `ap` 并确认足够，再调用 `records.store.apply`，以 `deltas: {"ap": -send_cost}` 扣费；任何失败都异常穿出锁作用域并回滚消息箱与发送者状态。即使记录仓未配置 `minimum.ap`，本组件也不会在行动点不足时写入消息。

`key` 与发送者联合去重：同一发送者、同一 `key`、同一正文和话题再次提交时返回原消息并标记 `duplicate: true`，不再扣费；同一 `key` 配不同正文或话题会报错。费用为0时查询元数据后读取最新状态、同步计划并提交，不申请事务。费用大于0才用短事务保护消息箱与发送者，保证扣费和投递一起成功；锁外才通知回应。

### read

频道：`chat`。参数：

```json
{ "limit": 20 }
```

`limit` 范围为 1 到 200，默认 20。返回最近的有限条消息：

```json
{ "messages": [ { "id": "...", "from": "alice", "to": "box", "text": "...", "topic": "" } ] }
```

`read_policy: "self"` 时核验 `ctx.requester_id == ctx.node_id`，远程请求即使能看到读取工具也会被拒绝。`read_policy: "reachable"` 时仍需框架路径、强度和频道校验通过。

### clear

频道：`chat`，参数必须为空对象 `{}`。只有消息箱所在节点自己可以清理本地消息和幂等回执，返回：

```json
{ "cleared": 3 }
```

清理是本地独立业务，不会删除其他节点状态。

## Agent 工具

- `send`（发送消息）：调用 `send`，参数模式与公开操作一致。
- `read`（读取消息）：调用 `read`，是否能看到内容仍由消息箱读取范围和真实路径决定。

工具不增加额外权限，发送者身份仍由请求链和 `ctx.requester_id` 决定。

## 状态

- `messages`：有限消息数组，受 `max_messages` 裁剪。
- `seen`：有限幂等回执，保存发送者与去重键的联合键、内容指纹和原消息 ID。

## 测试

`tests/test_messages_box.py` 使用真实 `ModuleHarness`，覆盖：

1. 真实 Agent 发送与读取。
2. 私信远程读取拒绝、公开讨论可读。
3. 普通 `node` 冒充身份发送拒绝及伪造字段的 Schema 拒绝。
4. 路径不足和频道不足拒绝。
5. 行动点不足不写消息、不扣款。
6. 并发发送不超支行动点。
7. 去重幂等、重复不扣费、冲突键拒绝。
8. 非所有者清理拒绝、所有者清理成功。
9. Schema 类型和边界错误直接抛 `ValidationError`。
10. 依赖调用末尾注入失败后，消息与行动点双方回滚。

运行宿主验证命令即可执行这些真实运行时测试。
