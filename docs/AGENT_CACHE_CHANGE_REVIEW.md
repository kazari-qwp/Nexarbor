# 本次 Agent 可见文本修改

## 文档

- `extensions/multi_agent/network_presets/discussion_group/members/AGENTS.md`：增加本轮请求次数位于尾部、上限 10 次的说明。
- `extensions/multi_agent/network_presets/decentralized_group/members/AGENTS.md`：说明尾部是共享记录摘要，候选全文用状态工具读取，记录 ID 或关键词可查询完整记录。

三个角色预设提示词没有修改。工具和工具箱的简短描述、参数说明没有修改。

## 新增或调整的运行时文字原文

经验记录，来源 `extensions/multi_agent/capabilities/experience/python/datanet/features/toolboxes/experience/runtime.py`，方括号值为实际经验字段：

```text
经验只作参考；待审核不代表可靠，权限不变。
[{id}; {version}] {trigger}：{advice}
```

讨论计数，来源 `extensions/multi_agent/capabilities/discussion_group/python/datanet/features/network_presets/discussion_group/runtime.py`：

```text
[讨论状态：{actor}]
当前请求次数：{count}/10。
```

通讯录继续使用原文前缀 `可主动联系：`，没有发送权限时为 `可主动联系：[]`；待回复消息仍使用 `待回复消息：`。前者进入历史，后者进入尾部。来源 `extensions/multi_agent/capabilities/agent_messaging/python/datanet/features/toolboxes/agent_messaging/runtime.py`。

排障提示、管理者和下属反馈的文字沿用原文，位置改为当前排障在尾部，其余记录在历史。来源 `extensions/multi_agent/capabilities/problem_handling/python/datanet/features/toolboxes/problem_handling/runtime.py`。

协作状态仍使用 `[协作状态：{group_id}]` 标识；JSON 的 `recent_entries` 改为 ID、成员、类型和 `preview`，候选保留 ID、批准成员与验收路径；完整内容仍由状态工具返回。来源 `extensions/multi_agent/capabilities/decentralized_group/python/datanet/features/network_presets/decentralized_group/runtime.py`。
