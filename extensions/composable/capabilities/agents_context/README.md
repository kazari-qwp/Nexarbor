# 角色上下文与私人记忆（agents.context）

适用于 NPC、小组成员和知识工作者等真实 Agent 节点。把稳定人格、通用设定、可选的固定地图和一次性开场提示装配到角色输入，并在每次模型请求前刷新本地账户、当前位置、可达邻域与时钟。私人记忆保存在本 Agent 自己的 `state` 中，只能由本人读取和写入。

## 复用与依赖

本组件复用已发布模块，不复制其业务：

- `records.store`：读取本角色的账户与记录（`values`）。
- `place.info`：读取本角色的当前位置（`location`）。
- `clock.counter`：可选。配置 `clock` 后按 `info` 频道读取天数与时刻。

装配时三个依赖需与角色位于同一节点（时钟可位于可达节点）。角色节点必须用 `agent=True` 创建。

## 配置

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `persona` | 字符串 | 空 | 长期人格，写入 `system_prompt`。 |
| `common` | 字符串 | 空 | 通用设定，与人格一起写入 `system_prompt`。 |
| `map` | 字符串 | 空 | 非空时作为 `context=[{id:'map',text:map}]`。 |
| `opening` | 字符串 | 空 | 非空时只投递一次到 Agent 的 `inputs`，不会反复写入人格。 |
| `clock` | 节点 id 或空 | 空 | 可选时钟节点，读取 `clock.counter.read`。 |
| `max_memories` | 正整数 | 100 | 私人记忆保留上限，超出后丢弃最早记忆。 |

状态只有 `memories`（有限数组，元素含 `text` 与可选 `key`）和 `opening_queued`（布尔）。

## 操作与 Agent 工具

所有操作频道均为 `self`，且会检查 `ctx.requester_id == ctx.node_id`；通过别人的工具调用会被拒绝，不能读取他人的记忆或处境。

- `prepare({})`：刷新并返回当前上下文，同时调用 `ctx.update_inputs` 更新该 Agent 的 `system_prompt`、`context`、`tail`；如有未投递开场，附加唯一 id 的一次性 `inputs`。适合绑定 `NativeExecutor.execution.prepare`，不依赖事件总线。
- `look({})`：返回与 `prepare` 相同的当前信息，但不改写输入。
- `remember({text, key?})`：写入自己的记忆。`text` 非空且最多 4000 字符；相同 `key` 相同内容返回 `duplicate=true`，相同 `key` 不同内容拒绝；超过上限丢弃最早记忆。
- `recall({query})`：在自己的记忆中做子串匹配，`query` 留空返回全部。

导出的中文工具为：`记住`（remember）、`回忆`（recall）、`查看处境`（look）。

## 装配示例

```json
{
  "config": {
    "persona": "你是镇上的图书管理员，说话简短可靠。",
    "common": "只根据自己看到和记得的事回答。",
    "map": "镇广场北接北林，东边是集市。",
    "opening": "你刚整理完书架，听见门口有人走近。",
    "clock": "town-clock",
    "max_memories": 50
  },
  "access": {
    "strength": 2,
    "channels": ["self", "records", "movement", "info"]
  }
}
```

## 每次模型请求前准备上下文

```python
async def before_model_request(executor):
    result = await executor.call(
        executor.node_id,
        "agents.context",
        "prepare",
        {},
    )
    if result.get("status") != "ok":
        raise RuntimeError(result.get("error", "角色上下文准备失败"))
    return result["data"]
```

若宿主通过 `NativeExecutor.execution.prepare` 绑定，直接把 `prepare` 注册为该执行钩子即可。每次调用都会重新读取当前账户、位置、可达边和时钟，所以移动、改边、记账后无需手工维护旧的 `tail`。
