# 双人协议与延后兑现（agreements.pair）

通用双人协议组件：两位真实 Agent 在同一 tick 分别表达同意后才成立。通过配置可以表示婚姻登记、共同家庭计划或其他双方约定，不包含具体 NPC 姓名或固定地图判断。

## 装配依赖

- `records.store`：挂在两位参与者身上，读取 `ap`、`age`、`home` 等普通值及 `spouse` 等显式引用。
- `place.info`：挂在参与者身上，用于核验协议地点和兑现地点。
- `clock.counter`：配置中的 `clock` 指向其节点，`agree` 与 `fulfill` 都读取它的 `tick`。
- 带 `template` 的规则还要求 `delivery_address` 节点提供已预登记的 `templates:instantiate` 宿主端口；组件只传 `template`、稳定 `key` 和仅含 `name/parents/home` 的 `arguments`。

最小访问频道（强度按网络需要）：`agreements`、`records`、`movement`、`info`、`runtime.template`、`tools`。

## 配置

```json
{
  "clock": "clock",
  "address": "registry",
  "delivery_address": "home",
  "sources": [],
  "rules": [
    {
      "id": "marriage",
      "title": "婚姻登记",
      "cost": 1,
      "require_values": {"age": 18},
      "pair_field": "spouse",
      "forbid_existing_pair": true,
      "set_values": {"married": true},
      "delay_ticks": 0
    },
    {
      "id": "family_plan",
      "title": "共同家庭计划",
      "cost": 1,
      "require_values": {"age": 18},
      "equal_fields": ["home"],
      "set_values": {"planning": true},
      "delay_ticks": 10,
      "template": "family_member"
    }
  ]
}
```

- `address` 非空时，同意时双方都必须在该地点。
- `delivery_address` 非空时，兑现时请求者必须在该地点。
- `sources` 非空时，本节点的 `fulfill` 只作为转发入口，依次调用这些来源登记节点的同模块 `fulfill`；来源节点只处理自己的待办，不扫描全网。
- `require_values`：每个字段要求双方值都等于给定值。
- `equal_fields`：双方对应字段相同且非空。
- `pair_field` 配合 `require_pair` 要求双方关系字段分别指向对方；配合 `forbid_existing_pair` 要求双方当前为空，完成时用 `records.apply.references` 互设为对方。
- `set_values` 在完成时分别写入双方记录。
- `delay_ticks > 0` 先创建待兑现协议；到 `due_tick` 后才能 `fulfill`。
- `template` 是宿主预登记模板 ID；没有模板的即时协议只修改双方记录。

## Agent 工具与操作

- `inspect`：查看规则和自己参与的最近协议。
- `agree({partner, rule, key})`：只能由实际 `ctx.requester_id` 的 Agent 同意自己的事；`partner` 必须是可达的真实 Agent。同一 tick 内两份同意才达成；旧 tick 的同意不沿用。新同意从本人 `ap` 扣 `cost`，相同 `key` 重试不重复扣费，不同参数复用同键会被拒绝。
- `fulfill({id, name})`：仅参与者、到期且到达兑现地点后可执行。带模板的协议先短锁保存稳定的待办请求，释放锁后调用 `templates:instantiate`；失败保留待办，用同一模板 key 可重试且不重复创建。成功后保存返回的节点引用，并为父母双方写入 `child` 引用。

`state.agreements` 保留最近 200 条协议，记录 `id`、`rule`、`participants`、`approvals`、`created_tick`、`due_tick`、`status`、待兑现模板请求和模板返回节点等。

## 示例调用

```python
# a 与 b 在同一 tick 同意婚姻规则
await ctx.network.call("registry", "agreements.pair", "agree",
                       {"partner": "b", "rule": "marriage", "key": "a-1"})
await ctx.network.call("registry", "agreements.pair", "agree",
                       {"partner": "a", "rule": "marriage", "key": "b-1"})

# 延迟协议到期后由参与者兑现
await ctx.network.call("registry", "agreements.pair", "fulfill",
                       {"id": agreement_id, "name": "宝宝"})
```
