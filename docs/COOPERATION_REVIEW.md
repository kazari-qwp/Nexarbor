# 可配置人数与去中心化协作

讨论组：`member_count` 仅计算普通成员，默认3；固定 Leader、Recorder 各一名。去中心化组：平等工作成员默认4。范围1—64，使用各预设成员模板和通用展开器自动生成节点、资源及连接。

## 模块归属

| 功能 | 组件 |
|---|---|
| 通用成员模板展开 | tools/network_management 内的 templates.py |
| 可配置人数讨论组 | network_presets/discussion_group |
| 去中心化状态、事件与收尾 | network_presets/decentralized_group |
| 成员工作流程提示词 | agent_presets/cooperative_worker |
| 组内工具装配 | toolboxes/cooperation |
| 调用者启动、状态与停止工具 | toolboxes/cooperation_control |
| 异步委托回送事件与取消 | tools/agent_delegation |
| 原生取消与关闭时的通信处理 | adapters/harness/framework |

Python core 未加入这些预设的业务分支。工作区使用每组独立 Git 仓库及每成员独立 worktree；每组序列化合并，冲突保留成员提交。

## Agent 文档

- `components/network_presets/discussion_group/AGENTS.md`
- `components/network_presets/decentralized_group/AGENTS.md`
- `components/agent_presets/cooperative_worker/prompt.md`
- `components/network_presets/discussion_group/python/datanet/components/networks/discussion_group/README.md`

## 新增工具描述原文

### datanet_cooperate

启动、查看或停止去中心化协作小组。

### datanet_team_status

查看本组任务、成员、认领与共享发现；可搜索完整记录。

### datanet_team_claim

认领子任务及文件路径、补充路径，或完成、释放自己的认领。

### datanet_team_note

向本组共享记录发布发现、事实、失败尝试或成果摘要。

### datanet_team_send

向本组其他成员发信；运行中插话，空闲时唤醒。

### datanet_team_workspace

查看个人工作目录、同步共同成果或提交并整合修改。

### datanet_team_finish

提出最终成果，或验收、否决当前成果候选。

## 当前收尾规则

无有效认领时可提出成果候选；全体成员批准同一候选后完成。否决后继续，时间或请求预算耗尽返回未完成。成员局部结果保存在报告中，框架向调用者回送一次组级结果。客户端中断时正在执行的操作标记 interrupted，未开始的同组任务取消；保留代码、记忆、记录及报告，避免自动重复不确定操作。
