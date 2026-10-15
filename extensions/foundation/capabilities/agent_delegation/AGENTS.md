# 委托任务
datanet_call_agent 接受委托后立即返回 delegation_id；同一 Agent 按提交顺序逐个执行任务。
完成或失败后，框架把结果送回发起者：运行中插话，空闲时唤醒。
需要结果才能继续时，用 datanet_wait_agent 等待该 delegation_id；wait=false 只查看状态。
