# 第三方能力复用

| 能力组件 | 上游 | 接入方式 |
|---|---|---|
| CSV | [pandas](https://pandas.pydata.org/) | 复用现有 CsvNode 与表格读写 |
| SQLite | [SQLite](https://www.sqlite.org/) / Python sqlite3 | 复用现有 SqliteNode 与参数化数据库操作 |
| 文档索引 | [LlamaIndex](https://github.com/run-llama/llama_index) | 复用加载、分块、增量文档刷新、向量检索和索引持久化 |
| 本地嵌入 | [HuggingFace LlamaIndex 适配](https://developers.llamaindex.ai/python/framework-api-reference/embeddings/huggingface/) | 应用统一配置模型，节点共享实例 |
| Agent Wiki | [llm-wiki](https://github.com/jackwener/llm-wiki) | 固定源码、原版维护指南及 BM25/图分析算法；薄适配接入现有知识记录，不另建模型循环 |
| Markdown Wiki | [MkDocs](https://www.mkdocs.org/) | 调用上游渲染、导航和搜索索引构建 |
| Git 工作区 | [Git](https://git-scm.com/) | 独立共享组件包装 worktree、提交与串行整合 |
| Agent 执行 | DeepSeek Harness / 可选执行器 | 通过核心执行器契约和通用适配层接入 |

扩展只承担必要的节点、权限、数据引用和工具接口适配。组件 manifest 记录上游信息；Python 可选依赖在对应 requirements.txt 中。没有向核心复制第三方项目实现。

本地验证使用 LlamaIndex Core 0.14.25、HuggingFace embedding 0.8.0、MkDocs 1.6.1 和 BAAI/bge-small-zh-v1.5 测试模型。模型留在忽略的 build/models 目录，不纳入源码或发布包。

llm-wiki 固定提交 `cd5466678341885fa29ca9e27fa9604c2e9c11c5`（上游 package 0.6.0）。未修改的源码、三份操作指南、Apache-2.0 LICENSE 与逐文件 SHA256 清单位于 `extensions/storage/capabilities/llm_wiki`。Node.js 22.18+ 执行其 TypeScript 算法；PyYAML 解析页面 frontmatter。来源版本与权限仍由知识存储组件处理，语义矛盾由 Agent 核查。
