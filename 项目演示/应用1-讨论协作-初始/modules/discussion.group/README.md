# discussion.group

固定轮次的局部闭环脉冲控制器。黑板保存每轮提交，每轮开始重读上一轮；公共笔记冻结为轮初快照，所有成员并行。配置 rounds、board、notebook、output。提交或跳过结束本轮；总轮数达到后只有 Recorder 定稿。

公开操作及参数见 module.json。
