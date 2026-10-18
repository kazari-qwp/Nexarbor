# v8 双组协作网络预设

这是一个可直接手动开启的成品网络，不包含时钟、pulse 或自动执行信号。各 Agent 的模型对话需要人在客户端逐个打开，当前没有发生任何模型协作。

## 冷加载修正：清空虚假 expose

此前三个板节点把模块操作名误写进了 `expose`（讨论板/公告箱的 `send`、`read`，任务板的 `knowledge_search`、`knowledge_get`、`knowledge_put`），导致冷加载把这些名字当作节点工具箱工具校验而拒绝。现已把 `board_discuss`、`board_tasks`、`board_notice` 的 `expose` 全部改为 `[]`，其余模块配置、状态、频道、边和授权保持不变。

原因：模块公开的 `agent_tools` 会由框架自动公开，不需要也不应该写进 `node.expose`；`expose` 只登记实际安装的节点工具箱工具。本次只做配置清理，没有重造模块，也没有执行绑定。

## 网络结构

| 节点 | 类型 | 作用 |
|---|---|---|
| `root` | Agent | 普通入口，只用于手动打开对话；没有管理模块、没有工具收集器、没有出边。 |
| `discuss_eng` / `discuss_pm` / `discuss_qa` | Agent | 讨论组，分别从工程、产品、测试角度在 `board_discuss` 讨论。 |
| `collab_eng` / `collab_pm` / `collab_qa` | Agent | 协作组，在 `board_tasks` 中自行检索并认领任务；没有领导 Agent。 |
| `board_discuss` | Node | 公共讨论板，使用 `messages.box`，只连接讨论组。 |
| `board_tasks` | Node | 共享任务板，使用 `knowledge.collection`，只连接协作组。 |
| `board_notice` | Node | 公共公告箱，使用 `messages.box`，六名成员都可读写。 |

六名成员都装配了：

- `agents.context`：本人私有记忆，提供 `remember`、`recall`、`look`，记忆不通过公共板共享。
- `tools.collector`：按可达范围汇总公开工具。讨论组成员的访问频道为 `tools`、`self`、`chat`，收集本人 `remember` / `recall` / `look`、`board_discuss` 与 `board_notice` 的消息工具；协作组成员增加 `knowledge`，收集本人记忆工具、`board_tasks` 知识工具和 `board_notice` 消息工具。收集器不会拿到另一组的板工具或他人的私人记忆工具。
- 递归依赖 `records.store`、`place.info`：由宿主按组件依赖自动补齐。

复用组件：`messages.box`、`knowledge.collection`、`agents.context`、`tools.collector`。没有新增自定义组件。

## 手动启动

1. 在客户端打开 `root`，它只是入口；也可以直接打开任意一个成员。
2. 打开 `discuss_eng`、`discuss_pm`、`discuss_qa`，它们会先读 `board_discuss` 最近消息，再发表各自视角；需要跨组通知时写 `board_notice`。
3. 打开 `collab_eng`、`collab_pm`、`collab_qa`，让它们用 `knowledge_search` / `knowledge_get` 查看 `board_tasks`，再用 `knowledge_put` 认领任务。
4. 所有成员都可读公告箱 `board_notice`；公告也通过同一个消息箱发送。

成员人格和流程写在各 Agent 的 `data/*.md` 与 `agents.context.persona/common` 中。协作组成员被明确告知：写入任务先带 `expected_revision`，遇到版本冲突必须重新 `knowledge_get` 读取最新 revision 后再重试，不能直接覆盖。

## 任务板初始任务

`board_tasks` 预置了三条任务，初始 revision 都是 1：

- `task-eng`：工程可行性
- `task-pm`：需求与验收范围
- `task-qa`：回归与边界验证

任务没有预设认领人。成员自行读取后更新为“已认领”并写上自己的节点 ID。

## 验收操作

以下操作可在客户端或测试副本中执行。跨节点调用使用正常强度 2 和对应频道。

### 1. 公开讨论板

- `discuss_eng` 调 `board_discuss / messages.box / send`，频道 `chat`，正文自拟。
- `discuss_pm` 调 `board_discuss / messages.box / read`，应读到该消息。
- 同一发送者用同一 `key` 和同一内容再次发送，应返回 `duplicate: true`，不重复追加。

### 2. 公共公告箱

- `collab_qa` 调 `board_notice / messages.box / send`，频道 `chat`。
- `discuss_eng` 调 `board_notice / messages.box / read`，应读到公告。跨组通知依赖这个公共公告箱，而不是讨论板或任务板。

### 3. 任务读写与 CAS 冲突

1. `collab_eng` 调 `board_tasks / knowledge.collection / get` 读取 `task-eng`，得到 `revision: 1`。
2. `collab_eng` 调 `put`，带上 `expected_revision: 1`，成功时 revision 变为 2，表示已认领。
3. 让另一个协作成员用旧的 `expected_revision: 1` 调 `put`，应收到业务错误“文档版本冲突……请先重新读取后再写入”，任务内容不变。
4. 该成员重新 `get` 读到 revision 2，再用 `expected_revision: 2` 调 `put`，应成功并产生 revision 3。

这就是任务板防止同时覆盖的流程。

### 4. 私人记忆

- `discuss_eng` 调自己的 `agents.context / remember`，再调自己的 `recall` 可以读回。
- `discuss_pm` 或任意其他成员去调 `discuss_eng` 的 `recall` / `remember` 应被拒绝（测试环境中为 `PermissionError: Component is outside the current graph view`）。
- 私有记忆只在本节点状态中，不写入任何公共消息箱或任务板。

### 5. 两组隔离与 root 限制

- `discuss_eng` 调 `board_tasks` 的 `knowledge.collection / get` 应被拒绝。
- `collab_eng` 调 `board_discuss` 的 `messages.box / read` 应被拒绝。
- `root` 调 `board_discuss` 或 `board_tasks` 应被拒绝；root 没有任何出边，也没有任务/消息/记忆工具。
- 公告箱是两组共同可达的唯一公共消息箱，不承载任务数据。

## 本次实际验证记录

已在 `network.json` 的独立 candidate 测试副本中实际调用模块，而不是只检查 JSON：

- `board_discuss` 的 `send` 成功，另一讨论成员 `read` 能读到；重复键返回 `duplicate: true`。
- `board_notice` 的协作成员 `send` 成功，讨论成员 `read` 能读到。
- `task-eng` 以 revision 1 认领成功后变为 revision 2。
- 使用旧 revision 1 覆盖时返回版本冲突，且内容保持不变。
- 重新读取 revision 2 后写入成功，版本变为 revision 3。
- 私有 `remember` / `recall` 成功；其他成员越权访问私人记忆被拒绝。
- 讨论成员访问任务板、协作成员访问讨论板、root 访问公共板均被拒绝。
- 六个成员的模块装配和递归依赖均通过验证；六个 `execution.prepare` 均为数组形式 `[{"module":"agents.context","operation":"prepare","arguments":{}}]`。
- 在 candidate 副本中逐个调用六名成员的 `tools.collector / collect`：三名讨论成员各返回 7 个工具（本人的 `remember`、`recall`、`look`，`board_discuss` 的 `send` / `read`，`board_notice` 的 `send` / `read`），不含 `board_tasks` 的知识工具，也不含其他成员的私人记忆工具。
- 三名协作成员各返回 11 个工具（本人的 `remember`、`recall`、`look`，`board_tasks` 的 6 个知识工具，`board_notice` 的 `send` / `read`），不含 `board_discuss` 的消息工具，也不含其他成员的私人记忆工具。

- 冷加载清理后重新 `reset` candidate：`discuss_eng` 的 `tools.collector / collect` 仍返回 7 个工具，`collab_eng` 仍返回 11 个工具，说明模块的 `agent_tools` 自动公开且未受 `expose` 清空影响；讨论板 `send` 成功，另一讨论成员 `read` 能读到同一条消息。

说明：测试环境禁用外部工具和节点工具箱，但 `tools.collector` 的组件公开操作可以正常调用；以上收集结果来自实际调用，而不是静态推断。真实外部工具的副作用仍需另行运行验收。
