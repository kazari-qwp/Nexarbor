# 四部分重构与组件拆解表

核心、适配层、可选执行器、协作扩展包的边界见 [架构说明](ARCHITECTURE.md)。本表记录源组件的最终归属。

| 原功能/组件 | 新模块/组件 | 配置与资源位置 |
|---|---|---|
| `agent_presets/cooperative_worker` | `nodes/agent_cooperative_worker` | `extensions/multi_agent/nodes/agent_cooperative_worker/` |
| `agent_presets/coordinator` | `nodes/agent_coordinator` | `extensions/multi_agent/nodes/agent_coordinator/` |
| `agent_presets/discussion_leader` | `nodes/agent_discussion_leader` | `extensions/multi_agent/nodes/agent_discussion_leader/` |
| `agent_presets/discussion_member` | `nodes/agent_discussion_member` | `extensions/multi_agent/nodes/agent_discussion_member/` |
| `agent_presets/discussion_recorder` | `nodes/agent_discussion_recorder` | `extensions/multi_agent/nodes/agent_discussion_recorder/` |
| `agent_presets/experiment_report` | `nodes/agent_experiment_report` | `extensions/multi_agent/nodes/agent_experiment_report/` |
| `agent_presets/leader` | `nodes/agent_leader` | `extensions/multi_agent/nodes/agent_leader/` |
| `agent_presets/member` | `nodes/agent_member` | `extensions/multi_agent/nodes/agent_member/` |
| `agent_presets/number_manager` | `nodes/agent_number_manager` | `extensions/multi_agent/nodes/agent_number_manager/` |
| `agent_presets/number_worker` | `nodes/agent_number_worker` | `extensions/multi_agent/nodes/agent_number_worker/` |
| `agent_presets/operator` | `nodes/agent_operator` | `extensions/multi_agent/nodes/agent_operator/` |
| `agent_presets/recorder` | `nodes/agent_recorder` | `extensions/multi_agent/nodes/agent_recorder/` |
| `agent_presets/worker` | `nodes/agent_worker` | `extensions/multi_agent/nodes/agent_worker/` |
| `network_presets/creation_validation` | `capabilities/creation_validation` | `extensions/multi_agent/network_presets/creation_validation/` |
| `network_presets/decentralized_group` | `capabilities/decentralized_group` | `extensions/multi_agent/network_presets/decentralized_group/` |
| `network_presets/delegated_number` | `capabilities/delegated_number` | `extensions/multi_agent/network_presets/delegated_number/` |
| `network_presets/discussion_group` | `capabilities/discussion_group` | `extensions/multi_agent/network_presets/discussion_group/` |
| `network_presets/experiment_analysis` | `capabilities/experiment_analysis` | `extensions/multi_agent/network_presets/experiment_analysis/` |
| `network_presets/number_network` | `capabilities/number_network` | `extensions/multi_agent/network_presets/number_network/` |
| `network_presets/project_root` | `capabilities/project_root` | `extensions/multi_agent/network_presets/project_root/` |
| `nodes/csv` | `capabilities/csv` | `extensions/multi_agent/nodes/csv/` |
| `nodes/llamaindex` | `capabilities/llamaindex` | `extensions/multi_agent/nodes/llamaindex/` |
| `nodes/sqlite` | `capabilities/sqlite` | `extensions/multi_agent/nodes/sqlite/` |
| `nodes/text` | `capabilities/text` | `extensions/multi_agent/nodes/text/` |
| `nodes/value` | `capabilities/value` | `extensions/multi_agent/nodes/value/` |
| `skills/network_management` | `capabilities/network_management` | `extensions/multi_agent/capabilities/network_management/` |
| `toolboxes/agent_delegation` | `toolboxes/agent_delegation` | `extensions/multi_agent/toolboxes/agent_delegation/` |
| `toolboxes/agent_feedback` | `toolboxes/agent_feedback` | `extensions/multi_agent/toolboxes/agent_feedback/` |
| `toolboxes/agent_management` | `toolboxes/agent_management` | `extensions/multi_agent/toolboxes/agent_management/` |
| `toolboxes/agent_messaging` | `capabilities/agent_messaging` | `extensions/multi_agent/toolboxes/agent_messaging/` |
| `toolboxes/command_execution` | `capabilities/command_execution` | `extensions/multi_agent/toolboxes/command_execution/` |
| `toolboxes/command_logs` | `toolboxes/command_logs` | `extensions/multi_agent/toolboxes/command_logs/` |
| `toolboxes/cooperation` | `toolboxes/cooperation` | `extensions/multi_agent/toolboxes/cooperation/` |
| `toolboxes/cooperation_control` | `toolboxes/cooperation_control` | `extensions/multi_agent/toolboxes/cooperation_control/` |
| `toolboxes/discussion` | `toolboxes/discussion` | `extensions/multi_agent/toolboxes/discussion/` |
| `toolboxes/discussion_member` | `toolboxes/discussion_member` | `extensions/multi_agent/toolboxes/discussion_member/` |
| `toolboxes/engineering` | `toolboxes/engineering` | `extensions/multi_agent/toolboxes/engineering/` |
| `toolboxes/experience` | `capabilities/experience` | `extensions/multi_agent/toolboxes/experience/` |
| `toolboxes/experience_access` | `toolboxes/experience_access` | `extensions/multi_agent/toolboxes/experience_access/` |
| `toolboxes/experience_maintenance` | `toolboxes/experience_maintenance` | `extensions/multi_agent/toolboxes/experience_maintenance/` |
| `toolboxes/file_reader` | `toolboxes/file_reader` | `extensions/multi_agent/toolboxes/file_reader/` |
| `toolboxes/interface_management` | `toolboxes/interface_management` | `extensions/multi_agent/toolboxes/interface_management/` |
| `toolboxes/local_data` | `capabilities/local_data` | `extensions/multi_agent/toolboxes/local_data/` |
| `toolboxes/network_access` | `capabilities/network_access` | `extensions/multi_agent/toolboxes/network_access/` |
| `toolboxes/network_management` | `toolboxes/network_management` | `extensions/multi_agent/toolboxes/network_management/` |
| `toolboxes/network_management_skill` | `toolboxes/network_management_skill` | `extensions/multi_agent/toolboxes/network_management_skill/` |
| `toolboxes/node_creation` | `toolboxes/node_creation` | `extensions/multi_agent/toolboxes/node_creation/` |
| `toolboxes/node_operations` | `toolboxes/node_operations` | `extensions/multi_agent/toolboxes/node_operations/` |
| `toolboxes/official_readonly` | `toolboxes/official_readonly` | `extensions/multi_agent/toolboxes/official_readonly/` |
| `toolboxes/official_skills` | `toolboxes/official_skills` | `extensions/multi_agent/toolboxes/official_skills/` |
| `toolboxes/official_tools` | `toolboxes/official_tools` | `extensions/multi_agent/toolboxes/official_tools/` |
| `toolboxes/problem_handling` | `capabilities/problem_handling` | `extensions/multi_agent/toolboxes/problem_handling/` |
| `toolboxes/problem_steps` | `toolboxes/problem_steps` | `extensions/multi_agent/toolboxes/problem_steps/` |
| `toolboxes/recovery` | `toolboxes/recovery` | `extensions/multi_agent/toolboxes/recovery/` |
| `toolboxes/self_repair` | `toolboxes/self_repair` | `extensions/multi_agent/toolboxes/self_repair/` |
| `toolboxes/skill_loader` | `toolboxes/skill_loader` | `extensions/multi_agent/toolboxes/skill_loader/` |
| `toolboxes/topology_inspection` | `toolboxes/topology_inspection` | `extensions/multi_agent/toolboxes/topology_inspection/` |
| `tools/agent_delegation` | `capabilities/agent_delegation` | `extensions/multi_agent/capabilities/agent_delegation/` |
| `tools/agent_lifecycle` | `capabilities/agent_lifecycle` | `extensions/multi_agent/capabilities/agent_lifecycle/` |
| `tools/command_logs` | `capabilities/command_logs` | `extensions/multi_agent/capabilities/command_logs/` |
| `tools/execution_records` | `capabilities/execution_records` | `extensions/multi_agent/capabilities/execution_records/` |
| `tools/network_management` | `capabilities/tools_network_management` | `extensions/multi_agent/capabilities/tools_network_management/` |
| `tools/reports` | `capabilities/reports` | `extensions/multi_agent/capabilities/reports/` |

| 原核心或适配功能 | 最终位置 |
|---|---|
| 普通 Agent 节点、私人记忆文件 | 核心 `core/agent_node.py` |
| 普通文本节点 | 核心 `core/text_node.py` |
| 原 Python Agent 模型循环 | 可选执行器 `executors/minimal/` |
| Agent 角色配置、创建与管理策略 | `capabilities/agent_identity/` |
| 常驻与查询文本行为 | `capabilities/text/`，配置位于 `nodes/text/` |
| MALFORMED_RESPONSE 有限次纠正 | `capabilities/response_recovery/` |
| 终端等待、硬上限及清理策略 | `capabilities/command_execution/` |
| Harness RPC、原生事件与请求适配 | `adapters/harness/` |
| 旧状态迁移、旧工作区回退、旧工具箱嵌套 | 删除 |

工具箱只保存工具 ID 列表；代码全部位于能力目录。含原 Python 示例实现的预设，其实现也归能力，原拓扑与资料归网络预设。每个角色或示例配置按引用读取自己的资源正文。
