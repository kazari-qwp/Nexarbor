# 本次 Agent 文档与工具描述原文

以下均为本次新增；原有 Agent 提示词和描述未改。foundation/network_access 的变更仅涉及执行上下文。

## 文档与配置

- [network_presets/small_town/AGENTS.md](../../../extensions/npc_world/network_presets/small_town/AGENTS.md)
- [network_presets/small_town/COMMON.md](../../../extensions/npc_world/network_presets/small_town/COMMON.md)
- [network_presets/small_town/prompt.md](../../../extensions/npc_world/network_presets/small_town/prompt.md)
- [nodes/npc_child/prompt.md](../../../extensions/npc_world/nodes/npc_child/prompt.md)
- [nodes/npc_resident/AGENTS.md](../../../extensions/npc_world/nodes/npc_resident/AGENTS.md)
- [nodes/npc_resident/prompt.md](../../../extensions/npc_world/nodes/npc_resident/prompt.md)
- [地图、初始目标与物品配置](../../../extensions/npc_world/network_presets/small_town/town.json)

## 工具描述

| 工具 | 描述原文 |
|---|---|
| `world_look` | 查看自己的状态、当前场所、邻居和上次结算。 |
| `world_messages` | 读取同场所居民留给自己的未读交谈。 |
| `world_submit` | 提交本时刻的行动计划；未选行动则等待。 |
| `world_observe` | 观察小镇地图、居民会话和最近结算。 |
| `world_round` | 开启、结算或运行一个小镇时刻；run会并行启动所有居民。 |
| `world_run_npc` | 仅运行指定居民本时刻的行动，供局部观察与测试。 |
| `move_here` | 计划移动到此地点。 |
| `talk` | 向同场所的此人说话。 |
| `give` | 计划赠送物品或钱给同场所的此人。 |
| `marry` | 在民政局申请与指定对象结婚，需双方同意。 |
| `plan_family` | 在居民楼与配偶共同登记生育计划。 |
| `rest` | 计划在此休息恢复体力。 |
| `drink` | 计划花1金币喝饮料，恢复体力。 |
| `repair` | 计划花2金币修理自己的镐子或斧头。 |
| `trade` | 计划在商店买卖木材、矿石或工具。 |
| `mine` | 计划用镐子挖矿，消耗体力与耐久。 |
| `chop` | 计划用斧头砍树，消耗体力与耐久。 |
| `birth` | 到期后在医院生产，迎接新的儿童居民。 |
| `local_info` | 查看本场所服务、价格与库存。 |

## 预设与工具箱描述

- `network_presets/small_town/component.json`：NPC小世界：在地点权限网络中移动、交流和生活，按五个时刻统一结算。
- `toolboxes/world_operator/box.json`：小世界观察与逐时刻推进。
- `toolboxes/world_resident/box.json`：在当前地点行动、交流并提交本时刻。
