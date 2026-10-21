# 知识归档与版本管理

本项目从四个节点开始：资料管理员、入库与来源目录、原始任务、交付文档。知识库为空，不含旧会话。管理员创建集合时，使用项目内的普通网络模板，为 CSV、SQLite、RAG、Wiki 各集合建立独立数据节点。网络使用 `knowledge` 频道访问资料；创建集合使用单独的 `runtime.template` 频道。

- `modules/context.network/`：按频道广度顺序组装上下文。
- `modules/documents.tasks/`：保留原始任务，保存带版本的交付文档。
- `modules/knowledge.catalog/`：集合目录、入库队列、原始来源、版本索引及跨集合检索。
- `modules/knowledge.collection/`：每个集合自己的读取、查询和修改入口。
- `modules/knowledge.tools/`：资料管理员使用的知识工具。

`workspace/imports/` 附带技术文档、编号目录、首批观测与项目简报；出处见 `workspace/SOURCES.json`。可以先要求管理员建立任务并归档工作区，再追加资料或只读查询。实现保留原文、前导零、原始观测字段与历史版本，支持增量合并、结构化统计、Wiki 来源链接和重启恢复。入库队列支持将原始文件关联到已有记录，或说明不入库的原因。

复制整个目录，在 Nexarbor 中打开项目文件夹，并选择自己的模型连接。项目使用 DeepSeek Flash 配置，不包含 API key、模型权重、运行记录或本机路径。

默认未配置嵌入模型，使用关键词检索。需要语义检索时，在“入库与来源目录”节点的 `knowledge.catalog` 配置中设置 `embedding.model_path` 为自己的本地模型目录，并按需安装向量检索依赖，然后为 RAG/Wiki 集合建立索引。检索返回条目后，可继续读取 Wiki 正文、关联链接及其原始版本；Wiki 初稿仍需要依据来源核查。

网络、模块、文本和后续知识数据均留在项目文件夹内。客户端保存运行状态；Commit 将项目版本交给 Git。资料文件与测试报告是不同的内容，本项目仅附带可使用的初始资料。
