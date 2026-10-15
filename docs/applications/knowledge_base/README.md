# 应用二：知识库与应用记忆

根节点就是知识库主 Agent，负责检索、归档和 Wiki 维护。默认自己完成任务，工作量大时创建助手。网络固定为主 Agent 与一层助手，不再设置固定检索员、归档员或 Wiki Agent。

## 组合与复用

| 职责 | 组件 | 实现来源 |
|---|---|---|
| Agent 身份、私人记忆与模型循环接入 | foundation/agent_runtime | 复用第一应用的通用运行时与 Harness 适配层 |
| 工单、回复、空闲唤醒与运行中插话 | foundation/agent_messaging | 复用既有 send 和一次性回复 |
| 原始任务与独立交付文档 | foundation/task_documents | 通用能力，复用普通文本节点、原子写入与检查点 |
| 单层助手与可授予权限检查 | foundation/scoped_workers | 通用能力，应用通过配置声明组件和权限范围 |
| CSV / SQLite | storage/csv、storage/sqlite | 既有 CsvNode、SqliteNode、pandas / SQLite |
| RAG | storage/llamaindex | LlamaIndex 与共享本地嵌入模型 |
| Agent Wiki | storage/llm_wiki | 上游原版 ingest/query/lint 指南、BM25 与链接图分析 |
| Wiki 站点 | storage/markdown_wiki | MkDocs 页面与搜索索引构建 |

知识库能力负责统一记录 ID、来源版本、集合目录和上述存储的适配。上游 llm-wiki 不调用模型；我们的 Agent 在现有 Harness 循环里按其指南维护页面。没有引入另一套 Agent 调度器，也没有复用上游 DB9 云同步。语义矛盾仍需要 Agent 判断。

实现代码都在 capabilities；工具箱、节点预设与网络预设只保留配置和文档。组合关系见 [组件目录](../../COMPONENT_MAP.md)，上游固定版本、许可证和文件哈希见 [第三方复用](../../THIRD_PARTY_COMPONENTS.md)。

## 启用

Harness 插件入口：`datanet-harness/knowledge-base`。也可给通用适配器提供：

```json
{
  "extensionRoot": "E:/DataNet-模块化成品/extensions/knowledge_base",
  "rootNetwork": "knowledge_base",
  "rootToolboxes": ["knowledge_base"],
  "workspace": "E:/我的知识工作区"
}
```

可选依赖：

```powershell
python -m pip install -r extensions/storage/capabilities/llamaindex/requirements.txt
python -m pip install -r extensions/storage/capabilities/markdown_wiki/requirements.txt
python -m pip install -r extensions/storage/capabilities/llm_wiki/requirements.txt
```

llm-wiki 的算法需要 Node.js 22.18+；可用 `wikiNodeBinary` 配置可执行文件路径。其上游源码已固定并随能力组件提供，不在运行时下载。模型与 Python 可选依赖不随源码打包安装。

语义检索配置一次，各集合共用模型：

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

未配置嵌入时仍可存储、读取和关键词检索；语义请求明确报告缺少配置。

## 三种任务入口

这是同一主 Agent 的三种任务模式，没有增加三名固定 Agent 或界面按钮。

- `kb_task(content=原始需求, mode=agent)`：保存需求，由主 Agent 自行判断读写任务。
- `kb_task(content=原始问题, mode=read)`：只读任务，直接进入检索；主 Agent 与助手均不能修改知识记录，仍可写交付文档。
- `kb_task(content=原始资料, mode=write)` 或 `kb_ingest`：进入归档；已有集合或路由时直接保存，否则返回 intake_id，由主 Agent 选择集合并提交。

普通 `kb_catalog`、`kb_search`、`kb_fetch`、`kb_query` 可独立调用，不创建额外模型会话。`kb_ingest` 支持工作区内 CSV、JSON、TXT、Markdown 文件，相对路径基于工作区，拒绝路径越界；导入的原始字节另行保留。

## 按需助手

```json
{}
```

以上参数调用 `datanet_spawn_helper`，创建继承可授予业务权限的通用助手。

```json
{"components": ["wiki"]}
```

选填组件会收窄写入类型；可选 csv、sqlite、rag、wiki 的组合。Wiki 助手仍能读取主 Agent 获准的数据库或原始资料，用作知识依据，但不能写入其他类型。read 模式只装配读取工具。框架自动连接已有的获准数据节点，新建集合也自动连接；不由助手填写内部工具箱、路径或节点接线参数。

助手最多一层，不能继续创建；每任务默认最多八名，可在 topology.json 的 helpers.limit 配置。创建只返回身份和文档引用，通过已有 `datanet_send_message` 下达分工。助手完成后使用消息的一次性回复入口交付，结束原工单；回复可不再回复。

助手范围同时由工具授权、业务组件范围和实际图连接检查约束。仅安装某个组件不会让 Agent 自动获得其权限。通用助手也不会继承终端或任意组网能力，因为知识库主 Agent 没有这些权限。

## 文档交接

框架保存不可经 Agent 工具改写的原始任务文本；大份归档资料通过不可改写的 intake 原件引用，使用 `kb_intake` 分页读取。每个参与者有独立的普通 Markdown 交付节点。

`task_document_read` 默认读取当前原始任务，也可指定交付节点与 task_id；`task_document_write` 只允许写自己的交付文档。来源包含 node_id、locator（记录 ID 或文中位置）和 version。归档回执须来自本任务的实际写入，框架验证记录、版本与节点，不能用一段“已保存”的声明替代。

父 Agent 阅读助手的交付文档，核查后提交自己的文档与引用。独立工作也使用同一路径。文档按需读取，不把完整资料库或所有成果塞入尾部；助手恢复时保留原任务绑定、权限和交付文档。

## Wiki 与持久化

用 `kb_wiki` 按需加载上游指南或执行页面搜索、链接图检查。当前应用的工具映射与原版指南一起提供。链接分析复用上游算法；来源变化检查复用知识库的来源版本记录。页面维护由主 Agent 或获准的 Wiki 助手执行，不另设常驻维护 Agent。

CSV、SQLite、RAG、Wiki 记录统一使用稳定 ID；更新与删除检查 expected_version，保留历史版本。来源更新或删除后，依赖页面标记 needs_refresh。中断的物化写入下次打开恢复；文件导出使用 `kb_export`，Wiki 可生成 MkDocs 站点。

两应用可通过 `extensions/all` 组合，公共组件只加载一次，权限仍明确装配。没有增加 PDF/OCR、任意 SQL 或通用数据库联接。

验证范围与限制见 [验证记录](../../VALIDATION_COMPONENT_KNOWLEDGE.md)，Agent 文案原文及地址见 [审阅清单](../../KNOWLEDGE_AGENT_REVIEW.md)。当前为源码实现，未重新打包发布。
