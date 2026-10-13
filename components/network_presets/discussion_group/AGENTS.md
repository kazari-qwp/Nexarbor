# 创建与使用讨论组

用 `datanet_create_network` 创建：`preset=discussion_group`，提供 `instance_id`。项目资料可用 `project_nodes` 引用一个或多个已有查询文本节点；否则用 `project` 填写背景、目标、约束和已有结论，两种方式选一种。`member_count` 为普通成员人数，默认3，另有固定 Leader、Recorder 各一名；`rounds` 为讨论轮数，默认8，范围1—8。`parent_node_id` 指定挂载节点，省略则挂在自己下面。保存返回的 `group_id` 和文档入口。

用 `datanet_discuss`，填写 `group_id` 和 `task`，说明本次要讨论的问题及交付要求。框架调度全部成员和轮次，最后由 Recorder 汇总成果。

调用完成后，返回结果包含成果正文、`run_id`、`archive_path` 和 `report_reference`。按本次问题与交付要求检查成果；创建结果中的 `entry_points.output` 是当前成果节点，`archive_path` 保存本次历史归档。

同一小组可以继续使用。完成后显式填写 `task` 会开始新讨论，即使文字相同也重新执行；省略 `task` 时，未完成则续跑原任务，已完成则读取已有成果。成员会话、个人记忆和项目资料保留，新任务的公共笔记、发言板和成果重新建立。
