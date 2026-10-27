# 三个实际应用入口与无连线依赖核对

来源为实际 profile.project → nexarbor.json.activeNetwork → 项目网络及节点分文件，不把 configs 中同名旧 network.json 当成当前运行入口。

| Profile | 实际项目 | 当前节点数 | 无连线跨节点依赖 |
| --- | --- | --- | --- |
| fixed_groups_v3 | projects/discussion-collaboration | 15 | 未发现。跨节点 prepare 已有业务边；collab.participant 与整合器在同一节点 |
| knowledge_v3 | projects/knowledge-archive | 4 | 未发现。prepare 都在本节点；knowledge.tools 与 documents.tasks 在 root 同节点 |
| npc_town_v3 | resources/examples/npc-town | 59 | 7 个 NPC 的 tool_sources 指向所属工具亚节点；这些亚节点无入边，旧 _accessible 以 same_family 放行，并用 use_parent_links 读取 NPC 出边 |

小镇 family.household 的两处 local.call 明确 target=ctx.node_id，是同节点模块互调，不需要 family 权限。小镇 prepare 也全部在本节点。实际无连线跨节点依赖位于工具来源装配。

## 按新设计迁移

- 管理通过显式管理员频道与真实连接；不增归属特权或 family 模式。
- 将小镇工具发现模块直接安装到对应 NPC 节点，符合“Agent + 工具发现 + 上下文组装器”的新组合。保留模块自身频道与强度；起点不施加偏置，所以可保持原工具亚节点借用 NPC 出边时的传播预算。
- 取消旧工具来源的亲缘跳转及该处 use_parent_links 依赖。无引用的空通信亚节点等后续核对实际引用后再删除，不能仅凭名称推断无用。
- 当前应用未使用的旧测试能力，不作为扩展 core 的理由；仍需审查其职责、实际调用方和可替代位置。
- 旧验收脚本存在历史英文节点 ID，而当前项目已使用不同节点配置。迁移测试时以实际项目入口适配 fixture/定位，保留讨论、协作、保存重开和小镇一天 5 tick 的业务断言，不把旧配置替换成简化应用。

详细机器可核对数据：evidence/2026-10-27-active-app-routing.json。
