# 应用二：知识库与应用记忆

知识库采用固定入口与数据区，归档和检索两个 Agent 按需运行。Agent 可以选择存储方式、命名集合、设计字段和分类；创建工具自动处理路径、节点和连接。普通读写、筛选及检索无需生成模型。

## 存储与复用

| 数据 | 实现 | 用途 |
|---|---|---|
| CSV | 复用 CsvNode / pandas | 简单、少更新、需要整表交换的数据 |
| 数据库 | 复用 SqliteNode / SQLite | 精确筛选、更新、索引、排序、分组统计 |
| RAG | 复用 LlamaIndex / HuggingFace Embedding | 原始文档、增量索引和混合检索 |
| Wiki | Markdown + 复用 MkDocs | Agent 整理的知识页面、链接与可浏览搜索站点 |

页面归档、引用和应用权限属于扩展适配逻辑。MkDocs 提供页面渲染、导航和站内搜索，不负责 Agent 知识判断。第三方实现通过能力组件引用，没有复制进核心。

## 启用

本应用的 Harness 插件入口为 `datanet-harness/knowledge-base`，也可向通用适配器提供以下配置：

```json
{
  "extensionRoot": "E:/DataNet-模块化成品/extensions/knowledge_base",
  "rootNetwork": "knowledge_base",
  "rootToolboxes": ["knowledge_base"],
  "workspace": "E:/我的知识工作区"
}
```

代码复用当前 Harness 适配器，未创建另一套 Agent 循环。可选执行器仍遵循核心执行器契约。

安装可选依赖：

```powershell
python -m pip install -r extensions/storage/capabilities/llamaindex/requirements.txt
python -m pip install -r extensions/storage/capabilities/markdown_wiki/requirements.txt
```

语义检索在应用级配置一次本地模型，各文档节点自动共用：

```json
{
  "knowledgeEmbedding": {
    "model_path": "E:/models/bge-small-zh-v1.5",
    "device": "cpu",
    "max_length": 512,
    "batch_size": 8
  }
}
```

没有嵌入配置时，原文保存与关键词检索仍可使用；语义请求明确报告配置缺失，不伪装成语义成功。模型不随组件源码分发。

## 使用

- `kb_ingest`：提交内容或工作区内的 CSV、JSON、TXT、Markdown 文件，归档 Agent 选择已有或新集合。同样结构和用途的后续输入可直接复用已登记路由。
- `kb_catalog`：按需查集合用途、存储形式和字段。
- `kb_search`：关键词、结构化筛选或语义检索，返回短片段与读取引用。
- `kb_fetch`：通过稳定 ID 取得完整内容、版本、来源、导入原件路径及更新提示。
- `kb_query`：SQLite 集合的筛选、排序及 count/sum/avg/min/max 分组统计；不接受模型生成的任意 SQL。
- `kb_ask`：由只读检索 Agent 综合问题。
- `kb_update`、`kb_delete`：带 expected_version 修改当前记录，保留可追溯版本。
- `kb_export`：完整 JSON/CSV 导出；Wiki 可用 format=wiki 生成 MkDocs 站点与搜索索引。

归档 Agent 只获得 `kb_create_node` 这个数据节点创建入口，不获得任意组网、创建 Agent 或终端权限。检索 Agent 不获得写入工具。大批次可按原始条目位置分组归档；不增加 Agent。

## 数据与恢复

资料放在本网络数据目录的 `knowledge/` 中。目录是 SQLite；原始输入及历史版本保留；选定类型的文件、数据表和派生索引分别保存。导入文件额外归档原始字节。

有稳定 key 的记录可以原位更新；内容重复不反复增加版本。来源修改后，引用它的页面会提示 `needs_refresh`。索引与原文版本分开登记；失败或中断的物化写入保留 pending 状态，下次打开时恢复。删除隐藏当前记录，历史读取及来源追溯保留。

应用没有将完整资料库注入系统提示或尾部。指南按需加入历史，检索仅返回片段，需要时再取完整内容。

## 共存

使用 `extensions/all` 可同时发现两个应用的组件，公共组件只加载一次。根节点使用哪个应用入口、给哪些工具箱权限，仍由配置决定。装配知识库所需依赖不会把讨论或组网权限交给知识库成员。

本版没有添加 PDF/OCR 导入或通用跨数据库联接；需要这些能力时优先接入现有实现。性能和测试记录见 [验证记录](../../VALIDATION.md)。
