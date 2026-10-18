# 双人协议与延后兑现（agreements.pair）

通用双人协议组件：两位真实 Agent 在同一 tick 分别表达同意后才成立。通过配置可以表示婚姻登记、共同家庭计划、共同孕育或其他双方约定，不包含具体 NPC 姓名、性别判断或固定地图特判。

## 装配依赖：同节点与跨节点

清单中的 `requires` 只列“必须自动挂在同一登记节点上”的依赖。本组件的记录、位置、时钟和模板都在其他节点上，因此 `requires` 为空，避免把无用组件自动挂到登记节点。

以下协作模块通过配置节点 ID 和 `ctx.network.call` 跨节点访问，需要分别挂在真实节点上：

- `records.store`：挂在两位参与者自己的 Agent 节点上；组件读取/写入他们的普通值和显式引用。
- `place.info`：挂在参与者节点上时用于核验协议地点和兑现地点；需要按地点判断时再装配。
- `clock.counter`：挂在配置 `clock` 指向的节点上，`agree` 与 `fulfill` 读取它的 `tick`。
- `templates:instantiate`：带 `template` 的规则需要兑现地点节点提供这个已预登记宿主端口；组件只传 `template`、稳定 `key` 和仅含 `name/parents/home` 的 `arguments`。端口按官方格式返回 `node_ids` 字典（值为新节点 ID），数组形式也兼容。

最小访问频道（强度按网络需要）：`agreements`、`records`、`movement`、`info`、`runtime.template`、`tools`。

## 配置

```json
{
  "clock": "clock",
  "address": "registry",
  "delivery_address": "hospital",
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
      "id": "shared_care",
      "title": "共同孕育",
      "cost": 1,
      "fulfill_cost": 1,
      "require_values": {"age": 18},
      "eligible_field": "can_carry",
      "fulfill_require_values": {"can_carry": true},
      "participant_effects": [
        {
          "when": {"can_carry": true},
          "on_start": {"pregnant": true},
          "on_finish": {"pregnant": false}
        }
      ],
      "set_values": {"is_parent": true},
      "delay_ticks": 10,
      "template": "child"
    }
  ]
}
```

- `address` 非空时，同意时双方都必须在该地点。
- `delivery_address` 非空时，兑现时请求者必须在该地点；带 `template` 时还必须提供模板端口。
- `sources` 非空时，本节点是来源登记节点的汇总入口，只访问这里明确列出的节点，不扫描全网。`inspect` 逐个调用来源的 `inspect`，把各来源中“当前请求者可见”的协议合并返回，并为每条协议附加 `source` 字段；规则按 `id` 合并。`fulfill` 先逐个 `inspect`，只在目标协议 ID 唯一匹配的来源上转调一次。
- `cost`：每位参与者每次新同意从自己的 `ap` 扣除的行动点，默认 1，非负整数。
- `fulfill_cost`：带模板协议首次准备待兑现模板请求时，从兑现者自己的 `ap` 扣除一次的行动点，默认 0，非负整数；没有模板的协议不扣此项。
- `require_values`：每个字段要求双方值都等于给定值。
- `eligible_field`：可选字符串。设置后，两位参与者记录中该字段至少有一位为 `true` 才允许同意，因此只按字段值判断资格，不由组件写死性别或其他字段。
- `fulfill_require_values`：普通对象。兑现时只检查“兑现者本人”的记录，每个字段都相等才允许兑现。
- `participant_effects`：数组，每项形如 `{when, on_start, on_finish}`。对每位参与者，用其本人当前 `records.values` 匹配 `when`；匹配后，`on_start` 在双方同意达成时按数组顺序写入该参与者记录，`on_finish` 只在实际完成时写入。
- `equal_fields`：双方对应字段相同且非空。
- `pair_field` 配合 `require_pair` 要求双方关系字段分别指向对方；配合 `forbid_existing_pair` 要求双方当前为空，完成时用 `records.apply.references` 互设为对方。
- `set_values` 在完成时分别写入双方记录，和匹配参与者的 `on_finish` 一起生效。
- `delay_ticks > 0` 先创建待兑现协议；到 `due_tick` 后才能 `fulfill`。`on_start` 在双方同意达成时立即执行，即使尚未兑现。
- `template` 是宿主预登记模板 ID；没有模板的即时协议只修改双方记录。

“至少一人具备孕育能力、只有具备该能力的人到医院兑现，开始让该人 `pregnant=true`、完成 `false`，双方 `is_parent=true`”只是上面 `shared_care` 配置的一种用法；把字段名和值换掉即可用于其他角色协议。

## 事务与幂等

- 同意、开始效果、完成效果和模板待办都位于“登记节点 + 两位参与者 + 时钟”的整组节点锁内；任一步失败会整体回滚该次操作。
- 第二份同意失败时，第二份同意记录、这次费用和开始效果都会回滚；先前已提交的第一份同意不受影响。
- 内部记录写入的幂等键含模块实例、协议 ID、参与者和阶段（`agree-cost`、`fulfill-cost`、`on_start`、`on_finish`/`complete`、`child` 等），相同请求重试不会重复执行或重复扣费。
- `fulfill_cost` 只在首次准备待兑现模板请求时扣一次；模板端口调用失败时待办和扣费记录都会保留，用相同 `id` 与 `name` 重试可继续，不会再次扣费；完成后的重复 `fulfill` 直接返回 `duplicate`。

## Agent 工具与操作

- `inspect`：查看规则和自己参与的最近协议。配置 `sources` 时逐个调用来源 `inspect`，只汇总当前请求者可见的协议，并给每条来源协议加上 `source` 字段；来源不可用或读取失败会返回明确错误，不会静默忽略。
- `agree({partner, rule, key})`：只能由实际 `ctx.requester_id` 的 Agent 同意自己的事；`partner` 必须是可达的真实 Agent。同一 tick 内两份同意才达成；旧 tick 的同意不沿用。新同意从本人 `ap` 扣 `cost`，相同 `key` 重试不重复扣费，不同参数复用同键会被拒绝。
- `fulfill({id, name})`：仅参与者、到期、满足 `fulfill_require_values` 且到达兑现地点后可执行。配置 `sources` 时先对每个来源执行 `inspect`：0 个来源匹配该 `id` 时返回“没有来源找到该协议”的错误；多个来源都匹配时返回歧义错误，且不执行任何来源；唯一匹配时只向该来源转调一次，并保留原请求者身份。来源的真实业务失败会原样浮出为错误，不会改报成功，也不会继续尝试其他来源。带模板的协议先短锁保存稳定的待办请求，首次保存时按 `fulfill_cost` 扣一次兑现者 `ap`；释放锁后调用 `templates:instantiate`。官方端口返回形如 `{"node_ids": {"child": "实际新节点ID"}, "duplicate": false, ...}`，组件从字典值提取节点 ID，也兼容旧的节点 ID 数组；返回为空或没有有效节点 ID 时协议保持 `pending`，不能标记完成。端口失败保留待办，用同一模板 key 可重试且不重复扣费。成功后保存返回的节点引用，并为父母双方写入显式的 `child` 引用（完整网络拷贝可自动映射）。

`state.agreements` 保留最近 200 条协议，记录 `id`、`rule`、`participants`、`approvals`、`created_tick`、`due_tick`、`status`、待兑现模板请求和模板返回节点等。

## 示例调用

```python
# a 与 b 在同一 tick 同意婚姻规则
await ctx.network.call("registry", "agreements.pair", "agree",
                       {"partner": "b", "rule": "marriage", "key": "a-1"})
await ctx.network.call("registry", "agreements.pair", "agree",
                       {"partner": "a", "rule": "marriage", "key": "b-1"})

# 延后协议到期后由参与者兑现；如配置了模板，可传新成员名称
await ctx.network.call("registry", "agreements.pair", "fulfill",
                       {"id": agreement_id, "name": "宝宝"})
```
