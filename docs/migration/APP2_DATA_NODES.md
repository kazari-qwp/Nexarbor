# 应用二数据节点迁移清单

依据用户要求，全部数据节点直接或间接继承 `domain.core.DataNode`。Value、CSV、SQLite 已完成节点级迁移；LlamaIndex、CollectionNode 仍待迁移。完整应用数据模块、模板与前端链路尚未接入。

| 旧类型 | 原源码 | 新结构要求 |
| --- | --- | --- |
| ValueNode | extensions/storage/capabilities/value/python/datanet/components/nodes/value_node/value_node.py | ValueNode(DataNode)，按 D007 改为 JSON 文件存储，访问由 ValueDataer 实现 |
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

Value/CSV/SQLite 已迁移，CSV/SQLite 数据方法在仅替换结果类型名后与原方法 AST 一致。158 项 Python 测试通过，含 7 项 Value 与 10 项 CSV/SQLite 文件、查询、写入、复制及 WAL 验证。其他具体方法、存储结构及旧断言继续逐文件审查后迁移。遇到 DataNode/Dataer/Saver 协议不兼容，按用户要求先讨论，不能私自改 core 或编造占位实现。

## 当前具体兼容点：B005

B005 已由 D007 解除：用户明确允许 ValueNode 改为文件存储。真实 JSON 文件、ValueDataer、ValueSaver 及 7 项行为测试已实现；原应用内联值配置的实际资源转换尚待接入。CSV/SQLite 继续沿用原存储引擎，不用其他实现替代。

## 已落地路径

- projects/knowledge_archive/nodes/value.py：ValueNode/Dataer/Saver，真实 JSON 文件。
- projects/knowledge_archive/nodes/csv.py：CsvNode/CsvDataer，pandas 规则保持。
- projects/knowledge_archive/nodes/sqlite.py：SqliteNode/SqliteDataer，一致数据库快照包含 WAL。
- domain/data_result.py、data_request.py、data_write.py、record_dataer.py：原结构化访问值对象与查询分派，均在 core 外。
- app/network_saver.py：保留业务节点 parameters，应用自行登记节点类型；不把应用类型内置进平台。
