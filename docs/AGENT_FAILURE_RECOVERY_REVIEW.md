# 本次 Agent 文档与框架提示审阅

## 修改的指南

- extensions/multi_agent/network_presets/decentralized_group/AGENTS.md：创建者查看退出状态、半数通知和剩余成员验收。
- extensions/multi_agent/network_presets/decentralized_group/members/AGENTS.md：成员接续退出者的认领及剩余成员验收。
- extensions/multi_agent/network_presets/discussion_group/AGENTS.md：普通成员退出后继续讨论，Leader/Recorder 失败报告未完成。

三个角色的原始提示词未修改。工具名称、参数和简短描述未修改。

## JSON 纠错反馈原文

实现：adapters/harness/framework/request-recovery.js。

```text
上一次工具调用的参数不是合法JSON，工具未执行。请重新生成正确的工具调用。
原始错误：{Harness 原始错误消息}
工具：{工具名}
参数原文：
{未被改写或截断的参数字符串}
JSON解析错误：{JSON.parse 的错误消息}
```

如果日志里没有对应的错误参数，仅添加前两行。该反馈作为普通历史消息进入同一个 Agent 的下一次请求；失败流留在 Harness 的尝试日志中。每个出错步骤最多纠正重试两次。只处理 `MALFORMED_RESPONSE` 中的 `tool input is invalid JSON`。

## 成员退出广播原文

执行组仍在运行：

```text
成员 {节点ID} 已退出本轮，其未完成认领已释放。用 datanet_team_status 查看退出原因、认领和工作区，继续推进共同目标。
```

剩余成员完成验收：

```text
共同成果已获本轮剩余成员验收，协作结束。请停止当前工作并简短回复。
```

## 半数退出通知中的 message 原文

去中心化组：

```text
本轮至少一半成员已退出；剩余成员继续工作。
```

如果全部退出且管理者不同于任务调用者：

```text
本轮全部成员已退出，小组无法继续。
```

讨论组：

```text
本轮至少一半普通成员已退出；Leader、Recorder和剩余成员继续讨论。
```

通知采用 JSON 消息，类型分别为 `cooperation_degraded`、`discussion_degraded`，包含 group_id、run_id、退出人数、初始人数、剩余成员、退出原因和 continuing。每轮任务只通知一次；全部失败的最终结果仍正常发送任务调用者。

## Recorder 汇总任务增加的一行

```text
本轮已退出的普通成员：{节点ID列表；没有时为“无”}。
```

执行组退出成员再次尝试本轮工作时，框架返回“成员已退出本轮协作”；成员达到请求额度时返回“成员请求预算已结束”。下一轮 start 会重新启用全部成员。
