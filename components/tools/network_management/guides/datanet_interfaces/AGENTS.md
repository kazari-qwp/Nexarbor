# 管理节点接口
list 查看接口，add 新增连接，update 修改现有连接，remove 删除连接。操作节点由 arguments.node_id 指定；省略按所属节点处理。读写方向分别设置。
add/update/remove 必须指定 target_node_id；即使给 interface_index，也要填目标 ID，框架核对它们一致。新增属性用 interface，修改属性用 changes；可设置 visibility 为 public 或 private。访问传播的底层参数由框架处理。
接口属于来源节点。private 用于内部访问边界，public 允许符合路径条件的外部访问；两者不改变目标 Agent 的私有工具权限。管理操作按管理范围授权，数据和任务访问仍检查普通路径。
暴露业务工具要在节点装配时选择 expose，并建立适当接口；仅添加接口不把工具变成公开业务工具。禁止尝试将agent的工具和skill进行暴露，如有需要，直接把工具加载到你想加载的地方。
