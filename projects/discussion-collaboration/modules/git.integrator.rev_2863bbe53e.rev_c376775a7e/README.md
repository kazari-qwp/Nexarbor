# Git 成果整合与全员验收

## 用途

多位平等成员各自在自己的 worktree／分支上完成提交。本模块负责：

1. 校验成员提交确实存在、是提交对象，并且可以从该成员声明的分支到达；
2. 按成员 ID 排序，把各成员提交**串行**合并成一个候选提交；
3. 用 `cand-` 开头的确定性标识标记候选，组织全员验收；
4. 只有仍在参与且属于该候选的成员全部认可同一个候选，才把整合分支推进到候选提交；
5. 否决、退出、重复请求、整合失败和重开都有明确状态。

不负责认领任务、创建团队、调度模型或运行 Agent。成员集合沿 `member_channel` 从真实拓扑动态发现：频道上 `metadata.node_type` 为 `agent` 的节点即成员，`node_id` 即成员 ID，与 `collab.board` 的成员发现规则一致。成员分支默认由 `member_branch_prefix` 加安全化后的节点 ID 生成；`config.members` 只用于显式分支覆盖和旧装配兼容，不再决定成员集合。

## 装配要求

模块通过宿主公开终端端口执行 Git，默认使用 `harness:pwsh`：

- 装配节点须在 `offered_tools` 中提供 `{"ref":"harness:pwsh","channels":["workspace"]}`；
- 节点 `access.channels` 须包含操作频道、`workspace` 以及成员发现频道（默认 `collaboration`）；
- 成员 Agent 节点须能从本模块节点沿 `member_channel` 实际到达；不可达或不是 `agent` 类型的节点不会被伪造成成员；
- 也可以把 `terminal_ref` 和 `terminal_channels` 配成其他公开终端端口／频道，但节点仍须实际提供并授权。

操作频道：

| 操作 | 频道 |
|---|---|
| `submit` | `collaboration` |
| `integrate` | `collaboration` |
| `approve` / `veto` / `reopen` | `collaboration` |
| `leave` | `collaboration` |
| `promote` | `collaboration` |
| `read` | `collaboration` |

## 配置

| 字段 | 说明 |
|---|---|
| `repository` | Git 仓库工作目录，建议绝对路径。 |
| `base_branch` | 尚无整合分支时的起点，默认 `main`。 |
| `integration_branch` | 验收通过后才推进的分支，默认 `nexarbor/integration`。 |
| `candidate_ref_prefix` | 候选引用前缀，默认 `refs/nexarbor/candidates/`。 |
| `member_channel` | 成员发现频道数组，默认 `["collaboration"]`。沿这些频道用 `ctx.network.nodes` 发现真实 Agent 节点，`node_id` 即成员 ID。 |
| `member_branch_prefix` | 成员分支前缀，默认 `member/`。成员分支 = 前缀 + 安全化后的节点 ID；`~`、空格、`^`、`:`、`?`、`*`、`[`、`\` 等 Git 引用非法字符替换为 `-`。 |
| `members` | 可选覆盖／旧装配兼容，默认 `[]`，不再决定成员集合。仅当 `id` 与发现的节点 ID 一致时，`branch` 才覆盖自动生成的分支；未发现的配置成员不参与。`branch` 也可省略，由前缀自动生成，`submit` 参数仍可覆盖。 |
| `terminal_ref` | 宿主终端端口，默认 `harness:pwsh`。 |
| `terminal_channels` | 调用终端的频道，默认 `["workspace"]`。 |
| `command_timeout_ms` | 单条 Git 命令超时，默认 60000。 |
| `busy_lease_seconds` | 外部操作占用租期，默认 900；进程异常退出后可恢复。 |

成员集合每次操作都会重新按拓扑发现。显式 `leave` 后不会被重新发现悄悄恢复；只是暂时不可发现（频道或拓扑短暂变化）的成员仍保留状态，重新可达时恢复参与。一个 Agent 成员都发现不到时，模块返回明确的 `config` 阶段错误，而不是伪造空成员或沿用 `config.members`。团队创建和成员生命周期仍归其他组件。

## 典型流程

```json
{"member":"alice","commit":"<提交哈希>"}
```

1. 每位成员调用 `submit`；
2. 调用 `integrate`：
   - 未提交的参与成员会阻止整合；
   - 生成候选提交并写入 `refs/nexarbor/candidates/<候选 ID>`；
   - 此时**不**推进整合分支；
3. 成员用候选 ID 调用 `approve` 或 `veto`；
4. 全员认可后，模块把整合分支推进到候选提交；若推进时整合分支已被外部更新，则拒绝覆盖，返回 `promotion_failed`，可调用 `promote` 重试；
5. 被否决的候选可调用 `reopen`，保留同一候选 ID 和候选提交，轮次加一、清空表决后重新验收。

候选 ID 由“基线提交 + 成员/提交列表 + 整合分支”确定性计算，相同输入得到相同 ID；重复 `integrate` 返回同一候选。

## 关键行为

- **成员发现**：每次 `submit`／`integrate`／`approve`／`veto`／`leave`／`reopen`／`read` 都沿 `member_channel` 重新发现成员；`config.members` 只覆盖分支。显式退出保持退出；频道不可达或没有 Agent 成员时返回错误，不用配置数组兜底。
- **冲突**：合并使用 `git merge-tree --write-tree`，不签出工作区。冲突时只中止候选，不删除或移动任何成员提交；冲突文件行写入 `state.last_failure.conflict_lines`，成员可解决后重新 `submit`。
- **个人提交保留**：模块只创建候选提交、候选引用和验收通过后的整合分支推进，从不执行 `reset`、`clean`、删除分支或强推。
- **否决**：任一仍在参与的候选成员否决，候选立即为 `vetoed`，整合分支不推进。
- **退出**：进行中候选的 `leave` 会移除该成员的当前表决并重新计算仍参与的成员，剩余成员全员认可时可以通过。已经 `passed` 的候选会在发布时冻结 `acceptance`（当时所需成员与完整表决）；之后退出、拓扑变化、读取或归档都保留这段验收事实。个人提交始终保留。
- **重复请求**：同一成员重复提交同一提交、重复认可、重复否决（同一理由）、重复 `integrate`、重复 `leave` 返回 `duplicate: true`，不会重复计数或重复建候选。
- **失败**：整合失败写入 `state.last_failure`（阶段、成员、提交、冲突行、详情），当前候选不被替换；成功整合后清除。
- **重开**：只有 `vetoed` 候选可 `reopen`；`passed` 不可重开，新成果应重新 `submit`。`promotion_failed` 使用 `promote` 重试。
- **并发**：模块用带租期的 `busy` 占用串行化外部 Git 操作；第二个并发请求会收到明确的“正在执行”错误，而不是交错写候选。

## 已知限制

- 需要 Git 2.38 或更新版本以支持 `merge-tree --write-tree`。
- 候选引用会保留用于审计；本模块不自动清理。
- 模块不校验调用者是否就是所声明的成员；成员身份和调用权限应由上层团队组件、频道和边授权约束。
- 模块不处理模型调度、任务认领、团队创建，也不主动发送信号。
- 同一仓库可以装配多个实例并使用不同的整合分支／候选前缀；但多个实例操作**同一个整合分支**时，仍应由外部保证只有一个实例在推进，或确保不会同时通过不同候选。模块只保护单实例内的外部操作串行化。
- 模块没有 `agent_tools`，也不生成或调度 Agent；装配在以 Agent 为主体的节点上不属于本组件的使用方式。

1.0.4 的发布历史保留修复由真实 Git 零 API 回归验证。Hone 整体实测使用修复前模块，本次局部修复未进行付费重跑。
