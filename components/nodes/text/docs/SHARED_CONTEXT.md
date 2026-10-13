# 共享文本

query_text / resident_text 预设均保存 UTF-8 文本，读写连接负责授权，管理归属独立。

查询文本：提供绑定查询工具，正文作为普通历史文档消息按需加载。仍保留时不重复加载，压缩后再次查询可重新加载。

常驻文本：每次模型请求读取当前正文，附加到请求尾部。公共笔记标识为 `[公共笔记：小组ID/notebook](由recorder维护)`。Recorder 用 write_resident_text 维护，写入结果不回显正文。正文不进入历史或压缩摘要。

根节点 project、progress、work 使用查询文本。讨论创建时用 project_nodes 引用多个已有查询文本；未提供时必须填写非空 project，自动生成查询文本。黑板 load_project 首次加载全部项目资料，成员之后按需查询。全部成员直接读取连接同一批资料和公共笔记。

插件提供官方 rc.2 AgentLoop 的请求尾部扩展及对应 invariant。每次 datanet/request-tail 记录当次请求快照用于还原，没有 surfaceOp，不参与 deriveMessages。旧标准文档在检查点恢复时迁移到对应类型。
