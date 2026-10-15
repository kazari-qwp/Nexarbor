# 创建与使用去中心化组

用 `datanet_create_network` 创建：`preset=decentralized_group`，提供 `instance_id` 和 `project`。项目说明写明目标、已有方案或初始框架、代码与资料位置、约束和验收标准。`member_count` 为成员人数，默认4，范围1—64；`parent_node_id` 指定挂载节点，省略则挂在自己下面。使用创建结果中的 `group_id` 和实际节点ID。

用 `datanet_cooperate` 下达任务：填写 `group_id`、`action=start` 和本次 `task`；`budget_minutes` 设置时间预算，默认30分钟。成员自行分工、执行、测试和整合成果，本轮剩余成员通过同一成果候选后结束。

个别成员无法继续时，框架释放其未完成认领，剩余成员继续工作；成员会话和个人工作目录保留。本轮退出人数达到一半时通知管理者一次，全部退出才报告小组失败。用 `status` 中的 `active_members` 和 `unavailable` 查看可用成员及退出原因。

启动立即返回 `accepted` 和 `run_id`，表示任务已开始。框架在结束时发送本次结果；期间可用 `action=status` 查看进度，`action=stop` 停止任务。

结束通知的 `status` 表示本次结果，`failure` 说明失败原因；用 `output_id` 读取成果说明，用 `workspace` 找到共同工作目录，按验收标准检查交付物。`archive_path` 是本次归档目录，`report_reference` 可用于查询委托报告。

小组结束后，再次 `start` 并提供 `task` 即可承接下一项任务，沿用成员、会话、个人记忆和工作区。每次有独立 `run_id`；历史归档通过 `status` 返回的 `runs` 查找。
