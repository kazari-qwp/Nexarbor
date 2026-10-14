# 消息、尾部与终端环境改动审阅

Agent 指南：
- [通信指南](E:/DataNet-模块化成品/components/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md)
- [协作成员指南](E:/DataNet-模块化成品/components/network_presets/decentralized_group/members/AGENTS.md)

工具描述原文：
- datanet_pending_messages：查看工单和回复，或结束无需继续处理的消息。
- datanet_team_status：按需查看本组认领、共享记录或验收材料。

新增参数说明原文（datanet_send_message 和 datanet_team_send 共用）：
- message_type：work_order 需要答复；reply 可不回复。
- 默认 work_order；一次性回复工具自动发送 reply。

查询参数说明原文：
- datanet_pending_messages.message_id：close 时填写要结束的消息 ID。
- datanet_team_status.section：选择要读取的内容。

框架消息标识原文：
- 此为回复，可以不回。

尾部标识原文：
- 存在待处理工单。
- 存在未读回复。
- 目前有成果等待审核。

执行阶段示例：
```text
[协作组：hone-exec]
阶段：执行。
```
审核阶段仅未批准当前候选的成员收到审核提醒，候选替换后重新计算。共享记录、认领、成员名单、运行 ID 与候选材料不再常驻尾部。

终端错误提示原文：
- Python 导入失败：将 workdir 设为包含目标包的项目根目录；确认依赖文件已同步。
- Python 写入被拒绝：核对目标是否在工作区或 $env:TEMP；临时文件使用 tempfile 的默认目录。

## 通信指南原文

需要查可主动联系的对象时，用 datanet_contacts_channel 查看通讯录。用 datanet_send_message 发信，填 target 和 content；运行中插话，空闲时唤醒，accepted 表示已投递。
message_type=work_order 表示需要答复的工单（默认）；message_type=reply 表示可不回复的信息。收到消息后可用其中的 reply_tool 回复，参数只有 content，调用一次后失效，发出的消息自动归为回复。
尾部的“存在待处理工单。”表示尚有工单未结束；“存在未读回复。”表示还有回复未读。用 datanet_pending_messages 查看，读取后未读提醒消失，回复工具仍可使用。无需继续处理的消息可用 action=close、message_id 结束。回复前的“此为回复，可以不回。”表示无需确认收到。
需要对方执行委托任务时使用 datanet_call_agent；讨论发言提交黑板。

## 协作成员指南原文

# 去中心化组成员工作指南

本次任务和个人工作目录由任务消息提供；项目资料已首次加载。尾部显示小组和当前阶段；“目前有成果等待审核。”表示当前候选尚未获你批准。用 `datanet_team_status section=claims` 查看认领，`section=records` 查看共享记录，`section=candidate` 查看候选正文和验收路径，`section=summary` 查看任务和成员；省略 section 查看全部。`query` 填记录 ID 或关键词查完整记录；需要重读项目资料时用绑定的查询工具。

用 `datanet_team_claim action=claim` 认领工作，`scope` 描述子任务。预计添加、修改或删除文件时，`paths` 填工作区相对路径，如 `src/parser.py`；可认领整个目录，如 `src/parsers/`，调查任务可省略。执行中需扩大范围时，用 `action=extend`、原 `claim_id` 和新增 `paths` 补充。返回 `conflict` 时查看已有认领者，通过 `datanet_team_send` 协商。同名任务、相同路径或目录包含关系会产生冲突。

在个人工作目录使用文件、终端工具执行和测试。`datanet_team_workspace action=inspect` 查看个人及共同目录，`action=sync` 同步共同成果，`action=publish` 提交并整合修改。整合冲突时保留个人提交，在个人目录同步、解决冲突、验证后再提交。完成认领用 `action=complete` 并提供 `evidence`；无法继续时用 `action=release`。

用 `datanet_team_note` 共享有用的信息：`OBSERVED` 记录观察，`FACT` 记录已确认事实，`FAIL` 记录失败尝试，`PATCH_SUMMARY` 记录修改摘要。用 `datanet_team_send` 联系同伴、协商依赖和范围；`message_type=work_order` 表示需要答复，`message_type=reply` 表示可不回复的信息。

测试报告、日志和临时产物放在 `inspect` 返回的 `artifacts_path`。终端日志由框架保存；查看其他片段时用 `datanet_command_logs` 列出或读取原日志。

所有有效认领结束后，用 `datanet_team_finish action=propose` 提交最终成果正文和证据，`test_scripts` 填已提交的测试脚本相对路径，`test_results` 填结果文件路径。可用 `log_ids` 选取终端日志，省略时附上自己本次运行的日志。框架保存当前提交的源码和验收材料快照，在候选的 `review` 中返回路径。

验收同伴候选时，通过 `datanet_team_status` 找到材料，阅读脚本、命令、结果和已知问题；无异议用 `action=approve`，有异议指出具体问题，按需补测或 `action=reject`。填写当前 `candidate_id` 和 `evidence`。提出或批准候选后可结束本轮等待；否决或收到新消息后继续工作。全体通过后框架保存成果并通知调用者。
