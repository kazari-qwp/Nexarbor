# 角色上下文与私人记忆（agents.context）

适用于 NPC、小组成员和知识工作者等真实 Agent 节点。把稳定人格、通用设定、可选的固定地图、按记录匹配的情境知识和一次性开场提示装配到角色输入，并在每次模型请求前刷新本地账户、当前位置、可达邻域与时钟。私人记忆保存在本 Agent 自己的 `state` 中，只能由本人读取和写入。`prepare` 还会把配置允许的公开资料发布到本模块命名空间，供同地其他角色查看；不会发布完整记录、资产、记忆或开场内容。

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
| `public_fields` | 非空字符串数组 | `["name","gender","profession","age_group"]` | 只把本记录中的这些字段发布给同地其他角色；未列出的字段不会发布。 |
| `knowledge` | 数组 | 空 | 每项 `{id, when, text}`。`prepare` 只把 `when` 中所有普通字段都等于自己 `records.store` 当前值的条目加入 `context`。 |

状态只有 `memories`（有限数组，元素含 `text` 与可选 `key`）和 `opening_queued`（布尔）。

`knowledge[].id` 必须是非空字符串，用于生成稳定的上下文条目 id（`knowledge:<id>`），与固定地图条目 `map` 区分。`when` 是普通字段等值对象；条件不满足时该条目不会出现在结果或 Agent 的 `context` 中，记录变化后下次 `prepare` 会自动更新。这样可以用同一组件配置职业、性别或家庭状态相关文本，而不读取其他角色的私有文本。

## 操作与 Agent 工具

所有操作频道均为 `self`，且会检查 `ctx.requester_id == ctx.node_id`；通过别人的工具调用会被拒绝，不能读取他人的记忆或处境。

- `prepare({})`：刷新并返回当前上下文，按 `public_fields` 发布自己的公开资料，同时调用 `ctx.update_inputs` 更新该 Agent 的 `system_prompt`、`context`、`tail`；如有未投递开场，附加唯一 id 的一次性 `inputs`。适合绑定 `NativeExecutor.execution.prepare`，不依赖事件总线。
- `look({})`：返回与 `prepare` 相同的当前信息，但不改写输入。
- `remember({text, key?})`：写入自己的记忆。`text` 非空且最多 4000 字符；相同 `key` 相同内容返回 `duplicate=true`，相同 `key` 不同内容拒绝；超过上限丢弃最早记忆。
- `recall({query})`：在自己的记忆中做子串匹配，`query` 留空返回全部。

导出的中文工具为：`记住`（remember）、`回忆`（recall）、`查看处境`（look）。

`nearby` 来自 `ctx.network.nodes(channels=['movement'])` 的真实返回数组，每项包含 `id`、`path`、`strength` 与 `profile`。`profile` 只采集其他节点在本模块命名空间发布的、且被本角色 `public_fields` 允许的字段；未发布或未知时为空对象，不会用节点 id 或其他字段编造。公开资料会显示在 `tail` 的附近可达描述中。

## 装配示例

```json
{
  "config": {
    "persona": "你是镇上的图书管理员，说话简短可靠。",
    "common": "只根据自己看到和记得的事回答。",
    "map": "镇广场北接北林，东边是集市。",
    "opening": "你刚整理完书架，听见门口有人走近。",
    "clock": "town-clock",
    "max_memories": 50,
    "public_fields": ["name", "gender", "profession", "age_group"],
    "knowledge": [
      {
        "id": "farmer",
        "when": {"profession": "农夫"},
        "text": "你熟悉节气、土壤和庄稼的收成。"
      },
      {
        "id": "pregnancy",
        "when": {"pregnant": true},
        "text": "你了解孕期需要多休息和补充营养。"
      }
    ]
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
