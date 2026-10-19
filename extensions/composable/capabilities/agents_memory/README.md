# 私人记忆

仅装在 Agent 上，只允许本人记住和回忆。相同记忆键重试去重，不同内容不能覆写相同键。max_memories 限制保留数量。记忆不会自动写进 system_prompt、context 或 tail；是否检索由角色决定。

从 agents.context 中拆出的单一职责组件，迁移保留 memories。
