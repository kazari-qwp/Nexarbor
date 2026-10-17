# 信息收集器

Agent 节点挂载 `information.collector`，配置 `strength`，默认使用会话获准强度；可选 include_self，默认 false。主机调用 `collect(context)`，不执行模型。

从所属 Agent 沿 access.read 频道遍历，复用核心返回的 path 与 remaining_strength，逐个显式调用节点 get_information；跳数为 len(path)-1。业务或其他无提供器节点自动跳过。结果返回结构化 items，并通过已有 Agent 输入 API 更新独立 tail 源 `information:<actor>`；不需要上下文子节点另连地图。

不注册 Agent 工具。何时收集由响应器配置决定；小世界只在每次 tick 激活时收集，模型请求和移动都不会触发重收集。卸载/关闭清除该 tail 源。
