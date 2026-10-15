# 按需通信与轮次尾部：Agent 文本原文

修改的文档：
- `extensions/foundation/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md`
- `extensions/multi_agent/network_presets/discussion_group/members/AGENTS.md`

新增工具描述（来源 `extensions/foundation/toolboxes/agent_messaging/tools.json`）：

`datanet_contacts_channel`：进入联系通道，查看可主动联系的 Agent。

`datanet_pending_messages`：查看当前待回复消息。

通信尾部原文：存在待回复消息。

讨论尾部模板：

```text
[讨论状态：{actor}]
当前轮数：{round}/{total}。
当前请求次数：{count}/10。
```

Recorder 最终汇总时，将轮数一行替换为：讨论已结束；当前阶段：成果汇总。

通信查询工具均无参数；待回复查询仅返回自己的消息。通讯录只在查询入口的工具结果里提供，通信 AGENTS 遵循已有文档加载周期。普通 Agent 保留原主动通信权限，讨论成员只获得待回复查询及收到消息对应的临时回复工具。
