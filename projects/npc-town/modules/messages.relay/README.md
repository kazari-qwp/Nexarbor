# 私信便笺中继

把一条便笺沿 `chat` 频道转交给另一位当前可达真实 Agent 的 `messages.box`。中继不保存消息、不提供读取；消息存储、读取范围和重复键幂等全部沿用收件人的消息箱。

## 装配

- 装在每位居民 Agent 节点上，与该居民的 `messages.box` 同节点；`requires` 已声明 `messages.box`。
- 模块访问频道：`chat`、`records`、`self`，默认强度 2。
- 居民之间需要有 `chat` 频道的方向可达边。A 调用自己的中继时，A 必须能到达 B 的 `messages.box`。
- 收件人的消息箱默认 `require_agent: true` 时会回查发送者资料，因此实际网络里收件人也要能沿自身授权访问发送者（通常居民之间保留双向 `chat` 边）。

## 操作与工具

- 操作 `send_to(channels: ["chat","self"])`
  - `recipient`：节点 ID，必须是当前网络可达、`node_type` 为 `agent` 且不是自己的节点。
  - `text`：非空便笺正文，最长 4000 字符。
  - `topic`：可选话题，默认空字符串。
  - `key`：可选去重键，沿用 `messages.box` 的幂等语义。
- 成功时原样返回消息箱结果，至少含 `id/from/to/duplicate`；`from` 是最初发起请求的居民，不是中继节点。
- Agent 工具：`send_to`（名称“发送私信”）。

## 错误与限制

- 收件人是自己、不可达、不是真实 Agent、未装 `messages.box` 或无法沿 `chat` 访问其私信箱时，返回清晰错误，不产生半条消息。
- 不新增存储，不提供读取操作。读取继续由收件人调用自己的 `messages.box.read`；默认读取范围为 `self`，其他居民不能代读。
- 重复 `key` 只返回原消息 ID 与 `duplicate: true`，不会重复投递；同一键配不同内容由消息箱拒绝。
