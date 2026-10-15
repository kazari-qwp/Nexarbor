# 本次 Agent 可见文本原文

## 文档

- 去中心化组成员：`extensions/multi_agent/network_presets/decentralized_group/members/AGENTS.md`。
- 讨论组成员：`extensions/multi_agent/network_presets/discussion_group/members/AGENTS.md`。

## 工具与工具箱描述

`datanet_command_logs`，来源 `extensions/foundation/capabilities/command_logs/tools.json`：

> 查询已执行命令的日志。

`datanet_team_finish`，来源 `extensions/multi_agent/network_presets/decentralized_group/tools.json`：

> 提交成果与验收材料，或批准、否决当前候选。

`command_logs` 工具箱，来源 `extensions/foundation/toolboxes/command_logs/box.json`：

> 终端日志查询。

## 新增参数说明

`datanet_team_finish.test_scripts`：

> 已提交的测试脚本在共同工作区中的相对路径。

`datanet_team_finish.test_results`：

> 自己的测试结果文件路径。

`datanet_team_finish.log_ids`：

> 附上的终端日志ID；省略时附上自己本次运行的日志。

## 运行时提示

讨论任务消息中替换的公共笔记说明，来源 `extensions/multi_agent/capabilities/discussion_group/python/datanet/features/network_presets/discussion_group/runtime.py`：

> 公共笔记使用轮初共同快照；Recorder用write_resident_text维护，更新在下一轮可见。

未批准成员结束循环时的提示，来源 `extensions/multi_agent/capabilities/decentralized_group/python/datanet/features/network_presets/decentralized_group/runtime.py`：

> 共同目标尚未收尾。依据当前协作状态继续推进；已有候选时阅读验收材料，有异议指出具体问题，无异议提交批准。

新候选通知，`{candidate_id}` 在实际消息中替换为候选 ID，来源同上：

> 本组已提出成果候选：{candidate_id}。读取 datanet_team_status 中的验收材料，审阅测试脚本、命令、结果和已知问题；无异议批准，有疑问指出具体问题再补测。
