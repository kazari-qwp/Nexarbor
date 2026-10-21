# discussion.member

讨论成员的原生执行桥。监听 discussion.round。每轮读取黑板新发言（排除自己的上一轮发言），尾部携带轮数/总轮数、请求次数/10和轮初公共笔记。Recorder 可更新≤200字公共笔记及输出板。submit_round/skip_round 立即结束本轮。

公开操作及参数见 module.json。
