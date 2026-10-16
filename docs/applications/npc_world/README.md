# NPC 小世界

第三个应用以普通节点、Agent 节点、文本节点与脉冲节点装配小镇，使用 DeepSeek Harness 前端。没有 Start 节点、世界构建器、统一业务结算或轮次收尾节点。

首次打开由通用 `disk_network` 组件读取 `small_town/network.json` 与 `initialFiles` 引用的只读资料，调用核心加载机制；以后恢复已有存档。该文件就是初始地图、连接、模块参数和状态，不是在启动时执行的小镇搭建程序。首次打开装配六居民会话，不运行模型。

## 地图与时间

每个地点包含地址和业务两个普通 Node。地址装配 `world.address`，仅提供移动；业务节点显式装配需要的服务模块。道路为公有双向边，居民与当前地址双向连接，业务访问强度2、节点散度−1、边门槛1。因此可访问本地业务、同地居民和邻居入口，不能访问邻居业务。

信号网络为 `脉冲 → 时间文本 → 居民 → 存档点 → 脉冲`。`world.tick` 与道路的业务访问分开。核心广度优先按层等待；时间文本的 `clock.text` 模块在新信号到来时推进五时刻时钟。`agent.signal` 通过现有信号响应器依次收集信息、装配工具、执行原生 Agent 循环（执行前复用现有上下文装配），正常结束就记录完成并继续传播，无提交/就绪工具。

每次操作只发一轮。居民默认最多8次请求、90秒，整个操作最多180秒。失败分支不继续传播，其他居民继续；已经成功的业务不会因 Agent 后续失败被撤销。中断脉冲保留进度，需要核对后恢复，不能盲目重放。

存档点是普通节点装配通用 `checkpoint.counter` 模块。同一信号多路汇入只计一次，每5次到达显式保存核心全量快照，并持久化全量恢复点请求。适配层等所有工具结果落盘后，关联所有 Agent 的原生日志位置，发布全量一致恢复点；期间增量保存继续工作。计数器随网络一起恢复，不承担业务结算。

## 工具立即生效

每时刻最多成功执行一个主要行动，交谈另外最多三次。移动、修理、交易、休息、采集和赠送在工具调用时立即生效。失败时恢复本次操作涉及的模块状态与连接，不扣行动额度。核心事务锁串行保护具体写操作；居民推理和执行在同层并行，资源争用按实际调用次序处理。移动成功后通过原生工具结束轮次机制正常结束当前居民活动，不再请求模型；移动失败允许纠正。同一批工具调用中的后续业务或交谈也不能绕过限制。下个时刻才能在新地点继续活动。

结婚与家庭登记将双方同意保存到对应业务节点，第二份同一时刻的有效同意到达后立即办理。孕期10时刻，到期在医院调用出生工具创建独立儿童 Agent 和上下文节点、私人记忆，登记父母及住所；下一次脉冲才加入。

自己的居民楼才允许休息。住所名单属于 `world.household.state.residents`；修理材料属于 `world.repair.state.materials`。元数据扩展器提供实时只读映射，不另存副本。性别、职业、目标、资金、位置等属于居民模块状态，核心 AgentNode 没有 NPC 字段。

## 功能拆分

| 原功能 | 当前模块/数据 | 装配位置 |
|---|---|---|
| 启动中搭建小镇 | 磁盘初始网络 + 通用 disk_network | 宿主加载入口；无 Start |
| WorldNode.place/kind 自动选业务 | 普通 Node + 显式 modules | 每个地址/业务节点 |
| 世界统一状态字典 | 各模块 config/state | 各自所属节点 |
| 移动及在场接口 | world.address | 地址 |
| 身份、财产、交流、赠送 | world.resident | 居民 Agent |
| 住户登记与休息 | world.household | 居民楼业务 |
| 木材/矿石采集 | world.gather（参数区分资源） | 树林/矿坑业务 |
| 商店库存与交易 | world.trade | 商店业务 |
| 店内材料与工具修理 | world.repair | 铁匠铺业务 |
| 饮料与体力恢复 | world.refreshment | 酒馆业务 |
| 服务与库存查询 | world.information | 业务节点 |
| 双方同意与结婚 | world.marriage | 民政局业务 |
| 家庭同意、孕期记录 | world.family | 居民楼业务 |
| 生产、新儿童节点 | world.birth + 儿童声明模板 | 医院业务 |
| 条件知识的读取权限 | world.knowledge | 居民 Agent |
| 上下文源列表及装配绑定 | context.sources，复用 context_assembly | 上下文 Node |
| 模型会话创建/恢复 | agent.session，复用 agent_runtime | Agent |
| 响应脉冲、限额、完成/失败记录 | agent.signal，复用 signal_response/原生循环 | Agent |
| 时钟与时间文本更新 | clock.text | 时间文本 |
| 观察与有限推进 | scene.operator | 操作入口 Agent |
| 统一业务结算、轮次收尾 | 删除；业务工具当场完成，层屏障负责等待 | 无 |
| 每5轮信号显式全量存档 | checkpoint.counter | 存档点普通 Node |
| 保存网络与业务状态 | 核心增量日志/全量快照 | 核心持久化 |

`scene_support` 仅提供调用者验证、一次业务操作的回滚、节点引用查询和元数据投影等共享辅助函数，没有构建器或按地点分派业务的大控制器。`scene.operator` 是装配在入口节点的观察/运行模块，不负责执行场所业务。业务类按模块本身定义，开启一个能力组件并不会让所有节点自动获得它。

## 运行与验证

入口导出 `Nexarbor/npc-world`，适配代码位于 `extensions/npc_world/capabilities/scene_operator/entry.js`。

`world_observe` 只观察，`world_run_npc(target)` 只运行指定居民一个时刻。测试配置 `worldAllowFullRun:false` 禁止完整运行。没有启动全世界真实 Agent 付费测试。

当前最小化测试见 [VALIDATION.md](VALIDATION.md)，Agent 文案原文见 [NODE_MODULE_REVIEW.md](NODE_MODULE_REVIEW.md)，通用装配接口见 [NODE_MODULES.md](../../NODE_MODULES.md)。旧自定义场所/居民节点、旧 world_* 初始化/结算 RPC 已删除，没有保留兼容入口；旧存档需另行转换，当前未实现转换器。

核心增量日志已纳入所有模块状态和文本，并由Harness适配层关联原生日志位置。支持按一致恢复点创建核心与会话的新分支，原分支保留；见 [持久化说明](../../CORE_PERSISTENCE.md)。不回滚外部副作用，不续接半截推理。

## 每时刻的自动邻域装配

NPC 的三步响应为 collect_information → assemble_tools → run_agent。同层 NPC 的三步管线并行执行，仍只在层尾统一等待；模块中的短暂图读取/写入受事务锁保护，不持锁等待模型。

信息提供器是通用元数据投影：NPC 配置姓名/性别，地址配置名称和 1跳本地/2跳相邻标签，业务节点不挂载。收集器从 NPC 自身读权限出发，显式调用可达节点 get_information，结果走独立尾部输入源。上下文子节点不需要连接地图。

工具装配器从 NPC 自身强度2的读写权限生成绑定目标的直接工具。描述含地点或人物名称，NPC 可直接移动、使用本地业务或交谈；每次执行仍检查当前权限，离开的人和旧地点入口不能继续使用。

首次活动、恢复后的首次活动和新生儿童的首次活动走同一流程，无需初始移动。只在 tick 开始刷新；移动后当前 tick 正常结束，下一 tick 才重收集/装配。三个通用组件分别位于 foundation 的 information_provider、information_collector、tool_assembly。核心仅增加默认无返回的 get_information 扩展入口，没有 NPC 或地图特判。

NPC 工具箱已移除 node_list/node_tools/node_invoke；移动、业务和交谈只使用装配后的直接入口。world_look、world_messages、node_read 和私人记忆工具保留，知识正文与交谈仍可按需读取。其他应用的网络访问工具不受影响。
