# 知识集合

在单个普通节点内保存可检索、可版本恢复的知识归档。组件只使用 `ctx.state` 和本节点锁，不依赖小镇、不读取文件、不调用外部模型，也不访问其他节点状态。

## 装配

- 模块 ID：`knowledge.collection`，版本 `0.1.0`，`node_types: ["node"]`。
- 所有公开操作使用频道 `knowledge`。
- 可挂载到普通 `node`，也可通过真实权限路由由 Agent 调用；Agent 工具已在本模块声明，不需要另外复制到 `offered_tools`。
- 示例配置见 `example.json`。

```json
{
  "config": {
    "title": "营地知识集合",
    "read_only": false,
    "max_entries": 1000,
    "history_limit": 20
  },
  "access": {"strength": 2, "channels": ["knowledge"]}
}
```

配置项：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `title` | 字符串 | 知识集合 | 集合展示名称 |
| `read_only` | 布尔 | `false` | 开启后拒绝 `put`、`remove`、`restore`，数据保持不变 |
| `max_entries` | 整数 | `1000` | 未删除文档数量上限；软删除会释放名额 |
| `history_limit` | 整数 | `20` | 每个文档保留的最近修订数，超出的旧修订被清理 |

配置由客户端按中文 Schema 自动生成表单，本组件没有额外前端页面。

## 操作与 Agent 工具

| 操作 | Agent 工具 | 参数 | 结果 |
|---|---|---|---|
| `put` | 写入知识 | `id` 非空字符串、`title`、`text`、`tags` 字符串数组、可选 `key` | 当前 `id`、`revision`、`deleted`、`created`、`idempotent` |
| `get` | 读取知识 | `id` | `document` 当前内容，包括软删除状态 |
| `search` | 检索知识 | `query` 默认空、`tags` 默认空数组、`limit` 1～50 默认 10 | `items`、`total`；只返回未删除文档 |
| `remove` | 删除知识 | `id` | 软删除，产生新修订并保留历史 |
| `history` | 查看知识历史 | `id` | 有限修订摘要，仅 `revision`、`title`、`deleted` |
| `restore` | 恢复知识修订 | `id`、`revision` 正整数 | 从保留历史创建新的当前修订，原历史条目不被改写 |

`put` 以“请求者 + key”幂等：同一请求者用相同 `key` 重复提交相同内容时返回原文档且不新增修订；相同 `key` 提交不同内容会被拒绝。没有 `key` 时按普通新增或更新处理。

## 检索边界

检索是对标题和正文做不区分大小写的**关键词子串匹配**，并要求文档包含全部指定标签。它不是语义检索、向量检索或外部嵌入模型检索；本组件暂不包含外部嵌入能力，也不声称理解同义词或语义相似度。`history` 只返回修订摘要，不批量暴露历史正文；正文仍保存在本地状态中供 `restore` 使用。

## 并发与失败

写操作在锁内重新读取状态后修改本节点，多个并发 `put` 会串行生成连续修订，不丢更新。业务错误返回 `status: "error"`；参数 Schema 错误、错误频道和断边由框架在执行前拒绝。锁内异常会恢复本节点状态，不会提交半成品修订。

## 测试

`tests/test_knowledge.py` 使用真实 `ModuleHarness` 覆盖：写入/读取/标签关键词检索、软删除默认隐藏、历史恢复与新修订、只读拒绝、容量与历史上限、并发修订、错误频道与断边、幂等与冲突，以及通过真实 Agent 权限路由访问节点工具。运行宿主 `validate` 即可执行。
