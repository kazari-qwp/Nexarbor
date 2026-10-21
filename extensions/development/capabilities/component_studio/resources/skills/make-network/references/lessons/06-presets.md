# 从需求组装网络

catalog_modules 查职责和参数，edit_network 从默认骨架组装 network.json。成品仅 {network,files}，network.version=8，nodes/signals/delegations 都存在；不要求 root，可以没有管理根或没有节点。files 放人格、常识、地图等文本，相对路径在网络内部。

需要运行时固定模板时，工作副本另有 `runtime.json`，只放 `{"templates":[...]}`。它会进入完整网络的运行时元数据，也会被候选自测加载；不要另写一个没有被成品消费的 templates.json。`copy_current_network` 会同时复制当前模板。声明与测试按需读 nexarbor-basics 的 `references/lessons/16-templates.md`。

通常优先用 edit_network 的短命令从默认骨架与发布装配开始组装，命令表见 make-network 的 references/批量组装.md；不要为了改几条线反复读写整份 network.json。

修改 `runtime.json` 的嵌套模板或 JSON 配置时，可用 `edit_json(path=文件,operations=[...])` 原子提交多项操作。`set` 设置或新增值，`remove` 删除，`copy` 从 `from` 路径复制到 `path`；如 `/templates/0/document/network/nodes/0/name`。数组从 0 计数，`/-` 追加；中间对象必须已存在。失败整批不保存，返回简短回执，仍需 validate。

大网络优先分批调用network_patch，每批提供完整节点对象和需要的files，按node_id合并；不必反复读取或重写所有节点。replace=true用于首次清空空白草稿，之后继续合并。没有管理者时 management_parent_id 为 null；设置管理者时必须引用实际存在的节点，不能为了凑格式创建 root；不要写屏幕坐标等非协议字段。

流程：列角色数据 → 查复用组件 → 分配本地职责 → 配频道和有向边 → 填配置/状态/授权 → validate。不写全局 Python 启动器。

装配 modules:{'模块ID':{config:{},state:{},access:{strength:2,channels:['tools']}}}；从目录复制 defaults 再改。框架递归补 requires。模块工具自动提供，外部工具才放 offered_tools:[{ref,channels}]。

组件携带工具不写node.expose：通常保持expose:[]、toolboxes:[]。expose只登记实际安装的节点工具箱工具，不能把模块操作名send/read等填进去，否则冷加载会拒绝。模块的agent_tools已经是独立的公开声明。

出边在起点 connections.interfaces：{target_node_id:'目标',metadata:{channels:['tools'],threshold:1,multiplier:1,attributes:{}}}。双向道路写两条边。按关系和任务设计频道，例如小镇的道路用 road，当前位置用 location，时间查询用 time；同一关系上的相关业务可共用频道，不必每种操作再加一条。需独立传播的 tick、上下文和内部运行能力仍明确分开，不用无限强度全通边掩盖问题。

频道设计同时是制作规范和验收项：避免全频道找目标，检查重复的多频道表能否合并；完整规则见 `nexarbor-basics` 的 `references/lessons/02-network.md`，验收见 `references/lessons/15-behavior-tests.md`。

也检查服务到依赖的路径，目的地移动模块须访问 NPC 和旧地点。事实只保存一份，经公开操作读取。

工具收集器的 config.channels 决定沿哪些关系找工具和串联收集器，发布装配默认 tools，可配置列表与黑白名单；access.channels 还要包含实际工具操作频道。需要独立检索出边时放在亚节点，通过 execution.tool_sources 显式引用；新样板的工具亚节点借用父链接，按 config.channels 中的 movement 收集工具；准确装配见小镇清单，不把旧版配置当成当前事实。不要把样板的频道名当作所有应用的固定要求。

同层信号接收器会并行执行，并等待全部完成才进入下一层。普通角色可由时间节点分叉后并行，再各自到存档点；只有业务本身有先后依赖时才用拓扑层次表达。及时回应可用有界 post，不用把角色排成队来规避并发；模块跨节点访问仍是默认异步。模型等待期间不要持独占锁；锁等待前序回调完全退出，不保证两个相互等待的整轮模型活动能同时写对方。

Agent execution 设 executor:'harness'、strength、channels、prepare、max_steps、timeout_seconds。人格常识用输入组件 system_prompt，现况用 tail，临时事件用唯一 ID inputs。模型思考前不锁全网。

上下文准备的执行配置示例（实际工具的操作频道另外加入 channels，独立工具来源用 tool_sources 引用）：
```json
{"executor":"harness","strength":2,"channels":["self","context.assembler"],"prepare":[{"node":"context-node","module":"context.assembler","operation":"assemble","arguments":{},"channels":["context.assembler"]}],"max_steps":16,"timeout_seconds":180}
```
prepare必须是数组，不能写true或单个对象，可引用本地归属树中的模块或通过明确授权连线可达的模块；上下文来源读 nexarbor-basics 的 references/lessons/09-context.md；执行器不支持tool_provider字段。tools.collector的access.channels也必须包含希望收集的实际操作频道（例如self/chat/knowledge），只有tools只能看见以tools作为操作频道的工具。执行器首次运行自动发现自己的工具提供模块。后续准备先比较依赖变化；可缓存的工具列表在相关拓扑、装配、工具声明或提供器状态变化时重新收集，不逐请求无条件全量扫描。不可缓存的动态提供器仍按需刷新；移动后失效的旧工具不能继续执行。

Schema中的default是说明，不能假设JSON Schema会自动填入配置；signals:{config:'signal_channels'}的组件必须显式填写signal_channels，否则没有接收频道。使用catalog返回的mount_defaults，再按需求改。

先小闭环再扩数量。知识库可先做归档、检索、引用和恢复；同类地点可通过参数复用组件，不同业务应保留清楚的职责。小镇的五条设计建议与完整案例入口，按需用 `read_skill_reference(skill="nexarbor-basics", file="references/lessons/13-town-evolution.md")` 读取。

可调人数的零件预设在 `network` 中声明 `repeat_unit_count`（1–100）和 `repeat_unit`（一个可重复单元所含节点 ID）。共享节点不列入单元；框架拖入时复制单元、重映射内部引用、连接与独立数据路径。没有此参数用缺省或 null；它不负责运行中招募成员，运行时实例化另用固定模板。

候选自测和局部管理员提交也按该数量展开；交付保留原型与数量声明。共享节点里的固定成员 ID 数组不会自动增长，成员集合宜沿专用频道从真实拓扑读取。需要两种独立数量时，交付两个可重复零件，分别验证不同数量的真实成员，而非让用户手工复制节点或改数组。

同一完整网络可附带多个独立零件：用 `edit_network(path="presets/某零件.json", commands=...)` 制作各自的 `{network,files}` 文档，再写 `outputs.json`，格式为 `{"outputs":[{"name":"零件名称","file":"presets/某零件.json","description":"用途"}]}`。`validate` 检查全部产物；测试中用 `NetworkHarness(network_file="presets/某零件.json")` 取得该产物真实展开后的独立夹具。通过后一起发布到零件预设栏，各自有独立的数量输入；主网络仍是 network.json。附加零件不携带主网络的全局 runtime 模板。

没有 request_component 只能用已发布组件。允许委托则提交最小通用需求，component_status 确认验证发布后再引用，不能猜 ID 或把未验证代码塞进网络。

已有公开组件需要改进时，用 `request_component(module="已安装的精确ID", requirement="修订需求")` 建立独立修订；不会覆盖原版本。已有委托则继续用 task，不从空白重复实现。修订后的新 ID 以回执为准。
