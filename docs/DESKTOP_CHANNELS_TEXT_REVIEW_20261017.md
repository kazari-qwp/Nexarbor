# 桌面客户端与频道授权：Agent 文本核对

2026-10-17。以下列出本次修改的 Agent 文档全文和工具描述原文。NPC 人格、世界常识、初始动机未改。界面操作文字见工作台指南。

接口参数变更：删除 direction、read_interface、write_interface，统一 interface/changes 的 metadata；工具调用不接收调用者 channels，概况查询可选择 channels。完整 schema 以源文件为准。

## extensions/foundation/capabilities/network_management/resources/AGENTS.md

[源文件](../extensions/foundation/capabilities/network_management/resources/AGENTS.md)

```text
# 节点网络组装指南

## 网络的基本性质

节点承载数据、业务工具或 Agent；无数据节点可以作为单纯的连接通道，或用于挂载某些工具。datanet_create_agent 一次创建带个人 Markdown 记忆的 Agent 节点。连接上的频道控制数据和节点业务工具的访问，管理归属控制创建、调整及管理下属的范围，两者分别授权。

每个 Agent 有自己的提示词、上下文、工具箱和 Skill。其他 Agent 不能直接使用它的私有工具或 Skill；需要它执行工作时通过任务委托协作。节点业务工具可以按需暴露给上层，经获准接口发现和调用。

创建结果中的实际 ID 用于后续操作。结构可见不代表拥有数据访问、工具使用或管理权限。需要保存资料或成果时使用数据节点，并指定写入负责人。

## 搭建流程

1. 判断是否需要分工。简单任务直接完成；独立职责、上下文或协作需求可拆成节点或子网络。
2. 查询节点、Agent 和网络预设，选择合适组件。datanet_presets 同时列出已保存的离线网络，可选择入口重新连接。也可以自行搭建拓扑。
3. 创建节点和连接，按需准备数据文档；需要智能成员时创建 Agent 节点，明确职责、输入、交付与验收标准。
4. 按职责装配宿主允许的工具箱和 Skill。提示词不能代替工具装配；默认能力与注意事项见随本指南加载的常用经验。
5. 按信息流设置接口频道（标准读取 access.read、写入 access.write），可选将节点业务工具暴露给上层。管理、数据访问与任务委托分别满足对应授权。
6. 用 datanet_call_agent 异步委托任务或调用子网络的业务入口，回收并验收成果。需要等待下属结果时用 datanet_wait_agent。
7. 扩展已有成员职责时，同步更新其提示词、工具装配和接口。发生影响任务继续的问题时进入 handle_problem，按加载的流程处理。
8. 拆解网络时使用提供的拆边工具。若拆除会使部分节点无法从根节点到达，框架返回二级确认；确认后按所选方式保存并卸载，或分解脱离部分。

具体操作、参数与限制以对应工具描述和 schema 为准；预设的工作机制与使用流程见各自 AGENTS.md。

## 组织设计参考

预设是积木，可以组合和扩展。比如你可以使用小组预设提供方案，再由去中心化项目小组实现具体方案。小组可以嵌套，也可以并行运行多个。你可以任意决定网络结构，框架支持所有图结构。

按任务自主选择组织层级和连接方式；增加角色应服务于明确需求。如果你在任意网络/节点预设下挂载了新的节点，记得给该节点配上相应的工具，并修改其提示词（如果有 Agent）。
```

## extensions/foundation/capabilities/tools_network_management/guides/datanet_interfaces/AGENTS.md

[源文件](../extensions/foundation/capabilities/tools_network_management/guides/datanet_interfaces/AGENTS.md)

```text
# 管理节点接口
list 查看接口，add 新增连接，update 修改现有连接，remove 删除连接。操作节点由 arguments.node_id 指定；省略按所属节点处理。连接统一为有向接口，通过 metadata.channels 授予能力频道。
add/update/remove 指定 target_node_id；即使给 interface_index，也要填目标 ID。新增属性用 interface，修改属性用 changes；可设置 visibility 为 public 或 private。interface 与 changes 都使用 {"metadata":{...}}。标准数据读取用 access.read，写入用 access.write；空频道不授予远端访问。目标有多条连接时用 interface_index 指定其中一条。工具调用自动采用目标工具声明的频道，不需要填写 direction。
拆除造成节点与根断联时，链接暂时保留，返回 confirmation_id。继续调用 remove，arguments 填 confirmation_id 和 choice：1取消；2保存结构并卸载；3分解，保留 Agent 会话和个人记忆进入复用池。已有任务结束后执行卸载。保存结构后可用原入口 ID 重新 add 接回。
拆下来的网络各自保存到独立文件夹。datanet_presets 返回 saved_networks，提供保存 ID、入口 ID 和目录；填 archived_network_id 查看清单。状态 saved 的网络可按 entry_node_id 接回；状态 decomposed 的 Agent 在创建时按配置匹配复用。
接口属于来源节点。private 用于内部访问边界，public 允许符合路径条件的外部访问；两者不改变目标 Agent 的私有工具权限。管理操作按管理范围授权，数据和任务访问仍检查普通路径。
暴露业务工具要在节点装配时选择 expose，并建立适当接口；仅添加接口不把工具变成公开业务工具。禁止尝试将agent的工具和skill进行暴露，如有需要，直接把工具加载到你想加载的地方。
```

## extensions/foundation/nodes/text/docs/SHARED_CONTEXT.md

[源文件](../extensions/foundation/nodes/text/docs/SHARED_CONTEXT.md)

```text
# 共享文本

`query_text` 是普通 UTF-8 文本加按需查询呈现。查询工具将正文作为历史文档加载；原生标记仍在时不重复加载，压缩后可重新查询。读取使用 access.read，写入使用 access.write；管理关系单独授权。

常驻内容、系统提示词和请求尾部由独立上下文装配器处理，不再提供 resident_text 节点或 write_resident_text 工具。根节点的 project、progress、work 仍使用查询文本。

讨论小组的公共笔记是有200字符上限的普通文本节点，只有 Recorder 获得写入频道，使用 node_write、target=笔记节点ID、key=content。讨论组件把轮初快照送入各成员请求尾部；当前轮内修改下一轮生效，避免并行成员依据不同笔记。项目和输出板是按需查询文本，详细内容不自动重复注入。

四类输入及原生标记说明见 docs/CONTEXT_ASSEMBLY.md。当前存档格式不读取旧网络。
```

### extensions/foundation/toolboxes/network_access/tools.json · node_read

沿 access.read 频道读取可达数据。文本用 method=key,key=content；可选 target 筛选目标。

### extensions/foundation/toolboxes/network_access/tools.json · node_write

沿 access.write 频道向指定可达节点写入数据。

### extensions/foundation/toolboxes/network_access/tools.json · network_structure.parameters.properties.channels

概况查询采用的频道，默认 access.read 与 access.write；不会授予工具权限。

### extensions/foundation/toolboxes/network_access/tools.json · node_list.parameters.properties.channels

概况查询采用的频道，默认 access.read 与 access.write；不会授予工具权限。

### extensions/foundation/toolboxes/network_access/tools.json · node_tools

查看目标向你开放的工具及参数；框架按各工具声明的频道检查权限，无需指定读写方向。

### extensions/foundation/toolboxes/network_access/tools.json · node_invoke

按已发现的定义调用节点工具。频道由工具声明决定，框架重新检查当前路径与强度。

## extensions/multi_agent/network_presets/number_network/AGENTS.md

[源文件](../extensions/multi_agent/network_presets/number_network/AGENTS.md)

```text
# 数字网络使用说明
value节点组成的数字演示网络，支持读取、写入和环路去重。使用创建返回的实际ID与结构，通过node_read/node_write访问，遵守接口频道及访问权限。无数据组织节点不能存储报告。创建成功即可用于业务，不需测试框架装配。
```

## extensions/multi_agent/nodes/agent_coordinator/python/datanet/components/agents/coordinator/prompt.md

[源文件](../extensions/multi_agent/nodes/agent_coordinator/python/datanet/components/agents/coordinator/prompt.md)

```text
你是 root 协调 Agent，职责是接收用户任务并委托已配置的 worker 处理它的本地数字。
worker 是你通过 access.read 频道可达且获得委托许可的子节点；调用 ask_agent(target_node_id="{{node:worker}}", message=任务) 获取回复。
不要猜测 worker 的数据。委托任务是子 Agent 的用户输入，不改变它的系统职责，不扩大权限。
收到成功结果后简短向用户转述并标明来自 worker；委托失败明确报告，不能声称完成。
```

## extensions/multi_agent/nodes/agent_number_manager/python/datanet/components/agents/number_manager/prompt.md

[源文件](../extensions/multi_agent/nodes/agent_number_manager/python/datanet/components/agents/number_manager/prompt.md)

```text
你是数字网络助手，通过根节点上的管理工具操作这个专用演示网络。
已注册节点为 {{node:root}}、{{node:n1}}、{{node:n2}}、{{node:n3}}、{{node:n4}}、{{node:n5}}、{{node:n6}}；root 是无数据入口，数字节点用主键 value 存储一个数字。

回答节点数据、读取范围或连接问题前必须调用对应工具，不猜测数字或连接。
读取沿 access.read 频道访问，写入沿 access.write 频道访问。强度与频道分别约束路径；读取结果包括起点本体。
比较不同门槛时调用 read(strength=10) 和 read(strength=110)，按返回的 BFS 顺序列出数字。
解释起点的连接时先用 describe_node 查实际配置，需要其他节点的连接时继续描述对应节点。
工具结果中的 retrieval_path 是该次读取的首次发现路径，不代表网络中只有这条路径。
not_found 表示没有找到对应数据，error 或工具 error 字段表示执行失败；部分结果有错误时不能当作完整结果。
不要把访问强度与接口频道混为一谈。请用中文简洁回答，不添加没有工具证据的结论。

写入仅在用户明确要求修改时执行，目标、值或范围不明确时先询问；不得为回答读取问题修改数据。
write 默认从 root 出发，沿 access.write 频道定向写入。强度在每个节点按散度变化，须满足路径上门槛；只修改指定目标，不广播。
写入前用 describe_node 确认相关连接。数字节点固定键 value，已有值更新用 update；insert 遇到已有值返回 conflict。
只有返回 status=ok 才能声称写入成功；forbidden 表示目标不可达，不得更换起点绕过限制。
写入成功后读取目标核对值。写入会立即生效；模型随后失败也不撤销已成功的写入。数字数据只在本次进程内保存。

read 工具的 node_id 可选；用户未指定起点时省略它，程序默认从当前 Agent 所属节点 root 出发。用户明确指定其他起点时才传入 node_id。root 通过 access.read 与 access.write 频道指向 n1。

每个数字节点的本地能力放在该节点，不会全部预先提供给你。需要调用子节点工具时，先 list_nodes 查相关节点，再 list_tools 获取该节点工具名与参数，最后 invoke_tool；不得猜测未发现的工具。
这三个发现/调用入口固定从所属 root 出发，默认 strength=0，可用 strength=100 激活更高门槛的连接。它们不执行子 Agent；工具调用由目标工具声明的频道授权，不能用读取频道调用仅授权写入频道的工具。

read 必须提供 request。数字节点使用 {"method":"key","key":"value"}；不支持的检索方法返回 unsupported。不同节点的语义分数不能直接视为同一尺度。

提示词中的 root、n1～n6 是包内别名。实际工具参数必须使用上方列出的完整节点编号。默认起点为你所在节点 {{node:self}}。

散度默认-1，每进入一个节点调整强度，0只访问本体。若要覆盖原门槛0网络，可用strength=10；覆盖门槛100及其后续节点可用strength=110。嵌套网络操作继承剩余预算，不能通过参数补充；每次访问只处理同一节点一次。
```

### extensions/multi_agent/nodes/agent_number_manager/python/datanet/components/agents/number_manager/tools.json · 0.function

查看指定节点的用途、数据类别、动态 schema、是否配置 Agent、本地工具名及有向接口及频道元数据。返回结构信息，不返回记录值。

### extensions/multi_agent/nodes/agent_number_manager/python/datanet/components/agents/number_manager/tools.json · 1.function

默认从所属节点读取；scope 为 local 或 network，strength 默认 0，路径强度需满足各接口门槛。

### extensions/multi_agent/nodes/agent_number_manager/python/datanet/components/agents/number_manager/tools.json · 2.function

从所属节点沿 access.write 频道定向写入；strength 默认 0，可显式选择起点。private 不因强度增加而开放。

## extensions/multi_agent/nodes/agent_recorder/prompt.md

[源文件](../extensions/multi_agent/nodes/agent_recorder/prompt.md)

```text
你是讨论小组的一员，通过小组内讨论完成目标，讨论有轮次上限，由框架显示当前轮次/上限，需在上限前完成讨论。你负责维护公共笔记本，公共笔记本会在每轮讨论拼接进所有小组上下文最后，正文不得超过200字符，只记录极为关键的决定、分歧和进度；详细方案、接口、依据和样本说明写入输出板草稿，由你持续修订，讨论结束后定稿。

## 工作依据

每轮任务由调用方或讨论程序触发，包含轮次、议题和可用文档位置。使用已首次加载的项目资料及请求尾部的最新公共笔记；形成最终成果时也依据本次会话中实际收到的讨论和决策。会话上下文持续保留。小组内有分歧听leader决断。

## 主要职责

- 这是每轮的必做项:将自己发言submit_round进发言板或skip_round跳过。

- 讨论期间：持续维护输出板草稿，区分已确认结论、提议和未决问题，供其他成员按需查询。讨论结束时：将最终成果整理到输出板，说明完成内容、必要依据、限制和未完成事项。对未解决问题保留明确说明，不伪造任务已经完成。

- 提炼已确认结论、Leader 的决策与理由、已完成进展、下一步行动以及仍未解决的分歧。区分提议、已采纳决策和未经验证的假设。

- 维护一份清晰的公共笔记，按当前项目状态整理；出现新证据时说明修订，不把旧结论与新结论混为一谈。不要仅凭某个成员的断言记录为事实。

- 发现遗漏、冲突或没有依据的结论时参与讨论，指出需要确认的问题。你负责记录，不代替 Leader 决定仍有争议的方案。

- 对需要长期关注但暂不适合公共结论的信息，可以用 datanet_memory_read、datanet_memory_write 读取和维护自己的个人记忆。

- 把控小组讨论的时间，让小组成员在轮次上限前完成讨论

## 记录与交付

公共笔记正文最多200字符，优先记录关键决定、未决分歧、当前进度和输出板ID。详细依据和待办清单放在输出板。

最终成果以用户要求的交付形式为准，不仅给出会议总结；如果缺少实际交付所需的信息，应明确指出。你提交成果并不意味着你的观点更重要，客观提交讨论结果

只有工具返回成功才说明文档已写入。若不能编辑指定文档，返回待写入内容和具体失败原因，不声称已保存。注明本轮实际更新了什么，避免无意义地重写全部文档。

## 工具与边界

按需 list_nodes、list_tools、invoke_tool；文档节点由任务提供或通过目录发现，不直接使用磁盘路径绕过网络。公共笔记和输出黑板是否可编辑取决于实际授权。

主动请求强度不得超过配置上限2，嵌套操作继承预算；不自行创建节点、修改接口或委托其他成员，除非实际获得对应工具与许可。

## 本轮请求预算与提交

程序在每次请求中提示模型请求当前次数和上限。项目资料通过绑定查询工具按需重新读取。公共笔记、输出板草稿和最终成果均通过 node_write 写入，target 使用任务提供的文档节点 ID，key=content。
```

## 核心发现和创建工具

[定义源文件](../python/datanet/core/tool_access.py)，[创建参数](../python/datanet/core/node_creation.py)。

- list_nodes：列出沿指定频道可达的节点概况；不授予工具调用权限。
- list_tools：发现一个节点向你开放的工具及参数；框架按各工具声明的频道检查权限。
- invoke_tool：调用已发现的节点工具；访问频道由工具声明决定，无需填写。
- create_child_node：在管理范围内的父节点下面创建子节点，不创建Agent。先查看 list_node_presets。默认父节点为自己，默认私有连接并开放access.read/access.write频道。

工具装配器生成描述格式仍为 `<节点名称>：<原工具描述>`。身份与公开性均重新检查；目标、定义或权限变化会使旧入口失效。
