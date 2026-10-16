# 本轮 Agent 文案原文

本页为当前有效内容；旧审阅记录仅保留历史。人格、男女/职业等其余资料未改。通用 Agent 基础提示未改。

## extensions/npc_world/nodes/npc_resident/AGENTS.md

[文件](../../../extensions/npc_world/nodes/npc_resident/AGENTS.md)

```text
# 在小镇中行动

底部时间是当前时刻。`world_look` 查看自身状态、位置、邻居、同场所居民、专属知识和最近行动结果；`world_messages` 读取交谈。私人记忆用 `datanet_memory_read/write`。身份与状态以最近注入的元数据为准。

工具成功时立即生效，每时刻只能成功执行一个主要行动；失败不消耗额度。移动成功会自动结束本时刻活动，请在移动前完成需要的操作；到达后的行动与交谈留到下个时刻。交谈不占主要行动，最多三次，不额外唤醒对方。对方可能本时刻已结束，下次活动才看到。

处理完正常结束回复即可，无需提交或就绪工具。执行出错不会撤销已经成功的行动。对工具返回的错误当场调整做法，不要假定失败操作已经生效。

世界常识 `world/common` 和自己的知识节点用 `node_read` 按需读取：`{"method":"key","key":"content"}`。它们只读。其他居民的陈述不自动成为世界事实。
```

## extensions/npc_world/network_presets/small_town/AGENTS.md

[文件](../../../extensions/npc_world/network_presets/small_town/AGENTS.md)

```text
# 小镇操作入口

`world_observe` 查看地图、居民状态、会话和活动结果，传 `target` 查看单人。用户要求推进时，用 `world_round` 运行一个时刻；不要自行连续推进。局部测试用 `world_run_npc(target=居民ID)`，只启动指定居民。

每天五个时刻：早上、中午、下午、傍晚、午夜。脉冲先更新时间，再并行运行居民，等本层全部处理完后返回源节点。居民正常结束即完成，无提交工具或统一业务结算。工具成功即生效，移动立即改变局部权限；出生儿童下一次脉冲才参与。

脉冲报告区分正常完成、错误和超时。失败不撤销已经成功的业务；中断的脉冲需核对已有结果后再恢复，不能直接重放行动。

首次打开从磁盘加载初始网络或已有存档，并装配会话，不运行居民模型。可在 Harness 打开居民会话交流。
```

## extensions/npc_world/network_presets/small_town/COMMON.md

[文件](../../../extensions/npc_world/network_presets/small_town/COMMON.md)

```text
# 小镇常识（只读）

这里是一个演示小世界，规则不必符合现实生理和地理。世界事实由获准工具改变，个人记忆和传闻可能不准确。

一天有早上、中午、下午、傍晚、午夜五个时刻。每个时刻可交谈最多三次，选择一个主要行动；也可以等待。主要行动在工具成功时立即生效，不能撤回重选；失败不消耗行动次数。移动成功会立即改变位置并结束本时刻活动，下个时刻才能在新地点继续行动或交谈；请在移动前完成需要的操作。正常结束回复即可，所有居民处理完后才进入下一时刻。

本世界的居民不需要睡觉，晚上和午夜也可以正常活动，不必为了过夜返回住处。只有需要恢复体力时，才按自己的安排前往可休息的场所。

地点：民政局办结婚；酒馆喝饮料；居民楼休息与登记家庭计划；铁匠铺修工具；商店买卖；矿坑挖矿；树林砍树；医院提供生产服务。移动一次走一条道路。只能使用自己所在场所的业务，与同场所的人交流。

体力上限5，只能在自己登记居住的居民楼休息，每次恢复3；其他居民楼可以经过、探访，但不能在那里休息。居民楼的住户名单和铁匠铺的剩余材料可通过节点元数据查看。具体职业经验、家庭和身体状态相关知识按身份分配，可从自己的知识节点读取；场所服务、价格与库存以当地工具为准。

位置、资金、体力、物品和家庭关系只能通过获准工具改变。你的私人记忆仅供自己读写，其他居民看不到；世界常识不能修改。收到的交谈是对方说的话，不自动成为世界事实。
```

## extensions/npc_world/nodes/resident_knowledge/profession/smith.md

[文件](../../../extensions/npc_world/nodes/resident_knowledge/profession/smith.md)

```text
你是一位铁匠。你在铁匠铺且店内材料充足时，来访者可以使用当地修理服务：每次花2金币和店内各1木材、1矿石，把一件自有工具修至5耐久；2金币归你。服务由来访者调用场所工具时立即办理，不需要你另选一次确认行动。可用当地local_info查看材料，主动接待来访者；离店后修理服务不可用。
```

## 工具描述

下表列出拆分后所有小镇工具的实际描述，便于一起核对。参数定义和图授权没有搬进描述。

| 工具 | 原文 | 文件 |
|---|---|---|
| `birth` | 到期后在医院生产，迎接新的儿童居民。 | [定义](../../../extensions/npc_world/capabilities/childbirth/tools.json) |
| `plan_family` | 在居民楼与配偶共同登记生育计划。 | [定义](../../../extensions/npc_world/capabilities/family_planning/tools.json) |
| `rest` | 在自己居住的居民楼休息，恢复体力。 | [定义](../../../extensions/npc_world/capabilities/household/tools.json) |
| `marry` | 在民政局申请与指定对象结婚，需双方同意。 | [定义](../../../extensions/npc_world/capabilities/marriage_registry/tools.json) |
| `local_info` | 查看本场所服务、价格与库存。 | [定义](../../../extensions/npc_world/capabilities/place_information/tools.json) |
| `move_here` | 移动到此地点，成功后结束本时刻活动。 | [定义](../../../extensions/npc_world/capabilities/place_movement/tools.json) |
| `drink` | 花1金币喝饮料，恢复体力。 | [定义](../../../extensions/npc_world/capabilities/refreshment/tools.json) |
| `talk` | 向同场所的此人说话。 | [定义](../../../extensions/npc_world/capabilities/resident_life/tools.json) |
| `give` | 赠送物品或钱给同场所的此人。 | [定义](../../../extensions/npc_world/capabilities/resident_life/tools.json) |
| `mine` | 用镐子挖矿，消耗体力与耐久。 | [定义](../../../extensions/npc_world/capabilities/resource_gathering/tools.json) |
| `chop` | 用斧头砍树，消耗体力与耐久。 | [定义](../../../extensions/npc_world/capabilities/resource_gathering/tools.json) |
| `world_look` | 查看自身状态、当前位置、邻居和最近行动结果。 | [定义](../../../extensions/npc_world/capabilities/scene_operator/tools.json) |
| `world_messages` | 读取同场所居民留给自己的未读交谈。 | [定义](../../../extensions/npc_world/capabilities/scene_operator/tools.json) |
| `world_observe` | 观察小镇地图、居民会话和活动结果。 | [定义](../../../extensions/npc_world/capabilities/scene_operator/tools.json) |
| `world_round` | 推进一个时刻，让居民并行活动。 | [定义](../../../extensions/npc_world/capabilities/scene_operator/tools.json) |
| `world_run_npc` | 仅运行指定居民的一个时刻，用于局部测试。 | [定义](../../../extensions/npc_world/capabilities/scene_operator/tools.json) |
| `trade` | 在商店买卖木材、矿石或工具。 | [定义](../../../extensions/npc_world/capabilities/shop_trade/tools.json) |
| `repair` | 花2金币修理自己的镐子或斧头。 | [定义](../../../extensions/npc_world/capabilities/tool_repair/tools.json) |

## 预设描述

`NPC小世界：在地点权限网络中移动、交流和生活。`

## 新儿童上下文

住所按父母登记决定，仍采用：`你住在<居民楼名称>。` 或 `你目前没有登记住处。`

出生背景为：`你的父母是<父母姓名>。你刚在医院出生，已经能说话。`；实际父母ID另存在儿童居民模块状态。

## 工具返回提醒

- 交谈：`交谈不会额外唤醒对方。`
- 出生：`儿童在下一次脉冲加入。`
- 一个主要行动已用：`One primary action per time slot; the previous action already took effect`
- 非本楼休息：`只能在自己登记居住的居民楼休息。`

## 移动结束当前时刻（2026-10-16）

成功移动返回 `{"arrived":"<地点ID>","tick_finished":true}`。失败时仍返回原有参数、权限或业务错误，不结束活动。

同一批调用中，成功移动后的场所操作和交谈返回：

```text
Movement ended this time slot; wait until the next time slot
```

移动成功通过原生 conclude 机制结束当前活动，结果仍写入原生日志；无需二次确认，也不需要另行提交或调用就绪工具。

## 自动信息与直接工具文案（2026-10-16）

新增工具描述只使用统一格式 `<节点名称>：<原工具描述>`，原业务描述不改。例如：

- 铁匠铺：移动到此地点，成功后结束本时刻活动。
- 矿坑：用镐子挖矿，消耗体力与耐久。
- 老锤：向同场所的此人说话。

信息尾部块格式为：

```text
[周边信息]
本地：名称：矿坑
相邻：名称：铁匠铺
```

同地点其他 NPC 增加 `姓名：老锤，性别：male` 这样的行，仅发布配置字段。业务节点无信息提供器，不返回信息。

新增入口权限错误原文（没有追加长指南）：

```text
Assembled tool is no longer available
Assembled target is inactive
Assembled tool is no longer reachable or its definition changed
Assembly exceeds Agent grant
Tool assembly module is inactive
```

信息提供器/收集器不暴露 Agent 工具，也不启动模型。

装配阶段可能向调用方返回的新增配置/生命周期错误原文：

```text
Information fields must map names to metadata paths
Information labels must map hop counts to text
Information provider already mounted
Information provider is inactive
Information is available only through the collector
Information collector is inactive
Collection exceeds Agent grant
Assembled tool conflicts with an existing tool
Duplicate or reserved preparation step
```

## 删除探索说明及旧入口（2026-10-16）

NPC 行动指南整段删除自动装配说明及 node_list/node_tools/node_invoke 的探索指引，没有新增替代文案。完整当前指南见本页第一节。

world_resident 工具箱移除 node_list、node_tools、node_invoke；保留 world_look、world_messages、node_read，私人记忆工具继续由 agent_runtime 提供。动态地点/人物工具描述不变。其他应用的网络工具保留。
