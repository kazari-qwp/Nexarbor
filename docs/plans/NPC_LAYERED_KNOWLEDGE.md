# NPC分层身份与知识

用户授权：按性别、职业和状态拆开描述/知识，暂用系统提示词承载；NPC按职业连接独立职业知识文本，通用模板不再包含怀孕到院等专属信息。只改E成品目录，不运行完整世界真实Agent。

实现：新增纯配置/文档节点组件resident_knowledge，复用foundation普通文本、私有只读边、network_access与agent_runtime.update_prompt。资料目录用when条件匹配角色字段及派生life_stage/pregnant/is_parent；gender与can_gestate独立。短描述和职业说明按关联节点装配系统提示词，家庭资料按需node_read；孕期资料仅当前孕者，生育后撤去连接与当前提示片段。已有历史仍保留。私人记忆独立不覆盖。

NPC业务组件负责装配与刷新，核心/适配层不改，不增加Agent工具。移动重建接口保留身份知识边；新生儿和恢复后重新匹配。只有prompt确实变化才调用原生更新，沿用Harness in-history。最小本地测试验证不同身份、私有权限、地点/职业分离、怀孕/出生增减、恢复与不重复更新；原生Mock验证实际请求提示。无需再花付费API。

交付：本次改过的所有Agent文案链接/描述原文，最小测试结果，本地commit。

完成：新增13份身份/知识文本及配置组件；通用指南与常识已删去专属孕期/职业细节。复用普通文本和私有读边，不增加工具，不修改核心或适配层。NPC7项与原生Harness+Mock测试通过，未使用付费API。原文与所有文件链接见docs/applications/npc_world/LAYERED_KNOWLEDGE_REVIEW.md。
