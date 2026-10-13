# 创建节点
选择数据节点或无数据组织节点；需要智能成员时创建后再挂载 Agent。
node_spec 使用预设时填写 preset，可补充 name、description。query_text 是按需查询的文本，读取连接建立后自动提供绑定查询工具；resident_text 是常驻文本，成为 Agent 的直接读取目标后，最新正文自动放在每次请求尾部。有写入连接的 Agent 可用 write_resident_text 维护常驻文本。自定义时填写 type、parameters，可选 name、data_kind、description、toolboxes、expose；type及可用参数通过 datanet_presets 查询。省略 parameters 时按空对象处理。自定义只使用框架支持的类型，不运行任意实现代码。
parent_node_id 省略时为所属节点，指定其他父节点需在管理范围内。child_id 为该父节点下未使用的名称。创建结果返回实际节点 ID 及接口装配信息。
节点的 toolboxes 装配业务工具，expose 选择向其他节点公开的工具名；省略时不公开业务工具。数据读写仍受接口控制，Agent 的私有工具箱另行装配。
文件资源留在工作区内。无数据 node 不存报告；文本、表格等数据按类型选择。
