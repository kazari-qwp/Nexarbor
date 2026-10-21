# 讨论会话（discussion.session）

一组讨论的运行与协议中心。它负责发现 `discussion.seat` 席位、建立运行身份、推进轮次、保存完整发言、接收 Leader 决策与 Recorder 草稿、生成最终成果，并处理停止、重开、成员退出和失败报告。

本模块**不运行模型、不拼装提示词**。参与者是真实 Agent 节点，另行安装 `discussion.seat` 席位模块；会话节点只按配置频道调用席位的 `describe`，再用信号把轮次和阶段通知出去。

## 装配方式

1. 在讨论中心节点安装 `discussion.session`，节点类型为 `node`。
2. 在每个参与者 Agent 节点安装 `discussion.seat`。席位 `describe` 应返回：

   ```json
   {"id": "节点 ID", "name": "显示名", "role": "leader"}
   ```

   `role` 只能是 `leader`、`recorder`、`member`；一次运行要求恰好 1 名 leader、1 名 recorder、至少 1 名 member。
3. 建立可达关系：
   - 会话节点 → 每个席位节点：允许 `discussion`（发现与 `describe`），并允许 `discussion.round`、`discussion.decision`、`discussion.record`（协议信号）。
   - 每个席位节点 → 会话节点：允许 `discussion`、`discussion`、`discussion.record`；需要读取或退出的再允许 `discussion`、`discussion`。
   - 控制台／编排 Agent → 会话节点：允许 `discussion`、`discussion`。
4. 按 `example.json` 装配会话节点访问授权，至少包含：

   `discussion`、`discussion`、`discussion`、`discussion`、`discussion.record`、`discussion.round`、`discussion.decision`、`discussion`。

`member_channel` 与 `channel_modes` 共同决定发现频道；如果席位安装正确但发现为空，先检查该频道是否在会话节点访问授权和连线中。

## 频道

| 频道 | 用途 |
| --- | --- |
| `discussion` | 发现 `discussion.seat` 并调用 `describe`；也作为连接席位的通道 |
| `discussion` | `start`、`advance`、`leave`、`stop`，以及读取 `read`/`status` |
| `discussion` | 参与者提交完整发言、本人退出 |
| `discussion` | 参与者或控制方读取运行、发言、决策、草稿和成果 |
| `discussion` | Leader 提交决策与任务清单 |
| `discussion.record` | Recorder 写章节、生成最终成果 |
| `discussion.round` | 会话节点发出的轮次信号，content 含 `run/round/phase/task/expected` |
| `discussion.decision` | 进入 deciding 的信号，content 含 `run/round/phase/task` |
| `discussion.record` | 进入 drafting 的信号，content 含 `run/phase/task/decision` |

## 配置参数

| 字段 | 类型 | 范围 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `rounds` | 整数 | 1..20 | 3 | 一次运行完成的讨论轮数；`start` 可用参数临时覆盖 |
| `max_speech_chars` | 整数 | 100..8000 | 4000 | 单条发言正文上限 |
| `max_speeches` | 整数 | 10..5000 | 500 | 当前运行保留的完整发言条数，超出删除最旧 |
| `max_runs` | 整数 | 1..50 | 20 | 历史运行摘要保留条数 |
| `member_channel` | 字符串数组 | 非空 | `["discussion"]` | 参与者发现频道 |
| `channel_modes` | 对象 | allow/deny | `{}` | 按频道声明允许或拒绝，与授权相交后使用 |

## 操作与参数

| 操作 | 频道 | 参数 | 返回 |
| --- | --- | --- | --- |
| `start` | `discussion` | `task` 1..2000；`rounds` 可选 1..20；`key` 可选 | `run/status/round/participants/duplicate` |
| `speak` | `discussion` | `text` 1..`max_speech_chars`；`round` 可选；`key` 可选 | `run/round/phase/recorded/waiting_for` |
| `read` | `discussion`、`discussion` | `round` 可选；`limit` 1..200，默认 20 | `run/participants/speeches/decision/draft/artifact/errors/events` |
| `decide` | `discussion` | `decision` 1..4000；`tasks[]`（0 项起，标题、路径、可选说明）；`key` 可选 | `run/phase/tasks` |
| `draft` | `discussion.record` | `section` 1..200；`text` 1..8000；`key` 可选 | `run/phase/sections` |
| `finish` | `discussion.record` | `title` 可选 1..200 | `run/artifact` |
| `advance` | `discussion` | `reason` 可选 | `run/round/phase/missing` |
| `leave` | `discussion`、`discussion` | `member` 可选；`reason` 可选 | `run/round/phase/member/missing/duplicate` |
| `stop` | `discussion` | `reason` 可选 | 运行摘要 |
| `status` | `discussion`、`discussion` | `include_history` 可选 | 状态、参与者、发言数、决策/草稿/成果摘要、错误、历史 |

`speak` 的调用者必须是当前运行中 `status=active` 的参与者，且轮次必须等于当前轮。同一 `(run, member, round, key)` 的相同正文只记录一次；相同键配不同正文会报错。`speak`、`advance`、`leave` 推进轮次时，用 `lock_nodes([会话节点])` 保护状态变更，发出信号在锁外进行。最后两位参与者并发发言时只会推进一次；迟到的同轮发言仍会被保存，但不会重复推进。

`decide` 仅限 Leader 且阶段为 `deciding`；`draft`、`finish` 仅限 Recorder，分别要求 `drafting` 阶段、已有决策且至少一个草稿章节。`finish` 生成的 Markdown 包含标题、讨论任务、Leader 决策、任务清单（标题/路径/说明）和 Recorder 章节；任务清单继承决策。

`leave` 允许本人退出，或由不在参与者名单中的控制方经 `discussion` 指定成员退出。退出后该成员从后续轮次的 `expected` 中移除；如果本轮剩余 active 成员都已发言，会按 `speak` 的规则继续推进。退出会写入参与者状态，并在 `events` 中留下一条 `kind=leave` 记录。重复退出是幂等成功，返回 `duplicate:true`，不会重复写事件或改变等待名单。

`stop` 对处于 `discussing/deciding/drafting` 的运行置为 `stopped` 并归档历史；已完成或已停止的运行不会被改写。再次 `start` 会生成新的运行身份，清空本次发言/决策/草稿/成果，保留历史摘要。

## Agent 工具

`agent_tools` 提供 `speak`、`read`、`decide`、`draft`、`finish`、`leave`，全部复用同名公开操作，不额外扩大授权。Agent 工具可见的操作仍取决于会话节点访问频道与网络连线。`leave` 是成员自助入口：调用时省略 `member`，只退出请求者本人；带 `member` 的代退出仍只供控制方经 `discussion` 使用。

## 状态

- `run`：当前运行 `id/status/task/phase/round/rounds/started_at/ended_at/error`。
- `participants`：`[{id,name,role,status}]`，`status` 为 `active|left`。
- `speeches`：当前运行的完整发言，按 `max_speeches` 截断。
- `decision`：`{text,tasks[],member,at}` 或 `null`。
- `draft`：`{sections:[{name,text,updated_at}]}`。
- `artifact`：`{run,title,content,tasks[],at}` 或 `null`。
- `runs`：最近 `max_runs` 条历史摘要。
- `errors`：最近 20 条错误。
- `events`：最近 200 条讨论事件；成员退出记录 `at/kind/member/text`。
- `receipts`：最近 300 条幂等键记录。

运行身份形如 `disc-<8 位十六进制>`；发言身份形如 `sp-<8 位十六进制>`。

发言返回 accepted_round（本条发言记录在哪一轮）与 round（操作后的当前轮次）。全体发言完成会推进 round，accepted_round 保留本条记录的轮次。

activity_timeout_seconds 为本模块所有发出信号的有限总时限和目标处理时限，默认 86400 秒；适用于包含资料读取、模型执行和验证的长任务。核心信号默认值保持不变。
