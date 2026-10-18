# 信号驱动的角色活动

`agents.activity` 面向 NPC、小组工作者等真实 Agent。收到 `tick` 等频道信号，或宿主调用公开操作 `activate` 时，它会：

1. 锁定本节点，核验活动键去重；
2. 通过本节点的 `records.store.apply` 把行动预算字段重置为配置值，并记下 `running`；
3. 释放锁后调用本地 `agents.context.prepare`；
4. 通过显式授权的官方端口 `runtime:agent_run` 运行本节点，消息为配置的 `prompt`；
5. 成功后短锁记录 `completed` 与完成次数并发布元数据；失败保留 `failed` 和错误原因。

信号使用 `activation.signal.signal_id` 作为活动键。信号处理失败会抛出异常，让传播器停止该分支；公开操作失败返回错误封套。相同已完成键再次到达时直接返回 `duplicate`，不会重置预算或重跑模型；相同 `running`／`failed` 键会被拒绝，避免半轮重放。

## 装配

本组件只装配在真实 `agent` 节点上，依赖 `records.store` 与 `agents.context`（后者还会递归装配其自身依赖）。模块不导出任何 Agent 工具，避免模型递归启动自己。

```json
{
  "modules": {
    "records.store": {
      "config": { "initial": { "ap": 3 }, "minimum": {} },
      "access": { "strength": 2, "channels": ["records"] }
    },
    "agents.context": {
      "config": { "persona": "谨慎的守夜人", "opening": "集合时间到了" },
      "access": { "strength": 2, "channels": ["self", "records", "movement"] }
    },
    "agents.activity": {
      "config": {
        "signal_channels": ["tick"],
        "budget_field": "ap",
        "budget": 10,
        "prompt": "现在开始你这一时刻的行动。",
        "enabled": false
      },
      "access": {
        "strength": 0,
        "channels": ["tick", "records", "self", "runtime.agent"]
      }
    },
    "tools.collector": {
      "config": {},
      "access": { "strength": 2, "channels": ["tools"] }
    }
  }
}
```

宿主必须为该 Agent 节点显式提供官方运行端口与频道授权：

```json
"offered_tools": [
  { "ref": "runtime:agent_run", "channels": ["runtime.agent"] }
]
```

`runtime:agent_run` 只运行当前节点，不接受任意 actor 参数；宿主运行时会从该节点自己的 `tools.collector` 取得当下可用工具。组件自身申请 `records`、`self`、`runtime.agent` 三个调用频道，并接收 `tick` 信号。

安全默认下 `enabled` 为 `false`，直接拖入组件不会响应 `tick`，也不会产生付费模型调用。装配后必须：先确认该节点 `offered_tools` 已提供 `runtime:agent_run` 及其频道授权，再由应用配置显式启用：

```json
{
  "agents.activity": {
    "config": { "enabled": true }
  }
}
```

只有应用确实要运行本节点时才做这次覆盖。`example.json` 保持安全默认 `false`，不会自动产生付费模型调用。

## 配置

| 字段 | 默认值 | 说明 |
|---|---|---|
| `signal_channels` | `["tick"]` | 触发活动的信号频道。 |
| `budget_field` | `"ap"` | 记录仓中的行动预算字段。 |
| `budget` | `10` | 每次新活动写入的非负整数预算。 |
| `prompt` | `""` | 投递给本节点 Agent 的用户消息。 |
| `enabled` | `false` | 默认关闭；必须由应用显式设为 `true` 才运行。关闭时跳过，不扣预算也不调用模型。 |

## 触发

- 信号：让时钟等源节点沿真实出边发送 `tick`。源节点本身不执行本组件，接收端必须在出边目标上。
- 单次运行：宿主在具备 `tick` 频道访问时调用公开操作 `activate`，参数 `{"key": "非空活动键"}`，并自行检查返回的 `status`、`duplicate` 与 `error`。

状态 `activities` 保留最近 200 个活动键的 `running`／`completed`／`failed`、该键完成次数与失败原因；`completed_total` 记录累计完成次数。
