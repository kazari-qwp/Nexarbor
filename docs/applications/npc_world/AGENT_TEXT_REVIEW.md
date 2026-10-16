> 历史审阅记录：本轮显式节点模块重构后的有效文案与路径见 [NODE_MODULE_REVIEW.md](NODE_MODULE_REVIEW.md)，以下旧结算说明不再使用。

最新住所、休息权限及场所元数据文案见[本轮完整原文](HOUSING_REVIEW.md)。

当前新增文案以[四类输入与人格审阅](CONTEXT_ASSEMBLY_REVIEW.md)为准。下列历次记录中，旧match_prompts工具已删除，旧常驻文本尾部机制已被装配器替代。

# 本次 Agent 文档与工具描述原文

本表为当前 Agent 可见文档与描述。2026-10-16脉冲接线改动了居民/儿童提示词、居民/操作指南、只读常识、world_round/world_run_npc和居民工具箱描述；移除了world_submit。

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
| `world_observe` | 观察小镇地图、居民会话和最近结算。 |
| `world_round` | 运行一个小镇时刻，居民并行活动后自动结算。 |
| `world_run_npc` | 仅运行指定居民的一个时刻，正常结束后自动结算。 |
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
- `toolboxes/world_resident/box.json`：在当前地点行动与交流。

地点业务登记后的共同返回提示：

> 这是行动计划；本次活动结束时自动确定，随后统一结算。

共享执行器的非正常结束诊断（由框架返回，非角色提示词）：`Host did not confirm normal Agent completion`；Harness无本次结束事件时报 `AGENT_EXECUTION_INCOMPLETE: No turn completion was recorded`，非正常结束时报 `AGENT_EXECUTION_NOT_COMPLETED: <kind> <error.message>`。

## 分层身份知识更新

职业和孕期说明已从通用文档分离。全部新增原文、逐文件链接与匹配说明见[分层身份知识审阅](LAYERED_KNOWLEDGE_REVIEW.md)。本轮工具描述未改。

## 频道响应与统一元数据更新

本轮新增match_prompts描述：**按自己的身份元数据补充尚未加载的提示文档。** 居民指南、孕期文档、条件包装和最新元数据提示原文与地址见[审阅清单](LAYERED_KNOWLEDGE_REVIEW.md)。身份知识不再装入整份角色系统提示。

## 无需睡眠的世界规则（2026-10-16）

[世界常识](../../../extensions/npc_world/network_presets/small_town/COMMON.md)新增原文：

> 本世界的居民不需要睡觉，晚上和午夜也可以正常活动，不必为了过夜返回住处。只有需要恢复体力时，才按自己的安排前往可休息的场所。
