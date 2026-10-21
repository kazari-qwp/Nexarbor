# 信号驱动的角色活动

角色活动采用明确的本地状态机，不申请节点事务：

1. 在任何 await 前核验活动键、同步登记 running。同一节点不能同时启动两轮模型；
2. 新活动通过本节点记录仓设置预算，后续回应沿用剩余预算；
3. 准备当前现场，再调用显式授权的 runtime:agent_run；
4. 运行中收到 notify 只置 pending 标记，模型返回后合并处理；已结束则继续同一活动键；
5. 同步登记 completed，每键仅累计完成一次。失败保留 failed，不自动重放。

同步状态转换不跨 await 暴露半成品。等待模型时可信端口让出访问占用，返回业务代码前重新通过门禁。移动、交易自己保护确实不能被看见的中间状态，活动模块不锁住整轮。

信号以 signal_id 为活动键；公开 activate 接收 `{"key":"活动键"}`，使用 tick 频道。同一完成键返回 duplicate；运行中或失败键拒绝重放。不同键也不能在本节点已有活动运行时重叠启动。

notify 仅接受当前信号的活动键，使用 activity 频道，不作为 Agent 工具提供。未初次激活的节点不会凭通知开始活动，初次准备上下文会读取已有便条。运行中通知合并，已完成则用剩余预算回应。核心 post 将后续访问纳入本信号层；发送者不等待对方整轮，下一层等本层所有工作结束。

每键最多初始运行一次加 max_reactions 次后续回应（默认8，允许0至32），剩余行动点不足则跳过后续运行，避免无限对话。通知不重置预算，不重复累计完成次数。

## 装配与配置

仅支持 agent，只依赖 records.store；上下文由执行器显式 prepare 配置，不依赖 agents.context。节点需显式提供 runtime:agent_run，频道 runtime.agent；活动模块需 records、self、runtime.agent 授权。消息箱配置 notify_activity:true 时另需 activity 频道。

| 字段 | 默认值 | 说明 |
|---|---|---|
| signal_channels | ["tick"] | 新活动的信号频道 |
| budget_field / budget | ap / 10 | 新活动写入预算，后续回应不重置 |
| prompt | 空字符串 | 初次活动的提示 |
| enabled | false | 应用明确启用才调用模型 |
| max_reactions | 8 | 同一活动键后续模型运行次数上限 |

状态 activities 保留最近200键，记录 status、runs、pending、completed_count 和可选错误；completed_total 只统计首次完成。示例默认关闭，直接装配不产生付费调用。

当前状态机由维护者重新设计，原 Agent 制作记录代表历史产物。复盘见基础概念 Skill 的 references/lessons/03-locks.md。
