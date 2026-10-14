需要查可主动联系的对象时，用 datanet_contacts_channel 查看最新通讯录。用 datanet_send_message 发信，填 target 和 content；对方工作时插话，空闲时唤醒，返回 accepted 表示已投递。
收到消息或回复时，可直接使用消息中的 reply_tool 回复，参数只有 content，调用一次后失效。尾部出现“存在待回复消息。”时，可用 datanet_pending_messages 查看消息正文、发送者、回复工具和失效时间。
需要对方执行任务时使用 datanet_call_agent；讨论发言仍提交黑板。
