# 去中心化协作小组

创建 `decentralized_group`，填写 `project`（目标、约束、验收标准）；`member_count` 为平等工作成员数量，默认4，范围1—64。成员有独立会话、个人记忆和官方文件、终端工具。

调用 `datanet_cooperate`，`action=start`，使用返回的 `group_id` 并提供 `task`。立即返回运行ID；最终状态由框架回送。`status` 查看进度，`stop` 停止运行。默认时间预算30分钟，每成员最多100次模型请求；预算耗尽会停止并报告未完成。关闭客户端后保留状态，通过 `status` 检查；进行中的操作不会自动重做。

小组结束后，用同一 `group_id` 再次 `start` 并提供 `task` 即可执行下一次任务。成员、会话、个人记忆和工作区保留；每次使用新的 `run_id`，认领、共享发现、验收候选和预算分别管理。`output` 保存当前任务成果；历史运行与归档路径通过 `status` 返回的 `runs` 查找，结束通知也包含本次 `archive_path`。运行中的任务须先结束或 `stop`，才能启动下一次。

成员自主选择工作，无需逐轮等待：用 `datanet_team_status` 了解状态，`datanet_team_claim` 认领任务；同名的有效认领会提示冲突，更广的范围重叠由成员通过 `datanet_team_send` 协商。完成认领要提供证据，无法继续时释放认领。

在个人工作目录执行任务。`datanet_team_workspace inspect` 返回个人目录和共同成果目录；`sync` 同步共同成果；`publish` 提交并整合修改。整合冲突时保留个人提交，回到个人目录同步、解决冲突和验证后再提交。实际文件和终端操作使用已有官方工具。

用 `datanet_team_note` 发布观察、已确认事实、失败尝试和成果摘要，帮助同伴避免重复工作。最新协作状态和最近20条记录放在请求尾部；完整记录通过 `datanet_team_status query` 搜索或读取 findings 查询文本。

全部认领结束后，任一成员可用 `datanet_team_finish propose` 提出最终成果。其他成员对照目标、验收标准和实际成果，使用候选ID `approve` 或 `reject` 并说明证据。全体通过同一候选后框架保存 output、结束协作并通知调用者；否决后继续工作。共同验收是成员判断，调用者仍按实际验收标准检查交付物。
