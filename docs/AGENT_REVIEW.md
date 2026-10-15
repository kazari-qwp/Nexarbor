# Agent 文档与工具描述

本次生命周期与异步改动见 [检查原文](AGENT_LIFECYCLE_REVIEW.md)。本文供人工检查；实际提示词和指南从下面的组件资源读取。

## 小组提示词

- [leader](../extensions/multi_agent/nodes/agent_leader/prompt.md)：来自 `D:/桌面/leader.docx`，已将个人笔记访问改为 Agent 自有记忆工具。
- [recorder](../extensions/multi_agent/nodes/agent_recorder/prompt.md)：来自 `D:/桌面/recorder.docx`，已将个人笔记访问改为 Agent 自有记忆工具。
- [member](../extensions/multi_agent/nodes/agent_member/prompt.md)：来自 `D:/桌面/member.docx`，已将个人笔记访问改为 Agent 自有记忆工具。

Python 旧配置包的 prompt_path 已指向以上同一份正文。

## 通道指南与 Skill

- [extensions/multi_agent/network_presets/discussion_group/AGENTS.md](../extensions/multi_agent/network_presets/discussion_group/AGENTS.md)
- [extensions/multi_agent/network_presets/number_network/AGENTS.md](../extensions/multi_agent/network_presets/number_network/AGENTS.md)
- [extensions/multi_agent/capabilities/network_management/resources/AGENTS.md](../extensions/multi_agent/capabilities/network_management/resources/AGENTS.md)
- [extensions/multi_agent/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md](../extensions/multi_agent/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md)
- [extensions/multi_agent/toolboxes/network_access/AGENTS.md](../extensions/multi_agent/toolboxes/network_access/AGENTS.md)
- [extensions/multi_agent/toolboxes/problem_handling/docs/AGENTS.md](../extensions/multi_agent/toolboxes/problem_handling/docs/AGENTS.md)
- [extensions/multi_agent/toolboxes/problem_handling/guides/datanet_recovery_status/AGENTS.md](../extensions/multi_agent/toolboxes/problem_handling/guides/datanet_recovery_status/AGENTS.md)
- [extensions/multi_agent/toolboxes/problem_handling/guides/datanet_resolve_feedback/AGENTS.md](../extensions/multi_agent/toolboxes/problem_handling/guides/datanet_resolve_feedback/AGENTS.md)
- [extensions/multi_agent/capabilities/tools_network_management/guides/datanet_create_agent/AGENTS.md](../extensions/multi_agent/capabilities/tools_network_management/guides/datanet_create_agent/AGENTS.md)
- [extensions/multi_agent/capabilities/tools_network_management/guides/datanet_create_node/AGENTS.md](../extensions/multi_agent/capabilities/tools_network_management/guides/datanet_create_node/AGENTS.md)
- [extensions/multi_agent/capabilities/tools_network_management/guides/datanet_interfaces/AGENTS.md](../extensions/multi_agent/capabilities/tools_network_management/guides/datanet_interfaces/AGENTS.md)
- [extensions/multi_agent/capabilities/tools_network_management/guides/datanet_manage_agent/AGENTS.md](../extensions/multi_agent/capabilities/tools_network_management/guides/datanet_manage_agent/AGENTS.md)
- [extensions/multi_agent/capabilities/reports/guides/datanet_reports/AGENTS.md](../extensions/multi_agent/capabilities/reports/guides/datanet_reports/AGENTS.md)

## 工具描述原文

### read_round

来源：[extensions/multi_agent/network_presets/discussion_group/tools.json](../extensions/multi_agent/network_presets/discussion_group/tools.json)

```text
读取本组上轮讨论快照；不读取本轮其他人的实时提交。
```

### submit_round

来源：[extensions/multi_agent/network_presets/discussion_group/tools.json](../extensions/multi_agent/network_presets/discussion_group/tools.json)

```text
向公共黑板追加本轮发言并结束本轮。
```

### skip_round

来源：[extensions/multi_agent/network_presets/discussion_group/tools.json](../extensions/multi_agent/network_presets/discussion_group/tools.json)

```text
明确跳过本轮并结束。
```

### datanet_discuss

来源：[extensions/multi_agent/network_presets/discussion_group/tools.json](../extensions/multi_agent/network_presets/discussion_group/tools.json)

```text
运行已创建的五人讨论组；每轮10次请求。所有人只看到同一上轮快照，最终由Recorder写成果。
```

### datanet_skill

来源：[extensions/multi_agent/capabilities/network_management/tools.json](../extensions/multi_agent/capabilities/network_management/tools.json)

```text
列出或加载获准能力包。load同时加载Skill文档并授予包声明的工具箱，无逐项二次授权；read按需读取已加载Skill的参考。
```

### experience_query

来源：[extensions/multi_agent/toolboxes/experience/tools.json](../extensions/multi_agent/toolboxes/experience/tools.json)

```text
查询经验线索，默认包括已验证和待审核；status可筛选。待审核不代表建议可靠，不自动加载；不授予权限。
```

### experience_submit

来源：[extensions/multi_agent/toolboxes/experience/tools.json](../extensions/multi_agent/toolboxes/experience/tools.json)

```text
提交已解决并验证的问题为候选经验；不会自动发布。未解决阻塞使用 datanet_feedback。
```

### experience_review

来源：[extensions/multi_agent/toolboxes/experience/tools.json](../extensions/multi_agent/toolboxes/experience/tools.json)

```text
仅获授权维护者使用：查看候选、审核发布、合并重复、停用过期经验或set_core调整常加载。推广候选仍须维护者确认；发布前核实证据和版本。
```

### node_read

来源：[extensions/multi_agent/toolboxes/network_access/tools.json](../extensions/multi_agent/toolboxes/network_access/tools.json)

```text
从所属节点出发读取网络数据，仍检查接口权限。文本用method=key,key=content；可以选target筛选可达目标。
```

### node_write

来源：[extensions/multi_agent/toolboxes/network_access/tools.json](../extensions/multi_agent/toolboxes/network_access/tools.json)

```text
从所属节点出发向可写目标写入。
```

### network_structure

来源：[extensions/multi_agent/toolboxes/network_access/tools.json](../extensions/multi_agent/toolboxes/network_access/tools.json)

```text
从所属节点查看连接摘要，默认使用最大depth，起点第0层，每个接口计1层；最大depth=100表示查看全部获准拓扑。只查看结构，不扩大数据或操作权限。
```

### node_list

来源：[extensions/multi_agent/toolboxes/network_access/tools.json](../extensions/multi_agent/toolboxes/network_access/tools.json)

```text
发现所属节点可达的节点。
```

### node_tools

来源：[extensions/multi_agent/toolboxes/network_access/tools.json](../extensions/multi_agent/toolboxes/network_access/tools.json)

```text
该节点向你暴露允许你使用的工具，这并不是该节点的工具列表
```

### node_invoke

来源：[extensions/multi_agent/toolboxes/network_access/tools.json](../extensions/multi_agent/toolboxes/network_access/tools.json)

```text
按已发现定义调用可达节点工具。
```

### handle_problem

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
遇到影响任务继续的问题，从这里开始处理；按需加载经验查询、获准排障流程和工具。进入不代表上报，也不增加任何业务权限。简单的参数或格式错误，不要进入此通道。
```

### problem_attempt

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
查过经验后开始验证方案。有experience_id代表尝试查询到的经验；不填则自行修复，必须拥有self_repair授权。只使用原有业务工具。
```

### problem_resolved

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
问题已解决且完成实际工具验证后结束排障。填简短依据；自行修复须先提交候选经验。记录成功复用并撤下临时工具，不自动提升常加载。
```

### problem_defer

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
结束本次排障但不标记解决。仅当当前委托仍可继续或允许交付失败结果时使用；必须记录原因、未解决影响及继续/交付依据。保留尝试记录与提示，不报错、不结束任务、不计成功经验。
```

### datanet_feedback

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
仅当未解决问题确实阻塞自身当前委托时上报并停止。必填task_blocker说明无法继续或交付的原因；下属失败不自动等于自身阻塞。missing_tool/permission_denied使用固定短文本，只有other填写message。可交付失败结果时用problem_defer后正常汇报。
```

### datanet_resolve_feedback

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
仅限处理`datanet_feedback`的通道:管理者查看并修复真实报错节点，可补充指令、职责或工具箱。
```

### datanet_recovery_status

来源：[extensions/multi_agent/toolboxes/problem_handling/tools.json](../extensions/multi_agent/toolboxes/problem_handling/tools.json)

```text
查看已恢复 Agent、网络讨论状态和中断时结果不明的操作；这些操作不会自动重放。
```

### incident_query

来源：[extensions/multi_agent/capabilities/execution_records/tools.json](../extensions/multi_agent/capabilities/execution_records/tools.json)

```text
查询自动收集的阻塞和执行异常，包括未解决现象与重试记录；它们不是已验证经验。
```

### incident_resolve

来源：[extensions/multi_agent/capabilities/execution_records/tools.json](../extensions/multi_agent/capabilities/execution_records/tools.json)

```text
报告者、管理者或获授权经验维护者可标记阻塞已解决。必须提供该节点在报错后正常完成的retry_run_id和具体结果依据；补工具或改提示词本身不能证明解决。可关联待审核或已验证经验ID。
```

### datanet_create_agent

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
创建 Agent 节点，自动配备独立会话、个人记忆和读写工具；配置匹配时复用当前网络池中的 Agent。
```

### datanet_call_agent

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
向获准的下属 Agent 异步委托任务，立即返回委托 ID；同一 Agent 按提交顺序执行，结果由框架回送。
```

### datanet_manage_agent

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
查看或调整获准 Agent 的提示词与会话。
```

### datanet_agent_capabilities

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
查看宿主允许为子 Agent 装配的工具箱。工具箱私有，不可跨 Agent 调用工具或 Skill。
```

### datanet_presets

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
查看预设与已保存的离线网络；指定 ID 查看对应说明或保存清单。
```

### datanet_interfaces

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
管理获准节点的链接；拆除导致节点与根断联时，确认取消、保存结构或分解进入复用池。
```

### datanet_create_node

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
创建数据或组织子节点，可选择预设或自定义受支持类型。
```

### datanet_create_network

来源：[extensions/multi_agent/capabilities/tools_network_management/tools.json](../extensions/multi_agent/capabilities/tools_network_management/tools.json)

```text
按预设创建网络，返回实际节点ID与连接摘要。
```

## 动态工具描述原文

来源：[extensions/multi_agent/capabilities/text/python/datanet/features/nodes/text/runtime.py](../extensions/multi_agent/capabilities/text/python/datanet/features/nodes/text/runtime.py)

QUERY_DESCRIPTION（第 4 行）：

```text
读取该查询文本，将当前正文加入上下文；需要时再次查询。
```

WRITE_DESCRIPTION（第 5 行）：

```text
写入有写入连接的常驻文本。target只能选择这些常驻文本节点；只有一个目标时可省略。
```

来源：[extensions/multi_agent/capabilities/agent_messaging/python/datanet/features/toolboxes/agent_messaging/runtime.py](../extensions/multi_agent/capabilities/agent_messaging/python/datanet/features/toolboxes/agent_messaging/runtime.py)

SEND_DESCRIPTION（第 7 行）：

```text
向自己的管理者或直接被管理的 Agent 发信；运行中插话，空闲时唤醒。
```

REPLY_DESCRIPTION（第 8 行）：

```text
仅用来回复此条消息，调用一次后失效
```

来源：[extensions/multi_agent/capabilities/reports/python/datanet/features/tools/reports/runtime.py](../extensions/multi_agent/capabilities/reports/python/datanet/features/tools/reports/runtime.py)

description（第 98 行）：

```text
查询你发起的委托或获准归档范围内的报告。进入后加载报告结构、索引用法和专用读取工具；这是普通查询入口，不启动排障或重试。
```

description（第 222 行）：

```text
按请求、委托或节点查询获授权报告索引及实际委托拓扑，返回可直接读取的相对路径；不返回报告正文。省略请求和委托时查询当前请求。
```

description（第 223 行）：

```text
按索引路径读取获授权报告文件，或读取按权限过滤的 node-index.json、topology.json。长文件按字符分页；路径不扩大权限。
```
