# 从需求组装网络

catalog_modules 查职责和参数，node_template 取合法单节点骨架，组合 network.json。成品仅 {network,files}，network.version=8，nodes/signals/delegations 都存在，保留 root。files 放人格、常识、地图等文本，相对路径在网络内部。

大网络优先分批调用network_patch，每批提供完整节点对象和需要的files，按node_id合并；不必反复读取或重写所有节点。replace=true用于首次清空空白草稿，之后继续合并。root的management_parent_id必须为null，其他节点通常为root；不要写屏幕坐标等非协议字段。

流程：列角色数据 → 查复用组件 → 分配本地职责 → 配频道和有向边 → 填配置/状态/授权 → validate。不写全局 Python 启动器。

装配 modules:{'模块ID':{config:{},state:{},access:{strength:2,channels:['tools']}}}；从目录复制 defaults 再改。框架递归补 requires。模块工具自动提供，外部工具才放 offered_tools:[{ref,channels}]。

出边在起点 connections.interfaces：{target_node_id:'目标',metadata:{channels:['tools'],threshold:1,multiplier:1,attributes:{}}}。双向道路写两条边。隔离 tick、移动、当地业务、资料、内部运行频道，不用无限强度全通边掩盖问题。

也检查服务到依赖的路径，目的地移动模块须访问 NPC 和旧地点。事实只保存一份，经公开操作读取。

Agent execution 设 executor:'harness'、strength、channels、prepare、max_steps、timeout_seconds。人格常识用输入组件 system_prompt，现况用 tail，临时事件用唯一 ID inputs。模型思考前不锁全网。

先小闭环再扩数量。第一应用只固定讨论组和去中心化组，不制作全网根管理者；知识库先归档、检索、引用和恢复；小镇通过通用生产/交易/转移/时钟参数区分场所。

没有 request_component 只能用已发布组件。允许委托则提交最小通用需求，component_status 确认验证发布后再引用，不能猜 ID 或把未验证代码塞进网络。
