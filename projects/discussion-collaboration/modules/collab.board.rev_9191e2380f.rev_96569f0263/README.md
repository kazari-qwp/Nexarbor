# 认领协作板

## 用途

给一组平等成员提供一张共享的任务认领板：

- 控制方开启一轮协作，列出任务与计划路径；
- 成员自主认领任务路径，路径前缀相同或相等即视为冲突并拒绝；
- 成员可以补充路径、释放认领、记录提交与修改摘要；
- 成员可以共享发现、失败原因和修改摘要；
- 成员退出时自动释放其未完成认领，已完成任务与提交摘要保留；
- 轮次结束后全部进度仍可读取，便于复盘或交给后续组件。

路径认领在同一任务内检查重叠；它不是全项目路径锁，也不限制成员在文件系统中的写入。不同任务的修改范围应先协调。

本模块**只记录协作状态**：不执行 Git、不校验提交是否存在、不做验收、不调度 Agent。Git 成果整合和全员验收由已发布的 `git.integrator` 承担。

## 装配

模块只装在普通 `node` 上（`node_types: ["node"]`）。成员是沿成员发现频道可达的真实 Agent 节点，模块只读取它们的 `metadata.node_id`、名称和 `node_type`。

节点 `access.channels` 至少需要：

```json
["collaboration", "collaboration.work"]
```

其中 `collaboration` 用于 `open` 时发现成员；如果修改了 `member_channel`，还要把实际频道加入授权。`collaboration.work` 用于 `open` 后广播工作信号。若配置了 `integrator_module`，还要把 `integrator_channel`（默认 `collaboration`）加入节点授权，并把整合器模块装在同一节点上。

建议连接：

- 协作板 → 每位成员：`collaboration`（成员发现）、`collaboration.work`（工作信号）；
- 每位成员 → 协作板：`collaboration`；
- 控制方 → 协作板：`collaboration`。

操作频道：

| 操作 | 频道 |
|---|---|
| `open` | `collaboration` |
| `list` / `status` | `collaboration` |
| `claim` / `extend` / `complete` | `collaboration` |
| `release` / `leave` | `collaboration` |
| `discover` / `fail` | `collaboration` |
| `close` | `collaboration` |

## 配置

| 字段 | 默认 | 说明 |
|---|---|---|
| `member_channel` | `["collaboration"]` | 成员发现频道；`ctx.network.nodes` 只接受 `metadata.node_type == "agent"` 的节点。 |
| `max_tasks` | `100` | 单轮最大任务数，范围 1–500；`open` 超限时整单拒绝。 |
| `max_shared` | `500` | 发现与失败摘要保留条数，范围 10–2000。 |
| `channel_modes` | `{}` | 频道匹配模式；`member_channel` 支持 allow/deny。 |
| `integrator_module` | `""` | 同节点整合器模块 ID，例如 `git.integrator`；留空表示退出不同步。填写后 `leave` 会调用它的 `leave` 操作。 |
| `integrator_channel` | `["collaboration"]` | 调用整合器时的频道，非空；节点 `access.channels` 与连接边必须同时允许。仅在 `integrator_module` 非空时使用。 |

## 操作

### `open`

```json
{
  "run_id": "round-1",
  "tasks": [
    {"id": "api", "title": "实现接口", "paths": ["src/api"], "detail": "可选说明"},
    {"title": "补测试", "paths": ["tests"]}
  ],
  "key": "open-round-1"
}
```

- 任务至少 1 项；`id` 可省略，省略时生成 `task-1`、`task-2`……并避开已给定的 ID。
- 同一 `key` 且请求内容相同返回原结果并标记 `duplicate: true`；已有运行中轮次但键不同则报错。
- 成员列表为空、任务超限或成员发现失败时不写入状态。
- 成功后向 `collaboration.work` 发送 `{run, phase: "working", tasks: [id...]}`，返回 `{run, duplicate, tasks, members}`。

### `list` / `status`

- `list` 返回 `run`、完整任务（含认领与完成信息）、成员和共享记录；`include_closed` 默认保留已结束轮次，显式传 `false` 可隐藏已结束轮次的任务与共享明细。
- `status` 返回轮次、任务概览（总数/未完成/已完成/open/claimed）、成员、共享记录；默认附最近 20 条事件，传 `include_events: false` 可省略事件。

### `claim` / `extend`

```json
{"task": "api", "paths": ["src/api/routes.py"], "key": "claim-api"}
```

- 调用者必须是当前轮次中的有效成员；任务必须存在且未完成。
- 新路径与同任务其他有效成员已认领路径前缀相同或相等时拒绝，并列出冲突成员与路径；**不修改任何状态**。
- 同一成员已有该任务认领时，`claim` 提示改用 `extend`；`extend` 合并到本人已有认领。
- 检查和写入在同一 `ctx.network.lock_nodes([ctx.node_id])` 事务内完成。
- 相同 `key` 的重复请求返回 `duplicate: true`，不会重复追加。

### `release` / `complete`

- `release`：本人省略 `member` 释放自己的认领；控制方带 `member` 代释放。已完成任务不能释放，事件保留。
- `complete`：本人必须已认领该任务；记录 7–64 位十六进制 `commit` 和 1–2000 字修改摘要，任务变为 `completed`。

### `discover` / `fail`

记录 `{kind: discovery|failure, member, task, text, at}`，受 `max_shared` 限制。调用者必须是有效成员；指定任务时必须存在。

### `leave`

本人省略 `member`，或控制方带 `member` 让成员退出。成员标记为 `left`，所有未完成认领被释放，相关任务在没有其他认领时回到 `open`；已完成任务、提交和摘要保留。返回 `{member, released_tasks, released_paths, duplicate, integrator, integrator_error}`。

若配置了 `integrator_module`，在协作板事务锁释放之后，模块会用 `integrator_channel` 调用同节点该模块的 `leave`，参数为 `{member, reason}`，使 Git 候选验收成员同步退出并重新计算待验收名单。重复 `leave`（任务板已是 `left`）仍会继续传播，整合器按自己的幂等规则返回 `duplicate`。整合器成功时 `integrator` 为其返回数据、`integrator_error` 为 `null`；调用失败时 `integrator` 为 `null`、`integrator_error` 为明确原因，已经提交的协作板状态不会被改写。

### `close`

结束当前轮次，写入 `ended_at` 和摘要事件，保留全部任务、认领、成员与共享记录。结束后不能继续认领、完成或共享；`list`/`status` 仍可读取进度。再次 `open` 会开启新轮次并替换当前轮次状态。

## 状态

- `run`：当前轮次 `{id,status,task_count,started_at,ended_at}`；
- `tasks`：任务映射，含 `title/detail/paths/status/claims/commit/summary/completed_at`；
- `shared`：有界共享记录；
- `members`：`{id,name,status,left_reason}`；
- `events`：最近 200 条 `{at,kind,member,text}`；
- `seen`：有界幂等键回执（最多 1000 条）。

## Agent 工具

声明了 `list`、`claim`、`extend`、`release`、`complete`、`discover`、`fail`，以及 `leave`（退出协作），供工具收集器使用。工具沿当前网络的调用身份执行，不额外增加权限。

`leave` 工具供真实 Agent 成员使用：调用时省略 `member`，只退出请求者本人，自己的未完成认领随之释放，其他成员可以重新认领同一路径；重复退出返回 `duplicate: true`。带 `member` 的代退出不属于该工具用法，仍只能由控制方经 `collaboration` 调用 `leave` 操作完成。

## 限制

- 不执行 Git、不校验 `commit` 是否真实存在、不合并分支；这些属于 `git.integrator`。
- 核心访问激活不携带本次请求实际使用的频道名。`release` / `leave` 使用 `collaboration`，模块用“控制方节点或非本轮成员”的身份再校验 `member` 代操作；成员不能借 `member` 参数代他人释放或退出。真正的频道边界仍由节点 `access.channels` 和边频道约束。
- 框架的 Agent 工具参数模式复用对应操作：`leave` 工具因此仍会列出操作中可选的 `member` 字段。工具用法是省略它、退出请求者本人；活动成员若填写 `member` 会被控制方校验拒绝，不会因此获得代他人退出的权限。
- 成员发现依赖 `member_channel` 上的真实可达路径；没有 Agent 成员时 `open` 会失败，而不是创建空板。
- 同一协作板只维护一个当前轮次；需要并行多个团队时装配多个实例。

activity_timeout_seconds 为本模块所有发出信号的有限总时限和目标处理时限，默认 86400 秒；适用于包含资料读取、模型执行和验证的长任务。核心信号默认值保持不变。
