# 概率事件

将 `probability.events` 装配到负责行动的节点。config.events 每项含 id、actions、probability、max_occurrences、text，可选 effects。概率范围 0～1；max_occurrences 为非负整数，null 表示无限。每项独立判断，次数是成功触发上限，不是权重。

调用 `draw(action_id, action, apply_effects)`，action_id 必须是同一成功行动的稳定标识。调用方必须在自身业务事务内调用，负责将效果应用与状态一起提交/回滚；传入的回调处理业务效果，组件不认识金币、NPC 或地点。重复 action_id 仅返回已存结果，不再次应用效果。组件不提供 Agent 工具或独立 RPC，也不自动监听查询。

state 保存随机种子、成功计数和每次抽取结果；同一节点实例的次数上限由所有调用者共享。以种子、行动 ID、事件 ID 计算独立抽取值，重试不改变结果。耗尽的事件不改变其他事件概率。由调用方选择将返回文本附到本次工具结果；不广播、不唤醒模型。

NPC 应用在既有 scene_action 事务中调用本模块，接受 `{item,quantity}` 的正数奖励，通过既有物品操作落实。失败行动、失败效果一起回滚。移动成功返回 destination 和可选 events 后正常结束本时刻。
