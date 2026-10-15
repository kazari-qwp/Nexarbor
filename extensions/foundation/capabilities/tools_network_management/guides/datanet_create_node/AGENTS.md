# 创建节点

选择数据节点、无数据组织节点或 Agent 节点。

node_spec 使用预设时填写 preset，可补充 name、description。query_text 是按需查询的文本，读取连接建立后自动提供绑定查询工具；resident_text 是常驻文本，成为 Agent 的直接读取目标后，最新正文自动放在每次请求尾部。有写入连接的 Agent 可用 write_resident_text 维护常驻文本。自定义时填写 type、parameters，可选 name、data_kind、description、toolboxes、expose；type 及可用参数通过 datanet_presets 查询。省略 parameters 时按空对象处理。自定义只使用框架支持的类型，不运行任意实现代码。

parent_node_id 省略时为所属节点，指定其他父节点需在管理范围内。child_id 为该父节点下未使用的名称。创建结果返回实际节点 ID 及接口装配信息。

节点的 toolboxes 装配业务工具，expose 选择向其他节点暴露的工具名，若一个工具被暴露，指向该节点的接口将可能访问到此工具；省略时不公开业务工具。数据读写仍受接口控制，Agent 节点的私有工具箱另行装配。预设会默认装配一些工具，无预设默认无工具。

文件资源留在工作区内。无数据 node 不存报告；文本、表格等数据按类型选择。
