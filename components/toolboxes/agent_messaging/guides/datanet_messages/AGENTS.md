send_message 向框架列出的管理者或直接被管理 Agent 发信，填 target 和 content。对方工作时插话，空闲时唤醒；返回 accepted 表示已投递。
收到消息或回复时，使用消息中的 reply_tool 回复，参数只有 content。此工具绑定原发送者，调用一次后失效。每次收到新消息会开放新的回复入口。
需要对方执行任务时使用 datanet_call_agent；讨论发言仍提交黑板。
