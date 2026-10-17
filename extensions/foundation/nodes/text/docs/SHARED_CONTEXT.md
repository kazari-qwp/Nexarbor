# 共享文本

`query_text` 是普通 UTF-8 文本加按需查询呈现。查询工具将正文作为历史文档加载；原生标记仍在时不重复加载，压缩后可重新查询。读取使用 access.read，写入使用 access.write；管理关系单独授权。

常驻内容、系统提示词和请求尾部由独立上下文装配器处理，不再提供 resident_text 节点或 write_resident_text 工具。根节点的 project、progress、work 仍使用查询文本。

讨论小组的公共笔记是有200字符上限的普通文本节点，只有 Recorder 获得写入频道，使用 node_write、target=笔记节点ID、key=content。讨论组件把轮初快照送入各成员请求尾部；当前轮内修改下一轮生效，避免并行成员依据不同笔记。项目和输出板是按需查询文本，详细内容不自动重复注入。

四类输入及原生标记说明见 docs/CONTEXT_ASSEMBLY.md。当前存档格式不读取旧网络。
