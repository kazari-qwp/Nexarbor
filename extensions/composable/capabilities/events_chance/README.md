# 地点概率事件 events.chance

一个只负责“目的地本地随机事件”的通用组件。它不移动节点、不扣预算，也不发布 Agent 工具；调用方应在已经完成道路校验和预算扣除的同一节点事务中，对目的地节点调用 `sample`。

- 只提供一个访问操作 `sample`，频道固定为 `events`。
- 必须由真实 Agent 作为请求者调用；普通节点或地点自身不能抽奖。
- 支持按 `sample` 的 `trigger` 参数筛选事件：每个事件可用 `triggers` 限定只在 `arrive`、`work` 等入口参与；`triggers` 为空数组表示所有入口。同一事件标识在任意入口共用成功次数上限。
- 自身和请求者节点在同一个核心锁事务内：先筛出匹配入口的事件并判断成功次数上限，再独立随机，成功后累计次数，最后只调用请求者的 `records.store.apply` 发放奖励。
- 奖励发放失败时异常穿出锁作用域，核心会回滚本次事件次数，外层再转换成错误结果。
- 未中奖返回空 `observations` 和空 `rewards`；`counts` 始终包含所有已配置事件当前累计成功次数，与入口筛选无关。
- 不使用全网查询、文件、环境变量或进程；除当前节点状态外只依赖 `records.store`。

## 装配

在目的地地点节点挂载 `events.chance`，框架会补齐同节点依赖 `records.store`。请求者 Agent 自己也要有 `records.store`。示例：

```json
{
  "config": {
    "events": [
      {
        "id": "coin-found",
        "text": "你在路边捡到几枚金币。",
        "probability": 0.35,
        "limit": 5,
        "rewards": { "金币": 3 }
      },
      {
        "id": "work-harvest",
        "text": "你完成了一段工作，收获一些木材。",
        "probability": 0.6,
        "limit": null,
        "triggers": ["work"],
        "rewards": { "木材": 1 }
      },
      {
        "id": "quiet-road",
        "text": "道路安静，没有发生特别的事。",
        "probability": 1,
        "limit": null,
        "triggers": [],
        "rewards": {}
      }
    ]
  },
  "state": { "counts": {} },
  "access": { "strength": 2, "channels": ["events", "records"] }
}
```

`events` 每项字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 稳定且唯一的事件标识，用于累计成功次数。 |
| `text` | 触发时加入 `observations` 的中文文字。 |
| `probability` | 0～1 的独立抽取概率；0 永不触发，1 必定触发。 |
| `limit` | 正整数成功次数上限，或 `null` 表示不限；达到上限后不再抽取。同一事件在任意 `trigger` 入口共用这一计数。 |
| `triggers` | 可省略，默认 `[]` 表示所有入口都参与。非空且唯一的字符串数组，例如 `["arrive", "work"]`；只有 `sample` 的 `trigger` 在数组内时该事件才参与抽取。 |
| `rewards` | 触发后叠加给请求者记录仓的非负数字映射，可省略。 |

重复的事件标识、重复或空字符串的 `triggers`、非法概率、非正整数的上限、负奖励等配置会被拒绝。

## 在移动事务中调用

移动模块可以在 `before_hooks` 中把目的地目标配置为调用本组件：

```json
{
  "target": "destination",
  "module": "events.chance",
  "operation": "sample",
  "arguments": { "trigger": "arrive" }
}
```

调用发生在道路、预算都验证通过且尚未提交位置修改的同一事务中。`trigger` 可选，省略时为空字符串，只匹配 `triggers` 为空数组（所有入口）的事件。示例可用参数：

```json
{
  "arguments": { "trigger": "work" }
}
```

`sample` 的参数是可选 `trigger` 字符串，不能带其他字段。成功返回：

```json
{
  "observations": ["你在路边捡到几枚金币。"],
  "rewards": { "金币": 3 },
  "counts": { "coin-found": 1, "quiet-road": 1 }
}
```

`rewards` 是本次所有触发事件按字段汇总后的奖励；`counts` 是本次结束后所有配置事件的总成功次数（含未匹配本次入口的事件）。调用方应检查返回封套的 `status`。

## 配置前端

组件自带 `ui.html`：可添加、删除、修改事件，编辑标识、文字、概率、次数上限和奖励 JSON，并只读显示当前成功次数。保存后写入网络草稿，需在客户端点击“应用网络”才影响运行实例。

## 测试

`tests/test_events.py` 使用真实 `ModuleHarness` 覆盖：概率 0/1、成功次数限制、重复事件配置拒绝、奖励发放失败整单回滚、外层锁嵌套、非 Agent 请求者拒绝、错误频道拒绝，以及 `arrive`/`work` 入口共享成功次数上限、错误入口不耗次数、缺省 `triggers` 保持原行为和非法 `triggers` 预检拒绝。运行 `validate` 即可执行宿主验证与测试。
