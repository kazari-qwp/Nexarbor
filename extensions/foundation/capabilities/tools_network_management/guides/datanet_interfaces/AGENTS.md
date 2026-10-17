# 管理节点接口
list 查看接口，add 新增连接，update 修改现有连接，remove 删除连接。操作节点由 arguments.node_id 指定；省略按所属节点处理。连接统一为有向接口，通过 metadata.channels 授予能力频道。
add/update/remove 指定 target_node_id；即使给 interface_index，也要填目标 ID。新增属性用 interface，修改属性用 changes；可设置 visibility 为 public 或 private。interface 与 changes 都使用 {"metadata":{...}}。标准数据读取用 access.read，写入用 access.write；空频道不授予远端访问。目标有多条连接时用 interface_index 指定其中一条。工具调用自动采用目标工具声明的频道，不需要填写 direction。
拆除造成节点与根断联时，链接暂时保留，返回 confirmation_id。继续调用 remove，arguments 填 confirmation_id 和 choice：1取消；2保存结构并卸载；3分解，保留 Agent 会话和个人记忆进入复用池。已有任务结束后执行卸载。保存结构后可用原入口 ID 重新 add 接回。
拆下来的网络各自保存到独立文件夹。datanet_presets 返回 saved_networks，提供保存 ID、入口 ID 和目录；填 archived_network_id 查看清单。状态 saved 的网络可按 entry_node_id 接回；状态 decomposed 的 Agent 在创建时按配置匹配复用。
接口属于来源节点。private 用于内部访问边界，public 允许符合路径条件的外部访问；两者不改变目标 Agent 的私有工具权限。管理操作按管理范围授权，数据和任务访问仍检查普通路径。
暴露业务工具要在节点装配时选择 expose，并建立适当接口；仅添加接口不把工具变成公开业务工具。禁止尝试将agent的工具和skill进行暴露，如有需要，直接把工具加载到你想加载的地方。
