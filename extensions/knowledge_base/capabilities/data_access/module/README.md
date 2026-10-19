# 本地数据读写

装配在 JSON、CSV、SQLite 或本地知识集合节点上。模块只用 ctx.schema/read/write 操作本节点；跨节点调用者必须顺着当前网络的 data 或 knowledge 频道到达。

基础操作是 inspect、read(key)、query(request)、write(key,value,mode)。JSON 节点固定使用 key=value。CSV/SQLite 使用配置中的主键。知识集合可另装配依赖此模块的 `data.knowledge`，由它提供 put、history、remove、restore、index、search、fetch；put 和修改操作可带 expected_version，避免覆盖并发更新。

RAG 和 Wiki 的语义检索需要配置本地嵌入模型；未配置时仍可存储、读取、条件查询和维护版本，语义请求明确失败，不伪装成关键词结果。模块从不接收模型路径、磁盘路径或任意 SQL。
