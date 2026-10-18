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

### 条件、物品门槛、最终上限与字段设置

每个动作还可配置以下通用字段，不包含任何行业或字段特判：

| 字段 | 作用 |
|---|---|
| `require_values` | 请求者当前记录逐字段必须严格相等；缺失或不一致即拒绝，例如 `{"adult": true}`。 |
| `require_items` | 当前持有量至少为“配置值 × `quantity`”；只校验、不扣除，例如 `{"pickaxe": 1}`。 |
| `actor_maximums` | 动作增减和全部事件奖励计算后，请求者字段最终值不得超过上限，例如 `{"debt": 8}`。 |
| `actor_set` | 成功时直接设置请求者字段，可存任意 JSON；不乘 `quantity`，与 `actor_deltas` 同次提交且先设置再增减。 |

`required_home` 仍与以上条件同时生效。所有门槛和上限都在写入前检查；任何一项失败都不会扣行动点、不改库存、不写入回执，也不会消耗事件次数。

成年持镐采矿：`require_values` 限制 `adult=true`，`require_items` 要求 `pickaxe=1`，但动作没有减镐，所以镐不会被消耗。数量为 2 时会要求至少 2 把镐。

```json
{
  "id": "mine",
  "title": "采矿",
  "require_values": {"adult": true},
  "require_items": {"pickaxe": 1},
  "actor_deltas": {"ore": 2},
  "local_deltas": {"ore": -2},
  "cost": 1
}
```

借贷是纯配置方案，不需要另写借贷模块：借出时请求者 `wood+1/debt+2`，场所 `wood-1/receivable+2`，`actor_maximums` 把债务封顶；还款时请求者 `gold-2/debt-2`，场所 `gold+2/receivable-2`。事件奖励也计入上限。

```json
{
  "actions": [
    {
      "id": "borrow",
      "title": "借贷购买木材",
      "actor_deltas": {"wood": 1, "debt": 2},
      "local_deltas": {"wood": -1, "receivable": 2},
      "actor_maximums": {"debt": 8},
      "cost": 1
    },
    {
      "id": "repay",
      "title": "还款",
      "actor_deltas": {"gold": -2, "debt": -2},
      "local_deltas": {"gold": 2, "receivable": -2},
      "cost": 1
    }
  ]
}
```

修理用 `actor_set` 写入工具状态，例如 `{"pickaxe_state": "良好"}`；即使 `quantity` 大于 1，设置值也不会被相乘。需要同时扣钱时把扣费放在 `actor_deltas`，记录仓会先设置状态再应用扣费。

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

1. 锁定服务节点和请求者节点，锁内重查位置、住所、记录值和库存。
2. `address` 非空时，请求者 `place.info.read` 的 `location` 必须相等。
3. `required_home` 非空时，请求者记录的 `home` 必须相等；`require_values` 逐字段严格相等；`require_items` 要求当前量至少为配置值 × `quantity`，只检查不扣除。
4. `actor_deltas`、`local_deltas` 按 `quantity` 倍数结算；`cost` 从请求者 `ap` 字段扣除，`per_unit_cost` 为真时乘数量。负向变化不足时整次拒绝。
5. 逐个独立抽取 `events`；`probability` 为 0/1 时确定不触发/触发，`limit` 是全服务共享的成功次数上限，达到后不再触发。奖励只给成功请求者，并按数量倍数叠加。
6. 用与记录仓相同的顺序（`actor_set` 先写入，再应用所有增减和事件奖励）计算请求者最终记录，检查 `actor_maximums`；事件奖励不能绕过上限。
7. 全部检查通过后才写入事件计数并执行两次 `records.store.apply`（请求者一次提交 `set + deltas`）；任何错误立刻抛出，出锁后转为错误封套，由核心回滚两个节点和事件计数。

### 幂等

带 `key` 的成功结果保存在服务状态的最近 200 条回执中。回执按原始请求者与用户 `key` 隔离：同一 Agent 在相同动作、数量下重试会返回旧结果（`duplicate: true`，不扣费、不重抽），不同参数会拒绝；两个 Agent 使用相同 `key` 互不冲突。

转调 `records.store.apply` 时，去重键会再拼接模块 id、服务节点 id、原始请求者、用户 `key` 以及 `actor`/`local` 结算步骤。因此同一 Agent 在两家商店使用相同 `key`、或两个 Agent 复用相同 `key` 时，各自的扣费与库存变更都会独立执行，不会错误复用记录仓回执。失败不写本地回执，可安全换键重试。

## 请求者身份

`ctx.requester_id` 是唯一可信的请求者身份，参数中没有 `actor_id`。本模块通过 `ctx.network.metadata` 确认请求者的 `node_type == 'agent'`；请求者不可达或不是 Agent 时直接拒绝，不回退到普通节点。
