# knowledge.collection

一个集合一个独立节点。配置明确集合ID和csv/sqlite/rag/wiki类型；负责该集合的检索、读取、写入、版本、查询和Wiki操作。通过knowledge频道访问历史目录服务，保持历史CollectionNode的职责，不靠固定名称搜索全网络。每次回执和读取引用返回本集合的真实node_id。

操作与参数见module.json，业务实现见module.py。
