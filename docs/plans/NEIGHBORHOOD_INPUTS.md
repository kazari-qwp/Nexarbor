# Tick 邻域装配实施计划

用户已确认：NPC 上挂信息收集器与工具装配器；信号响应器依次执行收集、装配、Agent 循环。只在 tick 开始刷新，首次、恢复与新生 NPC 的第一次活动使用相同路径，移动后不刷新。

三个通用组件：information.provider 用配置投影元数据与路径跳数标签；information.collector 从自身读权限显式调用可达节点 get_information；tools.assembly 从自身读/写权限装配直接调用入口。提供器不是 Agent 工具，业务节点不挂载即无信息。现有上下文装配继续负责资料，收集结果通过已有 tail 输入源提供。

保留访问强度2、实时权限检查、同层并行与移动正常结束。工具别名绑定目标与定义，不经过模型发现调用；NPC 不再获得 node_list/node_tools/node_invoke，只保留 node_read 读取知识正文。先实现、补最小生命周期与权限测试，再用 Harness 原生循环 + Mock 验证，无全世界真实模型运行。

## 完成记录

已新增 information.provider、information.collector、tools.assembly 三个通用节点模块和对应组件。NPC 与儿童模板均配置三步响应，地址/NPC 配置选择信息字段。核心只增加 get_information 委托入口；适配层复用原生动态工具权限与正常 conclude 机制。65项 Python 测试、原生 JSONL + Mock 直接业务/单次移动闭环通过，未运行全世界真实模型。文案审阅见 docs/applications/npc_world/NODE_MODULE_REVIEW.md。
