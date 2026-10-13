# Agent 可见描述与文档地址

本页供人工检查，不注入 Agent。下面的描述从本次成品源码提取，正文按原文列出。组件拆分迁移的既有指南保持原职责；通道指南仍按历史存在情况加载。

## 工具描述原文

### read_round

来源：`components/network_presets/discussion_group/implementation.js:129`

```text
读取本组上轮讨论快照；不读取本轮其他人的实时提交。
```

### submit_round

来源：`components/network_presets/discussion_group/implementation.js:134`

```text
向公共黑板追加本轮发言并结束本轮。
```

### skip_round

来源：`components/network_presets/discussion_group/implementation.js:158`

```text
明确跳过本轮并结束。
```

### datanet_discuss

来源：`components/network_presets/discussion_group/implementation.js:277`

```text
运行已创建的五人讨论组；每轮10次请求。所有人只看到同一上轮快照，最终由Recorder写成果。
```

### write_resident_text

来源：`components/nodes/text/controller.js:39`

```text
写入有写入连接的常驻文本。target只能选择这些常驻文本节点；只有一个目标时可省略。
```

### datanet_skill

来源：`components/skills/network_management/implementation.js:121`

```text
列出或加载获准能力包。load同时加载Skill文档并授予包声明的工具箱，无逐项二次授权；read按需读取已加载Skill的参考。
```

### datanet_send_message

来源：`components/toolboxes/agent_messaging/router.js:44`

```text
向自己的管理者或直接被管理的 Agent 发信；运行中插话，空闲时唤醒。
```

### e.reply_tool

来源：`components/toolboxes/agent_messaging/router.js:48`

```text
仅用来回复此条消息，调用一次后失效
```

### experience_query

来源：`components/toolboxes/experience/implementation.js:56`

```text
查询经验线索，默认包括已验证和待审核；status可筛选。待审核不代表建议可靠，不自动加载；不授予权限。
```

### experience_submit

来源：`components/toolboxes/experience/implementation.js:108`

```text
提交已解决并验证的问题为候选经验；不会自动发布。未解决阻塞使用 datanet_feedback。
```

### experience_review

来源：`components/toolboxes/experience/implementation.js:139`

```text
仅获授权维护者使用：查看候选、审核发布、合并重复、停用过期经验或set_core调整常加载。推广候选仍须维护者确认；发布前核实证据和版本。
```

### node_read

来源：`components/toolboxes/network_access/implementation.js:40`

```text
从所属节点出发读取网络数据，仍检查接口权限。文本用method=key,key=content；可以选target筛选可达目标。
```

### node_write

来源：`components/toolboxes/network_access/implementation.js:49`

```text
从所属节点出发向可写目标写入。
```

### network_structure

来源：`components/toolboxes/network_access/implementation.js:61`

动态描述的源模板（运行时替换变量）：

```text
`从所属节点查看连接摘要，默认使用最大depth，起点第0层，每个接口计1层；最大depth=${maxDepth}表示查看全部获准拓扑。只查看结构，不扩大数据或操作权限。`
```

### node_list

来源：`components/toolboxes/network_access/implementation.js:82`

```text
发现所属节点可达的节点。
```

### node_tools

来源：`components/toolboxes/network_access/implementation.js:85`

```text
该节点向你暴露允许你使用的工具，这并不是该节点的工具列表
```

### node_invoke

来源：`components/toolboxes/network_access/implementation.js:100`

```text
按已发现定义调用可达节点工具。
```

### handle_problem

来源：`components/toolboxes/problem_handling/implementation.js:93`

```text
遇到影响任务继续的问题，从这里开始处理；按需加载经验查询、获准排障流程和工具。进入不代表上报，也不增加任何业务权限。简单参数错误可正常重试。
```

### problem_attempt

来源：`components/toolboxes/problem_handling/implementation.js:143`

```text
查过经验后开始验证方案。有experience_id代表尝试查询到的经验；不填则自行修复，必须拥有self_repair授权。只使用原有业务工具。
```

### problem_resolved

来源：`components/toolboxes/problem_handling/implementation.js:154`

```text
问题已解决且完成实际工具验证后结束排障。填简短依据；自行修复须先提交候选经验。记录成功复用并撤下临时工具，不自动提升常加载。
```

### problem_defer

来源：`components/toolboxes/problem_handling/implementation.js:173`

```text
结束本次排障但不标记解决。仅当当前委托仍可继续或允许交付失败结果时使用；必须记录原因、未解决影响及继续/交付依据。保留尝试记录与提示，不报错、不结束任务、不计成功经验。
```

### datanet_feedback

来源：`components/toolboxes/problem_handling/implementation.js:232`

```text
仅当未解决问题确实阻塞自身当前委托时上报并停止。必填task_blocker说明无法继续或交付的原因；下属失败不自动等于自身阻塞。missing_tool/permission_denied使用固定短文本，只有other填写message。可交付失败结果时用problem_defer后正常汇报。
```

### datanet_resolve_feedback

来源：`components/toolboxes/problem_handling/implementation.js:291`

```text
仅限处理`datanet_feedback`的通道:管理者查看并修复真实报错节点，可补充指令、职责或工具箱。
```

### datanet_recovery_status

来源：`components/toolboxes/problem_handling/implementation.js:469`

```text
查看已恢复 Agent、网络讨论状态和中断时结果不明的操作；这些操作不会自动重放。
```

### incident_query

来源：`components/tools/execution_records/implementation.js:45`

```text
查询自动收集的阻塞和执行异常，包括未解决现象与重试记录；它们不是已验证经验。
```

### incident_resolve

来源：`components/tools/execution_records/implementation.js:73`

```text
报告者、管理者或获授权经验维护者可标记阻塞已解决。必须提供该节点在报错后正常完成的retry_run_id和具体结果依据；补工具或改提示词本身不能证明解决。可关联待审核或已验证经验ID。
```

### datanet_create_agent

来源：`components/tools/network_management/implementation.js:71`

```text
在获准节点挂载 Agent，选择职责预设与私有工具箱。
```

### datanet_call_agent

来源：`components/tools/network_management/implementation.js:107`

```text
向已有下属 Agent 委托任务；没有子 Agent 时不要使用本工具，也不要用它代替自己的工作。目标须读可达且符合管理范围；会话上下文保留。讨论成员自身由黑板调度。
```

### datanet_manage_agent

来源：`components/tools/network_management/implementation.js:178`

```text
查看或调整获准 Agent 的提示词与会话。
```

### datanet_agent_capabilities

来源：`components/tools/network_management/implementation.js:233`

```text
查看宿主允许为子 Agent 装配的工具箱。工具箱私有，不可跨 Agent 调用工具或 Skill。
```

### datanet_presets

来源：`components/tools/network_management/implementation.js:248`

```text
查看预设预览；指定preset查看网络的详细使用说明。
```

### datanet_interfaces

来源：`components/tools/network_management/implementation.js:274`

```text
查看、新增、修改或删除获准节点的读写接口。
```

### datanet_create_node

来源：`components/tools/network_management/implementation.js:334`

```text
创建数据或组织子节点，可选择预设或自定义受支持类型。
```

### datanet_create_network

来源：`components/tools/network_management/implementation.js:379`

```text
选择配置包创建网络；返回structure为新建网络读写连接摘要（实际ID），包括父节点挂载关系。以返回ID操作，不要猜测路径。discussion_group 会挂载五个持久 Harness Agent：project_nodes可引用多个已有查询文本；不提供时必须填写project正文，两者只选一种。number_network 是通用数字网络。
```

### datanet_reports_channel

来源：`components/tools/reports/channel.js:12`

```text
查询你发起的委托或获准归档范围内的报告。进入后加载报告结构、索引用法和专用读取工具；这是普通查询入口，不启动排障或重试。
```

### datanet_reports_query

来源：`components/tools/reports/channel.js:17`

```text
按请求、委托或节点查询获授权报告索引及实际委托拓扑，返回可直接读取的相对路径；不返回报告正文。省略请求和委托时查询当前请求。
```

### datanet_report_read

来源：`components/tools/reports/channel.js:20`

```text
按索引路径读取获授权报告文件，或读取按权限过滤的 node-index.json、topology.json。长文件按字符分页；路径不扩大权限。
```

### 查询文本工具 query_text_<节点散列>

来源：`components/nodes/text/controller.js`。先拼接该文本节点的标识，再换行添加正文描述：

```text
读取该查询文本，将当前正文加入上下文；需要时再次查询。
```

### node_tools 空返回

```text
该节点并未有向你开放的工具
```

### 常驻公共笔记标识

其中“小组ID”替换为实际小组 ID：

```text
[公共笔记：小组ID/notebook](由recorder维护)
```

## Agent 指南和 Skill 正文地址

以下是成品中的实际位置，可直接点击。绝对路径以本次交付目录为准，组件运行时按相对路径定位。

| 内容 | 文档 |
|---|---|
| components/agent_presets/coordinator/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/coordinator/prompt.md) |
| components/agent_presets/coordinator/python/datanet/components/agents/coordinator/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/coordinator/python/datanet/components/agents/coordinator/prompt.md) |
| components/agent_presets/discussion_leader/python/datanet/components/agents/discussion_leader/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/discussion_leader/python/datanet/components/agents/discussion_leader/prompt.md) |
| components/agent_presets/discussion_member/python/datanet/components/agents/discussion_member/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/discussion_member/python/datanet/components/agents/discussion_member/prompt.md) |
| components/agent_presets/discussion_recorder/python/datanet/components/agents/discussion_recorder/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/discussion_recorder/python/datanet/components/agents/discussion_recorder/prompt.md) |
| components/agent_presets/experiment_report/python/datanet/components/agents/experiment_report/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/experiment_report/python/datanet/components/agents/experiment_report/prompt.md) |
| components/agent_presets/leader/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/leader/prompt.md) |
| components/agent_presets/member/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/member/prompt.md) |
| components/agent_presets/number_manager/python/datanet/components/agents/number_manager/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/number_manager/python/datanet/components/agents/number_manager/prompt.md) |
| components/agent_presets/number_worker/python/datanet/components/agents/number_worker/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/number_worker/python/datanet/components/agents/number_worker/prompt.md) |
| components/agent_presets/operator/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/operator/prompt.md) |
| components/agent_presets/recorder/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/recorder/prompt.md) |
| components/agent_presets/worker/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/agent_presets/worker/prompt.md) |
| components/network_presets/creation_validation/python/datanet/components/networks/creation_validation/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/network_presets/creation_validation/python/datanet/components/networks/creation_validation/prompt.md) |
| components/network_presets/discussion_group/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/network_presets/discussion_group/AGENTS.md) |
| components/network_presets/number_network/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/network_presets/number_network/AGENTS.md) |
| components/network_presets/project_root/python/resources/agent/prompt.md | [prompt.md](E:/DataNet-模块化成品/components/network_presets/project_root/python/resources/agent/prompt.md) |
| components/skills/network_management/resources/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/skills/network_management/resources/AGENTS.md) |
| components/skills/network_management/resources/SKILL.md | [SKILL.md](E:/DataNet-模块化成品/components/skills/network_management/resources/SKILL.md) |
| components/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md) |
| components/toolboxes/network_access/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/toolboxes/network_access/AGENTS.md) |
| components/toolboxes/problem_handling/docs/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/toolboxes/problem_handling/docs/AGENTS.md) |
| components/toolboxes/problem_handling/docs/RECOVERY_LIMITS.md | [RECOVERY_LIMITS.md](E:/DataNet-模块化成品/components/toolboxes/problem_handling/docs/RECOVERY_LIMITS.md) |
| components/toolboxes/problem_handling/guides/datanet_recovery_status/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/toolboxes/problem_handling/guides/datanet_recovery_status/AGENTS.md) |
| components/toolboxes/problem_handling/guides/datanet_resolve_feedback/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/toolboxes/problem_handling/guides/datanet_resolve_feedback/AGENTS.md) |
| components/tools/network_management/guides/datanet_create_agent/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/tools/network_management/guides/datanet_create_agent/AGENTS.md) |
| components/tools/network_management/guides/datanet_create_node/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/tools/network_management/guides/datanet_create_node/AGENTS.md) |
| components/tools/network_management/guides/datanet_interfaces/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/tools/network_management/guides/datanet_interfaces/AGENTS.md) |
| components/tools/network_management/guides/datanet_manage_agent/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/tools/network_management/guides/datanet_manage_agent/AGENTS.md) |
| components/tools/reports/guides/datanet_reports/AGENTS.md | [AGENTS.md](E:/DataNet-模块化成品/components/tools/reports/guides/datanet_reports/AGENTS.md) |

根网络的项目、进度与工作资料也位于 `components/network_presets/project_root/python/resources/`，作为查询文本使用。`adapters/harness/docs/INSTRUCTION_LOADING.md` 描述装载实现，供维护者阅读。

## 预设和工具箱的描述原文

### agent_presets/coordinator

来源：`components/agent_presets/coordinator/component.json`

```text
协调员：对接小组、处理任务交接和依赖、回收成果；按上级委托组装或调整子网络。
```

### agent_presets/leader

来源：`components/agent_presets/leader/component.json`

```text
小组内领导者：负责组内方向、分歧决策并参与讨论；不是组外协调员。单独创建该 Agent 建议仅用于 discussion_group 网络预设的扩展，例如增加成员数量；谨慎脱离该预设网络架构使用，须配套讨论调度、黑板工具与共享资料。组外协调应选择 coordinator。
```

### agent_presets/member

来源：`components/agent_presets/member/component.json`

```text
小组普通成员：参与分析、提出建议并维护私人笔记。单独创建该 Agent 建议仅用于 discussion_group 网络预设的扩展，例如增加成员数量；谨慎脱离该预设网络架构使用，须配套讨论调度、黑板工具与共享资料。组外协调应选择 coordinator。
```

### agent_presets/operator

来源：`components/agent_presets/operator/component.json`

```text
操纵专员：按委托执行实际工作、验证与测试；默认个人建议只汇报；上级可在当前任务中明确授予自主测试、调试等权限，按其范围执行。默认无组网或成员管理能力。
```

### agent_presets/recorder

来源：`components/agent_presets/recorder/component.json`

```text
小组内记录者：负责公共笔记、重要进展与最终成果归档，并参与讨论。单独创建该 Agent 建议仅用于 discussion_group 网络预设的扩展，例如增加成员数量；谨慎脱离该预设网络架构使用，须配套讨论调度、黑板工具与共享资料。组外协调应选择 coordinator。
```

### toolboxes/agent_delegation

来源：`components/toolboxes/agent_delegation/box.json`

```text
所有 Agent 默认具备的任务委托能力；没有下属 Agent 时不使用，不包含创建或管理权限。
```

### toolboxes/agent_feedback

来源：`components/toolboxes/agent_feedback/box.json`

```text
所有 Agent 默认具备的阻塞反馈通道；上报创建者后结束当前轮，保留上下文。
```

### toolboxes/agent_management

来源：`components/toolboxes/agent_management/box.json`

```text
管理获准范围内的 Agent，委托任务；不借用其工具或 Skill。
```

### toolboxes/agent_messaging

来源：`components/toolboxes/agent_messaging/box.json`

```text
普通 Agent 默认装配的主动通信工具；讨论成员仅获得消息对应的临时回复入口。
```

### toolboxes/discussion

来源：`components/toolboxes/discussion/box.json`

```text
调度讨论，不访问成员私有执行能力。
```

### toolboxes/discussion_member

来源：`components/toolboxes/discussion_member/box.json`

```text
讨论成员私有的提交和跳过操作，只在讨论调度中装配。
```

### toolboxes/engineering

来源：`components/toolboxes/engineering/box.json`

```text
官方文件编辑和终端执行能力。
```

### toolboxes/experience_access

来源：`components/toolboxes/experience_access/box.json`

```text
默认经验与阻塞查询、候选提交；报告者或创建者可凭重试依据标记问题解决，不能发布经验。
```

### toolboxes/experience_maintenance

来源：`components/toolboxes/experience_maintenance/box.json`

```text
授权维护者审核、发布、合并和停用经验。
```

### toolboxes/file_reader

来源：`components/toolboxes/file_reader/box.json`

```text
官方只读文件检索能力。
```

### toolboxes/interface_management

来源：`components/toolboxes/interface_management/box.json`

```text
管理接口拓扑；目标连接权限在装配时确定。
```

### toolboxes/network_access

来源：`components/toolboxes/network_access/box.json`

```text
从所属节点发现、读取、写入和调用节点明确暴露的业务服务。
```

### toolboxes/network_management

来源：`components/toolboxes/network_management/box.json`

```text
网络管理组合包：查询预设、创建节点和子网络、管理接口和 Agent、委托任务、恢复状态及搭建指南。管理范围与自定义权限继承各小工具箱配置。
```

### toolboxes/network_management_skill

来源：`components/toolboxes/network_management_skill/box.json`

```text
允许按需加载网络管理Skill；加载即装配其声明的管理工具箱。
```

### toolboxes/node_creation

来源：`components/toolboxes/node_creation/box.json`

```text
选择预设或自定义受支持的节点、子网络。
```

### toolboxes/node_operations

来源：`components/toolboxes/node_operations/box.json`

```text
节点操作组合包：发现节点、读写数据、发现及调用显式暴露的节点服务。
```

### toolboxes/official_readonly

来源：`components/toolboxes/official_readonly/box.json`

```text
官方只读组合包：文件读取和搜索；不授予写文件或终端执行。
```

### toolboxes/official_skills

来源：`components/toolboxes/official_skills/box.json`

```text
官方 Skill 组合包：按官方 provider 筛选装配时已安装的 Skills，按需加载；不自动授予 Skill 所需其他工具。
```

### toolboxes/official_tools

来源：`components/toolboxes/official_tools/box.json`

```text
官方完整工具组合包：按官方工具名称清单与装配时客户端工具取交集；清单可配置，不自动包含第三方或 DataNet 工具。仅含 Skill 加载器，不授予 Skill 内容权限。
```

### toolboxes/problem_handling

来源：`components/toolboxes/problem_handling/box.json`

```text
默认问题处理入口：平时只展示handle_problem；进入后临时加载流程与排障工具，不上报、不增加业务权限。
```

### toolboxes/problem_steps

来源：`components/toolboxes/problem_steps/box.json`

```text
排障中的尝试、已解决退出、未解决退出工具，平时不展示。
```

### toolboxes/recovery

来源：`components/toolboxes/recovery/box.json`

```text
查看网络恢复状态和结果不明的操作。
```

### toolboxes/self_repair

来源：`components/toolboxes/self_repair/box.json`

```text
允许Agent在原有工具权限内主动排障；仍需先查询经验，不授予任何终端、数据或管理工具。
```

### toolboxes/skill_loader

来源：`components/toolboxes/skill_loader/box.json`

```text
官方 Skill 加载器；允许的 Skill 在宿主配置中指定。
```

### toolboxes/topology_inspection

来源：`components/toolboxes/topology_inspection/box.json`

```text
仅查看所属连通网络的拓扑，可穿透私有连接；不授予数据、工具、写入或管理权限。
```
