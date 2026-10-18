# 知识归档网络预设

## 用途

这是一个可运行的知识归档小网络：

- `root`：网络入口，也是可手动对话的「资料管理员」Agent。
- `knowledge`：知识集合节点，保存文档正文、标签、修订历史和软删除状态。

资料管理员通过自身挂载的 `tools.collector` 收集知识库公开的六个工具，以及自己的 `remember`、`recall`、`look` 私人工具，再按用户对话调用：

| 工具 | 作用 |
| --- | --- |
| `knowledge_put` | 新增或更新文档并生成新修订 |
| `knowledge_get` | 读取当前正文和状态 |
| `knowledge_search` | 按关键词和标签检索 |
| `knowledge_history` | 查看修订摘要 |
| `knowledge_remove` | 软删除文档，保留历史 |
| `knowledge_restore` | 从指定历史修订恢复出新修订 |

## 复用组件

本网络没有新造组件，全部使用已发布组件，并通过配置组合：

- `knowledge.collection`：知识归档、关键词检索、修订历史、软删除与恢复。
- `agents.context`：管理员人格、上下文和仅本人可读写的私人记忆。
- `records.store`、`place.info`：`agents.context` 的本地依赖。
- `tools.collector`：管理员动态工具收集器，覆盖 `tools`、`knowledge` 和 `self` 频道。

Agent 执行使用官方 `harness` 执行器：`prepare` 是数组，只调用本节点已挂载的 `agents.context.prepare`，用于准备人格、现况和私人记忆；没有使用 `tool_provider` 之类的宿主不支持字段。

## 结构与权限

- 只有 `root` 到 `knowledge` 的单向边，频道为 `tools` 和 `knowledge`。
- `knowledge` 没有任何出边，因此知识节点无法访问 `root` 的私人记忆。
- 未挂载终端、任意网络管理或修改连接的模块。
- 管理员私人笔记保存在 `root` 的 `agents.context` 私有记忆中，不写入知识库；`tools.collector` 的 `access.channels` 包含 `self`，因此能收集管理员自己的 `remember`、`recall` 和 `look` 工具。

## 使用指南

1. 在客户端应用本预设，打开 `root` 的对话。
2. 录入资料时给出文档 ID、标题、正文和标签，例如：
   「把文档 `guide` 归档，标题『归档指南』，标签 `归档`、`指南`，正文……」
3. 检索时说明关键词或标签，例如：
   「检索标签为 `归档`、正文含『检索』的文档。」
4. 读取、删除、恢复时使用文档 ID；恢复需说明历史修订号。
5. 写入、删除和恢复前，管理员会先读取当前 `revision`，再带上 `expected_revision` 操作，避免覆盖并发修改。

## 可调参数

- `knowledge.collection.config.title`：知识集合名称。
- `knowledge.collection.config.read_only`：只读模式，开启后拒绝写入、删除和恢复。
- `knowledge.collection.config.max_entries`：最大未删除文档数，默认 1000。
- `knowledge.collection.config.history_limit`：每个文档保留的修订数，默认 20。
- `agents.context.config.persona` / `common` / `opening`：管理员人格、通用规则和开场提示。
- `agents.context.config.max_memories`：管理员私人笔记保留上限，默认 100。

## 能力边界

- 检索是标题与正文的本地关键词子串匹配，标签为全部包含过滤；**不是向量检索，也不是语义 RAG**。
- 检索只返回未删除文档的摘要；已软删除文档仍可用 `get` 查看状态，并可恢复。
- 恢复不会改写历史修订，而是把旧内容复制为新的当前修订。
- 真实模型对话和外部副作用需要在正式运行环境中另行验收；本预设只负责网络配置、权限和组件装配。

## 已验证流程

在候选网络测试副本中实际执行：

1. `put` 第一版，得到 `revision 1`。
2. `put` 第二版并带 `expected_revision: 1`，得到 `revision 2`。
3. `search` 关键词加标签，命中第二版。
4. `remove` 带 `expected_revision: 2`，得到 `revision 3`，文档为软删除状态。
5. `restore` 到修订 1，得到 `revision 4`，`restored_from: 1`。
6. `get` 确认正文回到第一版，当前 `revision` 为 4。

另外验证了相同幂等键重复写入不新增修订、过期 `expected_revision` 返回版本冲突且不修改数据、错误频道被拒绝，以及知识节点无法访问管理员私人记忆。

在候选网络副本中以 `root` 调用自己的 `tools.collector.collect`，成功收集到九个工具：六个知识工具 `knowledge_put`、`knowledge_get`、`knowledge_search`、`knowledge_history`、`knowledge_remove`、`knowledge_restore`，以及管理员自己的 `remember`、`recall`、`look`。同时以 `self` 频道调用 `agents.context.prepare`，成功返回人格系统提示词、现况与私人记忆上下文，确认本地 prepare 数组有效。正式网络未做任何修改。
