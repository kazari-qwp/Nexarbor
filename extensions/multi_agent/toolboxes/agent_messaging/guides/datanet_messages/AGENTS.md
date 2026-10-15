需要查可主动联系的对象时，用 datanet_contacts_channel 查看通讯录。用 datanet_send_message 发信，填 target 和 content；运行中插话，空闲时唤醒，accepted 表示已投递。
message_type=work_order 表示需要答复的工单（默认）；message_type=reply 表示可不回复的信息。收到消息后可用其中的 reply_tool 回复，参数只有 content，调用一次后失效，发出的消息自动归为回复。
尾部的“存在待处理工单。”表示尚有工单未结束；“存在未读回复。”表示还有回复未读。用 datanet_pending_messages 查看，读取后未读提醒消失，回复工具仍可使用。无需继续处理的消息可用 action=close、message_id 结束。回复前的“此为回复，可以不回。”表示无需确认收到。
需要对方执行委托任务时使用 datanet_call_agent；讨论发言提交黑板。
