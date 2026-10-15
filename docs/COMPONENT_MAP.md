# 可组合组件目录

共享实现位于 foundation 与 storage；应用用 extension.json 选择组件。同一组件只装配一次。

| 组件 ID | 唯一源码位置 | 直接依赖 |
|---|---|---|
| `capabilities/agent_delegation` | `extensions/foundation/capabilities/agent_delegation` | `capabilities/agent_runtime` |
| `capabilities/agent_identity` | `extensions/foundation/capabilities/agent_identity` |  |
| `capabilities/agent_lifecycle` | `extensions/foundation/capabilities/agent_lifecycle` | `capabilities/tools_network_management`, `capabilities/agent_identity`, `capabilities/agent_runtime` |
| `capabilities/agent_messaging` | `extensions/foundation/capabilities/agent_messaging` | `capabilities/agent_identity` |
| `capabilities/agent_runtime` | `extensions/foundation/capabilities/agent_runtime` | `capabilities/agent_identity` |
| `capabilities/command_execution` | `extensions/foundation/capabilities/command_execution` | `capabilities/agent_identity` |
| `capabilities/command_logs` | `extensions/foundation/capabilities/command_logs` | `capabilities/agent_identity` |
| `capabilities/creation_validation` | `extensions/multi_agent/capabilities/creation_validation` | `capabilities/agent_identity`, `nodes/value` |
| `capabilities/csv` | `extensions/storage/capabilities/csv` |  |
| `capabilities/decentralized_group` | `extensions/multi_agent/capabilities/decentralized_group` | `capabilities/tools_network_management`, `capabilities/agent_delegation`, `capabilities/text`, `toolboxes/engineering`, `capabilities/agent_messaging`, `nodes/agent_cooperative_worker`, `capabilities/agent_identity`, `capabilities/agent_runtime`, `capabilities/shared_workspace` |
| `capabilities/delegated_number` | `extensions/multi_agent/capabilities/delegated_number` | `capabilities/agent_identity`, `nodes/value` |
| `capabilities/discussion_group` | `extensions/multi_agent/capabilities/discussion_group` | `nodes/agent_discussion_leader`, `nodes/agent_discussion_member`, `nodes/agent_discussion_recorder`, `nodes/agent_leader`, `nodes/agent_member`, `nodes/agent_recorder`, `capabilities/text`, `capabilities/tools_network_management`, `capabilities/agent_identity`, `capabilities/agent_runtime` |
| `capabilities/document_structure` | `extensions/storage/capabilities/document_structure` |  |
| `capabilities/execution_records` | `extensions/foundation/capabilities/execution_records` | `capabilities/agent_identity` |
| `capabilities/experience` | `extensions/foundation/capabilities/experience` | `capabilities/agent_identity` |
| `capabilities/experiment_analysis` | `extensions/multi_agent/capabilities/experiment_analysis` | `capabilities/agent_identity`, `nodes/csv`, `nodes/sqlite` |
| `capabilities/knowledge_agents` | `extensions/knowledge_base/capabilities/knowledge_agents` | `capabilities/scoped_workers`, `capabilities/knowledge_tools`, `nodes/knowledge_worker`, `toolboxes/knowledge_reader` |
| `capabilities/knowledge_store` | `extensions/knowledge_base/capabilities/knowledge_store` | `nodes/csv`, `nodes/sqlite`, `nodes/llamaindex`, `capabilities/markdown_wiki`, `capabilities/document_structure`, `capabilities/llm_wiki` |
| `capabilities/knowledge_tools` | `extensions/knowledge_base/capabilities/knowledge_tools` | `nodes/knowledge_collection`, `capabilities/llm_wiki` |
| `capabilities/llamaindex` | `extensions/storage/capabilities/llamaindex` |  |
| `capabilities/llm_wiki` | `extensions/storage/capabilities/llm_wiki` | `capabilities/document_structure` |
| `capabilities/local_data` | `extensions/foundation/capabilities/local_data` |  |
| `capabilities/markdown_wiki` | `extensions/storage/capabilities/markdown_wiki` |  |
| `capabilities/network_access` | `extensions/foundation/capabilities/network_access` | `capabilities/agent_identity` |
| `capabilities/network_management` | `extensions/foundation/capabilities/network_management` | `capabilities/tools_network_management`, `capabilities/agent_identity` |
| `capabilities/number_network` | `extensions/multi_agent/capabilities/number_network` | `capabilities/agent_identity`, `nodes/value` |
| `capabilities/place_actions` | `extensions/npc_world/capabilities/place_actions` | `capabilities/world_state` |
| `capabilities/problem_handling` | `extensions/foundation/capabilities/problem_handling` | `capabilities/experience`, `capabilities/execution_records`, `capabilities/tools_network_management`, `capabilities/agent_identity` |
| `capabilities/project_root` | `extensions/multi_agent/capabilities/project_root` | `capabilities/text`, `capabilities/agent_identity`, `capabilities/tools_network_management`, `capabilities/agent_runtime`, `toolboxes/network_access`, `toolboxes/node_creation`, `toolboxes/agent_management`, `toolboxes/interface_management`, `toolboxes/discussion`, `toolboxes/recovery`, `toolboxes/discussion_member`, `toolboxes/engineering`, `toolboxes/cooperation`, `toolboxes/agent_delegation`, `toolboxes/agent_messaging`, `toolboxes/problem_handling`, `toolboxes/cooperation_control` |
| `capabilities/reports` | `extensions/foundation/capabilities/reports` | `capabilities/execution_records`, `capabilities/agent_identity` |
| `capabilities/response_recovery` | `extensions/foundation/capabilities/response_recovery` |  |
| `capabilities/round_barrier` | `extensions/foundation/capabilities/round_barrier` |  |
| `capabilities/scoped_workers` | `extensions/foundation/capabilities/scoped_workers` | `capabilities/agent_runtime`, `capabilities/task_documents`, `toolboxes/agent_messaging` |
| `capabilities/shared_workspace` | `extensions/foundation/capabilities/shared_workspace` |  |
| `capabilities/sqlite` | `extensions/storage/capabilities/sqlite` |  |
| `capabilities/task_documents` | `extensions/foundation/capabilities/task_documents` |  |
| `capabilities/text` | `extensions/foundation/capabilities/text` |  |
| `capabilities/tools_network_management` | `extensions/foundation/capabilities/tools_network_management` | `capabilities/agent_identity`, `capabilities/agent_runtime` |
| `capabilities/value` | `extensions/storage/capabilities/value` |  |
| `capabilities/world_runtime` | `extensions/npc_world/capabilities/world_runtime` | `capabilities/place_actions`, `capabilities/agent_runtime`, `capabilities/network_access`, `nodes/npc_resident`, `nodes/npc_child` |
| `capabilities/world_state` | `extensions/npc_world/capabilities/world_state` | `capabilities/round_barrier` |
| `network_presets/creation_validation` | `extensions/multi_agent/network_presets/creation_validation` | `capabilities/creation_validation`, `nodes/value` |
| `network_presets/decentralized_group` | `extensions/multi_agent/network_presets/decentralized_group` | `capabilities/decentralized_group`, `toolboxes/network_access`, `toolboxes/engineering`, `toolboxes/cooperation` |
| `network_presets/delegated_number` | `extensions/multi_agent/network_presets/delegated_number` | `capabilities/delegated_number`, `nodes/value` |
| `network_presets/discussion_group` | `extensions/multi_agent/network_presets/discussion_group` | `capabilities/discussion_group`, `toolboxes/network_access`, `toolboxes/discussion_member` |
| `network_presets/experiment_analysis` | `extensions/multi_agent/network_presets/experiment_analysis` | `capabilities/experiment_analysis`, `nodes/csv`, `nodes/sqlite` |
| `network_presets/knowledge_base` | `extensions/knowledge_base/network_presets/knowledge_base` | `capabilities/knowledge_agents`, `toolboxes/knowledge_base` |
| `network_presets/number_network` | `extensions/multi_agent/network_presets/number_network` | `capabilities/number_network`, `nodes/value` |
| `network_presets/project_root` | `extensions/multi_agent/network_presets/project_root` | `capabilities/project_root` |
| `network_presets/small_town` | `extensions/npc_world/network_presets/small_town` | `capabilities/world_runtime`, `toolboxes/world_operator`, `toolboxes/world_resident` |
| `nodes/agent_cooperative_worker` | `extensions/multi_agent/nodes/agent_cooperative_worker` | `toolboxes/engineering` |
| `nodes/agent_coordinator` | `extensions/multi_agent/nodes/agent_coordinator` | `toolboxes/discussion`, `toolboxes/network_management_skill`, `toolboxes/node_operations`, `toolboxes/topology_inspection`, `capabilities/agent_identity` |
| `nodes/agent_discussion_leader` | `extensions/multi_agent/nodes/agent_discussion_leader` | `capabilities/agent_identity` |
| `nodes/agent_discussion_member` | `extensions/multi_agent/nodes/agent_discussion_member` | `capabilities/agent_identity` |
| `nodes/agent_discussion_recorder` | `extensions/multi_agent/nodes/agent_discussion_recorder` | `capabilities/agent_identity` |
| `nodes/agent_experiment_report` | `extensions/multi_agent/nodes/agent_experiment_report` | `capabilities/agent_identity` |
| `nodes/agent_leader` | `extensions/multi_agent/nodes/agent_leader` |  |
| `nodes/agent_member` | `extensions/multi_agent/nodes/agent_member` |  |
| `nodes/agent_number_manager` | `extensions/multi_agent/nodes/agent_number_manager` | `capabilities/agent_identity` |
| `nodes/agent_number_worker` | `extensions/multi_agent/nodes/agent_number_worker` | `capabilities/agent_identity` |
| `nodes/agent_operator` | `extensions/multi_agent/nodes/agent_operator` | `toolboxes/engineering`, `toolboxes/node_operations`, `toolboxes/official_skills` |
| `nodes/agent_recorder` | `extensions/multi_agent/nodes/agent_recorder` |  |
| `nodes/agent_worker` | `extensions/multi_agent/nodes/agent_worker` |  |
| `nodes/csv` | `extensions/storage/nodes/csv` | `capabilities/csv` |
| `nodes/knowledge_collection` | `extensions/knowledge_base/nodes/knowledge_collection` | `capabilities/knowledge_store` |
| `nodes/knowledge_worker` | `extensions/knowledge_base/nodes/knowledge_worker` | `toolboxes/knowledge_worker`, `toolboxes/task_documents`, `toolboxes/agent_messaging` |
| `nodes/llamaindex` | `extensions/storage/nodes/llamaindex` | `capabilities/llamaindex` |
| `nodes/npc_child` | `extensions/npc_world/nodes/npc_child` |  |
| `nodes/npc_resident` | `extensions/npc_world/nodes/npc_resident` |  |
| `nodes/sqlite` | `extensions/storage/nodes/sqlite` | `capabilities/sqlite` |
| `nodes/text` | `extensions/foundation/nodes/text` | `capabilities/text` |
| `nodes/value` | `extensions/storage/nodes/value` | `capabilities/value` |
| `toolboxes/agent_delegation` | `extensions/foundation/toolboxes/agent_delegation` | `capabilities/tools_network_management`, `capabilities/agent_delegation` |
| `toolboxes/agent_feedback` | `extensions/foundation/toolboxes/agent_feedback` | `capabilities/problem_handling` |
| `toolboxes/agent_management` | `extensions/foundation/toolboxes/agent_management` | `capabilities/tools_network_management` |
| `toolboxes/agent_messaging` | `extensions/foundation/toolboxes/agent_messaging` | `capabilities/agent_messaging` |
| `toolboxes/command_execution` | `extensions/foundation/toolboxes/command_execution` | `capabilities/command_execution` |
| `toolboxes/command_logs` | `extensions/foundation/toolboxes/command_logs` | `capabilities/command_logs` |
| `toolboxes/cooperation` | `extensions/multi_agent/toolboxes/cooperation` | `capabilities/decentralized_group` |
| `toolboxes/cooperation_control` | `extensions/multi_agent/toolboxes/cooperation_control` | `capabilities/decentralized_group`, `network_presets/decentralized_group` |
| `toolboxes/discussion` | `extensions/multi_agent/toolboxes/discussion` | `capabilities/discussion_group`, `network_presets/discussion_group` |
| `toolboxes/discussion_member` | `extensions/multi_agent/toolboxes/discussion_member` | `capabilities/discussion_group` |
| `toolboxes/engineering` | `extensions/foundation/toolboxes/engineering` | `capabilities/command_logs`, `toolboxes/command_logs` |
| `toolboxes/experience` | `extensions/foundation/toolboxes/experience` | `capabilities/experience` |
| `toolboxes/experience_access` | `extensions/foundation/toolboxes/experience_access` | `capabilities/execution_records`, `capabilities/experience` |
| `toolboxes/experience_maintenance` | `extensions/foundation/toolboxes/experience_maintenance` | `capabilities/experience` |
| `toolboxes/file_reader` | `extensions/foundation/toolboxes/file_reader` |  |
| `toolboxes/helper_creation` | `extensions/foundation/toolboxes/helper_creation` | `capabilities/scoped_workers` |
| `toolboxes/interface_management` | `extensions/foundation/toolboxes/interface_management` | `capabilities/tools_network_management` |
| `toolboxes/knowledge_base` | `extensions/knowledge_base/toolboxes/knowledge_base` | `capabilities/knowledge_agents`, `toolboxes/knowledge_worker`, `toolboxes/helper_creation`, `toolboxes/task_documents`, `toolboxes/agent_messaging` |
| `toolboxes/knowledge_reader` | `extensions/knowledge_base/toolboxes/knowledge_reader` | `capabilities/knowledge_tools` |
| `toolboxes/knowledge_worker` | `extensions/knowledge_base/toolboxes/knowledge_worker` | `capabilities/knowledge_tools` |
| `toolboxes/local_data` | `extensions/foundation/toolboxes/local_data` | `capabilities/local_data` |
| `toolboxes/network_access` | `extensions/foundation/toolboxes/network_access` | `capabilities/network_access` |
| `toolboxes/network_management` | `extensions/foundation/toolboxes/network_management` | `capabilities/problem_handling`, `capabilities/tools_network_management` |
| `toolboxes/network_management_skill` | `extensions/foundation/toolboxes/network_management_skill` | `capabilities/network_management` |
| `toolboxes/node_creation` | `extensions/foundation/toolboxes/node_creation` | `capabilities/tools_network_management` |
| `toolboxes/node_operations` | `extensions/foundation/toolboxes/node_operations` | `capabilities/network_access` |
| `toolboxes/official_readonly` | `extensions/foundation/toolboxes/official_readonly` |  |
| `toolboxes/official_skills` | `extensions/foundation/toolboxes/official_skills` |  |
| `toolboxes/official_tools` | `extensions/foundation/toolboxes/official_tools` |  |
| `toolboxes/problem_handling` | `extensions/foundation/toolboxes/problem_handling` | `capabilities/execution_records`, `capabilities/experience`, `capabilities/problem_handling` |
| `toolboxes/problem_steps` | `extensions/foundation/toolboxes/problem_steps` | `capabilities/problem_handling` |
| `toolboxes/recovery` | `extensions/foundation/toolboxes/recovery` | `capabilities/problem_handling` |
| `toolboxes/self_repair` | `extensions/foundation/toolboxes/self_repair` | `capabilities/problem_handling` |
| `toolboxes/skill_loader` | `extensions/foundation/toolboxes/skill_loader` |  |
| `toolboxes/task_documents` | `extensions/foundation/toolboxes/task_documents` | `capabilities/task_documents` |
| `toolboxes/topology_inspection` | `extensions/foundation/toolboxes/topology_inspection` | `capabilities/network_access` |
| `toolboxes/world_operator` | `extensions/npc_world/toolboxes/world_operator` | `capabilities/world_runtime` |
| `toolboxes/world_resident` | `extensions/npc_world/toolboxes/world_resident` | `capabilities/world_runtime`, `toolboxes/network_access` |

共 110 个唯一组件。
