# 官方扩展网络访问模块

这是需要额外网络视角时才装配的可选组件，默认不启用。普通组件始终通过自己的强度和频道访问网络；该模块以显式装配授权提供例外，不提供 Backend 或任意 RPC。

详见 [局部模块核心](../../../../docs/LOCAL_MODULES.md)。模块 ID 为 `network.gateway`，组件 ID 为 `capabilities/network_gateway`。config.channels 默认为 `["network.extended"]`。

operations（不会自动成为 Agent 工具）：

- `nodes()`：允许目标的元数据列表。
- `metadata(target)`：允许目标的元数据。
- `incoming(target)`：目标入边；来源节点也须被授权。
- `interfaces(target)`：目标出边；另一端也须被授权。
- `connect(source,target,channels,threshold=0,multiplier=1)`：两端授权后新增或合并连接，并提交核心存档。
- `disconnect(source,target,channels)`：只删除这些频道，保留连接上的其他频道，并提交核心存档。

装配项 `access.extension` 必须列出 operations 和 targets；缺省没有权限。targets 中的 `"*"` 是显式全局授权。普通组件调用前仍需有到本网关的正确频道与足够强度。模块不接收信号，也不申请模型会话。没有公开持久业务状态。
