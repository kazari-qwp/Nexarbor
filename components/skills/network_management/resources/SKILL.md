---
name: network_management
description: 当需要创建、组织或调整节点、Agent、子网络，以及委托任务和恢复工作时使用。
---

# 网络管理

加载本能力包即获得配套工具箱。工具的管理范围、自定义许可与连接权限已经由包配置确定，正常调用不需要再次申请逐项工具授权。

1. 查询datanet_presets和datanet_agent_capabilities，根据任务选择节点和Agent；简单任务不必扩展组织。
2. 通过datanet_create_node/create_network创建结构，以返回的实际ID和连接摘要操作，不猜路径。
3. 需要智能角色时用datanet_create_agent创建Agent节点，自带个人记忆。给现有成员增加下属时inspect/update_prompt，保留旧职责并补充委托与结果回收要求。
4. 用datanet_interfaces管理连接。需要看结构时使用network_structure(depth=2)，最大depth代表全部获准连通拓扑；查看权限不扩大数据或操作权限。
5. 普通Agent用datanet_call_agent异步委托，结果自动回送；依赖结果时用datanet_wait_agent等待。讨论组用datanet_discuss。
6. 依据真实结果更新项目资料，遇到错误先查看状态。恢复讨论仅传group_id可沿用保存任务。框架装配正确性由程序保证，不要求模型试写验证网络。


恢复时先查询 datanet_recovery_status：phase=round_in_progress 只继续未提交成员；phase=finalizing 只继续Recorder收尾，不重建小组或重新讨论。使用返回的 resume 参数续接。遇到 MODEL_OUTPUT_TRUNCATED 或 FINAL_OUTPUT_NOT_CONFIRMED，任务尚未完成；先检查已执行结果再继续，不能把旧成果当作本次成功。

管理范围采用self/children/descendants，对应管理归属而非普通接口可达；私有成员可以正常管理，普通数据访问和委托不会因此穿透私有接口。无需进入特殊管理模式。
