# 可配置业务服务

程序标识：`service.actions`。同一份组件通过配置提供采集、买卖、修理、休息、饮料等业务，不为每个地点或 NPC 单独写模块。

## 装配

- 服务节点：挂载本模块与 `records.store`（保存场所库存），需要 `place.info` 时一并挂载。
- 请求者 Agent：挂载 `records.store`（保存钱、物品和行动点），配置了 `address` 时还需挂载 `place.info`。
- 频道：本模块操作使用 `service`；读取位置使用 `movement`；记录仓使用 `records`。
- 依赖：`requires` 声明同节点直接依赖；框架会递归自动装配、去重并复用已有配置和状态，`records.store` 随本模块同节点装配。

示例配置：

```json
{
  "address": "market",
  "actions": [
    {
      "id": "gather",
      "title": "采集",
      "description": "从场所库存取得木材。",
      "actor_deltas": {"wood": 2},
      "local_deltas": {"wood": -2},
      "cost": 1
    },
    {
      "id": "buy",
      "title": "购买",
      "description": "用金币换取木材。",
      "actor_deltas": {"wood": 1, "gold": -3},
      "local_deltas": {"wood": -1, "gold": 3},
      "cost": 1
    },
    {
      "id": "rest",
      "title": "休息",
      "description": "恢复体力。",
      "actor_deltas": {"energy": 1},
      "local_deltas": {},
      "cost": 2,
      "per_unit_cost": true,
      "required_home": "home-a"
    }
  ],
  "events": [
    {
      "id": "bonus",
      "text": "你在角落发现了一点额外收获。",
      "probability": 0.2,
      "limit": 5,
      "rewards": {"gold": 1}
    }
  ]
}
```

## 操作与 Agent 工具

### inspect

参数 `{}`，返回：

```json
{"actions": [{"id": "gather", "title": "采集"}], "inventory": {"wood": 10}}
```

`actions` 是配置数组的副本，`inventory` 是服务节点 `records.store` 的当前记录。

### perform

参数：`action`（配置动作 id）、`quantity`（1..100 整数，默认 1）、`key`（可选非空幂等键）。

成功返回 `action / quantity / actor / values / observation / duplicate`。`actor` 始终取 `ctx.requester_id`，参数中没有 `actor_id`；不能替别人消费。

结算规则：

1. 锁定服务节点和请求者节点，锁内重查位置、住所和库存。
2. `address` 非空时，请求者 `place.info.read` 的 `location` 必须相等。
3. `actor_deltas`、`local_deltas` 按 `quantity` 倍数结算；`cost` 从请求者 `ap` 字段扣除，`per_unit_cost` 为真时乘数量。
4. 负向变化先检查余额，不足则整次拒绝且不修改任何字段。
5. `required_home` 非空时，请求者记录的 `home` 必须相等。
6. 成功后逐个独立抽取 `events`；`probability` 为 0/1 时确定不触发/触发，`limit` 是全服务共享的成功次数上限，达到后不再触发。奖励只给成功请求者。
7. 两次 `records.store.apply` 都在锁内；任何错误立刻抛出，出锁后转为错误封套，由核心回滚两个节点和事件计数。

### 幂等

带 `key` 的成功结果保存在服务状态的最近 200 条回执中。回执按原始请求者与用户 `key` 隔离：同一 Agent 在相同动作、数量下重试会返回旧结果（`duplicate: true`，不扣费、不重抽），不同参数会拒绝；两个 Agent 使用相同 `key` 互不冲突。

转调 `records.store.apply` 时，去重键会再拼接模块 id、服务节点 id、原始请求者、用户 `key` 以及 `actor`/`local` 结算步骤。因此同一 Agent 在两家商店使用相同 `key`、或两个 Agent 复用相同 `key` 时，各自的扣费与库存变更都会独立执行，不会错误复用记录仓回执。失败不写本地回执，可安全换键重试。

## 请求者身份

`ctx.requester_id` 是唯一可信的请求者身份，参数中没有 `actor_id`。本模块通过 `ctx.network.metadata` 确认请求者的 `node_type == 'agent'`；请求者不可达或不是 Agent 时直接拒绝，不回退到普通节点。
