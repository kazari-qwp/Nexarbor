# 知识库 Agent 文档与描述审阅

本次合并固定角色为主 Agent，增加受限助手与任务文档；以下是实际给 Agent 读取的文件。

## 主 Agent 的职责与任务入口
- [extensions/knowledge_base/network_presets/knowledge_base/prompt.md](../extensions/knowledge_base/network_presets/knowledge_base/prompt.md)
- [extensions/knowledge_base/network_presets/knowledge_base/AGENTS.md](../extensions/knowledge_base/network_presets/knowledge_base/AGENTS.md)
- [extensions/knowledge_base/capabilities/knowledge_agents/USAGE.md](../extensions/knowledge_base/capabilities/knowledge_agents/USAGE.md)

## 助手提示词（依次拼接）

- [extensions/foundation/capabilities/scoped_workers/prompt.md](../extensions/foundation/capabilities/scoped_workers/prompt.md)
- [extensions/knowledge_base/nodes/knowledge_worker/prompt.md](../extensions/knowledge_base/nodes/knowledge_worker/prompt.md)

## 按权限和操作加载的指南

- [extensions/knowledge_base/capabilities/knowledge_tools/AGENTS.md](../extensions/knowledge_base/capabilities/knowledge_tools/AGENTS.md)
- [extensions/knowledge_base/capabilities/knowledge_tools/READING.md](../extensions/knowledge_base/capabilities/knowledge_tools/READING.md)
- [extensions/knowledge_base/capabilities/knowledge_tools/WIKI.md](../extensions/knowledge_base/capabilities/knowledge_tools/WIKI.md)

## 复用的上游原版指南

三份文件保留原文；操作时同时加载 WIKI.md 中的本应用映射。

- [ingest](../extensions/storage/capabilities/llm_wiki/vendor/skills/ingest/SKILL.md)
- [query](../extensions/storage/capabilities/llm_wiki/vendor/skills/query/SKILL.md)
- [lint](../extensions/storage/capabilities/llm_wiki/vendor/skills/lint/SKILL.md)

## 本次新增或修改的工具描述原文

| 工具 | 描述 |
|---|---|
| [kb_ingest](../extensions/knowledge_base/capabilities/knowledge_agents/tools.json) | 接收资料或文件，优先复用已有归档位置。 |
| [kb_task](../extensions/knowledge_base/capabilities/knowledge_agents/tools.json) | 建立知识库任务；可选择自动、只读或归档模式。 |
| [datanet_spawn_helper](../extensions/foundation/capabilities/scoped_workers/tools.json) | 工作量较大时创建助手；可选组件限制其业务范围。 |
| [task_document_read](../extensions/foundation/capabilities/task_documents/tools.json) | 读取原始任务或交付文档。 |
| [task_document_write](../extensions/foundation/capabilities/task_documents/tools.json) | 更新自己的交付文档，记录结果与依据。 |
| [kb_wiki](../extensions/knowledge_base/capabilities/knowledge_tools/tools.json) | 维护 Wiki 时读取操作指南、检索页面或检查链接与过期来源。 |

## 工具箱描述原文

| 工具箱 | 描述 |
|---|---|
| [knowledge_base](../extensions/knowledge_base/toolboxes/knowledge_base/box.json) | 知识库读写、维护与按需并行处理。 |
| [knowledge_worker](../extensions/knowledge_base/toolboxes/knowledge_worker/box.json) | 知识资料的分类、读写与维护。 |
| [helper_creation](../extensions/foundation/toolboxes/helper_creation/box.json) | 创建单层任务助手。 |
| [task_documents](../extensions/foundation/toolboxes/task_documents/box.json) | 原始任务与交付文档。 |

`kb_ask` 与两个固定角色已删除；原有数据读写工具描述未改。组件说明和开发验证文档不是 Agent 上下文。


## 2026-10-15 实测后的指南修订

工具名称、简短描述和角色提示词未改。以下三份按需指南修正了实际使用中暴露的参数歧义：

- `extensions/knowledge_base/capabilities/knowledge_agents/USAGE.md`：知识记录的 locator 仅填单个真实记录 ID；文档位置引用单独说明；只读任务不填写写入回执。
- `extensions/knowledge_base/capabilities/knowledge_tools/AGENTS.md`
- `extensions/knowledge_base/capabilities/knowledge_tools/READING.md`

后两份新增原文：

> kb_query 仅用于 SQLite。计数用 aggregate={"function":"count"}；求和、平均值、最小值、最大值还须在 aggregate 内填写 field，fields 只选择返回列。CSV 的条件筛选用 kb_search 的 filters。

USAGE 修订段落原文：

> 核查助手交付后再提交结果。引用知识记录时，sources 每项对应一条记录：node_id、version 沿用 kb_fetch 的返回值，locator 只填该记录 ID，不填说明文字或多个 ID。引用任务或交付文档时，node_id 填文档节点，locator 可标文中位置。receipts 只填本任务实际存储返回的记录；只读任务不填。无需反复转述完整内容。

## 2026-10-15 结构感知检索

Agent 可见指南本次只修改以下两份，角色提示词未改：

- [知识库读写指南](../extensions/knowledge_base/capabilities/knowledge_tools/AGENTS.md)：存储选择、文档/碎片集合、原文与章节读取、来源核实和索引重建。
- [只读检索指南](../extensions/knowledge_base/capabilities/knowledge_tools/READING.md)：从检索入口展开上下文、分页和固定版本引用。

两种用途复用同一 RAG 组件，可分别建集合，不自动规定必须创建两个集合。独立碎片不生成虚假的章节，目录用 has_structure 标明是否存在标题结构。

工具描述修改原文（参数定义在同一个 tools.json）：

| 工具 | 描述 |
|---|---|
| [kb_fetch](../extensions/knowledge_base/capabilities/knowledge_tools/tools.json) | 读取完整原文、文档目录，或展开章节与相邻上下文。 |
| [kb_search](../extensions/knowledge_base/capabilities/knowledge_tools/tools.json) | 检索知识入口，返回片段、来源和按需展开的读取参数。 |

新增 kb_fetch 参数：view、section_id、start_line、end_line、offset、max_chars、limit；新增 kb_index 参数 rebuild。其余工具描述不变。

## 2026-10-15 统一 Wiki 页面入口

本次修改四份给 Agent 读取的指南，角色提示词未改，上游原版指南未改：

- [AGENTS.md](../extensions/knowledge_base/capabilities/knowledge_tools/AGENTS.md)：完整文本/碎片可直接保存为 Wiki，统一搜索，维护原文与来源，沿链接访问和索引维护。
- [READING.md](../extensions/knowledge_base/capabilities/knowledge_tools/READING.md)：统一搜索入口、局部结构及页面链接的按需读取，处理歧义和历史版本。
- [WIKI.md](../extensions/knowledge_base/capabilities/knowledge_tools/WIKI.md)：上游操作映射，明确正文向量检索与原有 BM25 的区别。
- [USAGE.md](../extensions/knowledge_base/capabilities/knowledge_agents/USAGE.md)：交付 sources 可直接沿用读取返回的 evidence，避免记录 ID 与框架节点 ID 混淆。

工具描述修改原文：

| 工具 | 描述 |
|---|---|
| [kb_fetch](../extensions/knowledge_base/capabilities/knowledge_tools/tools.json) | 读取知识页或原文，按需展开章节与关联链接。 |
| [kb_index](../extensions/knowledge_base/capabilities/knowledge_tools/tools.json) | 更新 Wiki 或文档集合的语义索引。 |

kb_fetch 新增 view=links，沿 links_next_fetch 分页。搜索结果 entry、页面及局部阅读结果的 links 给出可直接沿用的读取参数；该链接不授予任何额外读取权限。

USAGE 本次引用说明原文：

> 引用知识记录时，sources 每项可直接沿用 kb_fetch 返回的 evidence；如手动填写，node_id、version 沿用返回值，locator 只填单个记录 ID，不填说明文字，也不把记录 ID 当作节点 ID。
