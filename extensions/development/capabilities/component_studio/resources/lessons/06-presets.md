# 从需求组装网络

catalog_modules 查职责和参数，node_template 取合法单节点骨架，组合 network.json。成品仅 {network,files}，network.version=8，nodes/signals/delegations 都存在；不要求 root，可以没有管理根或没有节点。files 放人格、常识、地图等文本，相对路径在网络内部。

大网络优先分批调用network_patch，每批提供完整节点对象和需要的files，按node_id合并；不必反复读取或重写所有节点。replace=true用于首次清空空白草稿，之后继续合并。没有管理者时 management_parent_id 为 null；设置管理者时必须引用实际存在的节点，不能为了凑格式创建 root；不要写屏幕坐标等非协议字段。

流程：列角色数据 → 查复用组件 → 分配本地职责 → 配频道和有向边 → 填配置/状态/授权 → validate。不写全局 Python 启动器。

装配 modules:{'模块ID':{config:{},state:{},access:{strength:2,channels:['tools']}}}；从目录复制 defaults 再改。框架递归补 requires。模块工具自动提供，外部工具才放 offered_tools:[{ref,channels}]。

组件携带工具不写node.expose：通常保持expose:[]、toolboxes:[]。expose只登记实际安装的节点工具箱工具，不能把模块操作名send/read等填进去，否则冷加载会拒绝。模块的agent_tools已经是独立的公开声明。

出边在起点 connections.interfaces：{target_node_id:'目标',metadata:{channels:['tools'],threshold:1,multiplier:1,attributes:{}}}。双向道路写两条边。隔离 tick、移动、当地业务、资料、内部运行频道，不用无限强度全通边掩盖问题。

也检查服务到依赖的路径，目的地移动模块须访问 NPC 和旧地点。事实只保存一份，经公开操作读取。

角色自己装工具收集器时，通常只让它从本节点被调用：位置/道路边传movement、业务边传service/chat/knowledge，不在这些边上传tools，自己的收集器仍有tools操作频道，且access包含所需业务频道。这样能取得周围真实工具，又不会互相转调其他角色的收集器。只有明确设计的工具中继链才让tools贯通；框架不替你修理循环中继。

同层信号接收器会并行执行，并等待全部完成才进入下一层。需要互相读写的角色若要按先后处理消息，可把tick连接写成clock→角色1→角色2→汇合→save→pulse；这只是网络顺序，模块跨节点访问仍是默认异步。模型等待期间不要持独占锁；锁等待前序回调完全退出，不保证两个相互等待的整轮模型活动能同时写对方。

Agent execution 设 executor:'harness'、strength、channels、prepare、max_steps、timeout_seconds。人格常识用输入组件 system_prompt，现况用 tail，临时事件用唯一 ID inputs。模型思考前不锁全网。

可直接复制的执行配置：
```json
{"executor":"harness","strength":2,"channels":["tools","self","chat","knowledge"],"prepare":[{"module":"agents.context","operation":"prepare","arguments":{}}],"max_steps":16,"timeout_seconds":180}
```
prepare必须是数组，不能写true或单个对象，只能调用本节点已装模块；不支持tool_provider字段。tools.collector的access.channels也必须包含希望收集的实际操作频道（例如self/chat/knowledge），只有tools只能看见以tools作为操作频道的工具。执行器首次运行自动访问自己的工具提供模块，后续每次请求刷新，移动后不能复用已经失效的旧工具。

Schema中的default是说明，不能假设JSON Schema会自动填入配置；signals:{config:'signal_channels'}的组件必须显式填写signal_channels，否则没有接收频道。使用catalog返回的mount_defaults，再按需求改。

先小闭环再扩数量。第一应用只固定讨论组和去中心化组，不制作全网根管理者；知识库先归档、检索、引用和恢复；小镇通过通用生产/交易/转移/时钟参数区分场所。

没有 request_component 只能用已发布组件。允许委托则提交最小通用需求，component_status 确认验证发布后再引用，不能猜 ID 或把未验证代码塞进网络。
