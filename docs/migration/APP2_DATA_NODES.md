# 应用二数据节点迁移清单

依据用户要求，全部数据节点直接或间接继承 `domain.core.DataNode`。当前仅完成原文件定位与继承约束记录，尚未声称节点迁移完成。

| 旧类型 | 原源码 | 新结构要求 |
| --- | --- | --- |
| ValueNode | extensions/storage/capabilities/value/python/datanet/components/nodes/value_node/value_node.py | ValueNode(DataNode)，JSON 值的语义保持，访问由 ValueDataer 实现 |
| CsvNode | extensions/storage/capabilities/csv/python/datanet/components/nodes/csv_node/csv_node.py | CsvNode(DataNode)，保留主键、字段类型、条件查询和更新规则 |
| SqliteNode | extensions/storage/capabilities/sqlite/python/datanet/components/nodes/sqlite_node/sqlite_node.py | SqliteNode(DataNode)，保留表、键列、查询、事务与原资源复制恢复规则 |
| LlamaIndexNode | extensions/storage/capabilities/llamaindex/python/datanet/components/nodes/llamaindex_node/llamaindex_node.py | LlamaIndexNode(DataNode)，保留导入、分块、嵌入、索引、来源和增量更新行为 |
| CollectionNode | extensions/knowledge_base/capabilities/knowledge_store/python/datanet/knowledge/node.py | CollectionNode(DataNode)，保留 csv/sqlite/rag/wiki 集合后端及文档/修订/索引归属 |

## 迁移边界

- 原类中读取、写入、Schema/查询的具体数据行为迁到对应 Dataer；保存、复制、资源路径和恢复按对应 Saver/应用持久化编排实现。
- 不把所有数据转成 Markdown，不把语义检索替换成关键词匹配，不改字段或权限语义来消除失败。
- 业务节点及其配套模块随资料库应用项目携带，不增加第四种平台内置业务模块。
- 共用的外部存储/解析依赖在 adapt 中明确归属；节点最终仍继承新 DataNode。
- 多文件、数据库、索引数据的保存/回滚须覆盖原资源集合，不能只复制一个路径就报告恢复成功。

## 必须复用的验证来源

- tests/test_data_nodes.py -> scripts/verify_data_nodes.py
- tests/test_knowledge_base.py、test_knowledge_navigation.py、test_knowledge_semantic.py
- 原资料库应用的归档、检索、来源引用、只读权限、复制与保存重开断言。
- 新增结构验收：所有装配出来的资料节点均为新 DataNode 子类，实际读取来自其 Dataer。

## 状态

类型与文件已定位；具体方法、存储结构及旧断言需逐文件审查后迁移。遇到 DataNode/Dataer/Saver 协议不兼容，按用户要求先讨论，不能私自改 core 或编造占位实现。

## 当前具体兼容点：B005

ValueNode 只持有内存 JSON 值，原 codec 直接写 parameters.value；通用 Saver 的抽象 path 要求与它冲突。已停止该节点的实现并记录 B005，等待讨论是否将文件源路径下移到文件保存器。不能通过虚构文件路径、强制创建 backing file 或不继承 DataNode 来绕过。
