# 周期存档触发器

runtime.periodic_checkpoint 按收到的不同信号计数，每 every 次（默认 5）调用显式装配的 runtime:checkpoint。计数与信号强度、角色人数和日历无关；不处理时间文本。

需要 tick 接收授权以及 runtime.checkpoint 工具授权。read 查看 count/pending，flush 重试待办存档。小镇节点 aggregation 配为 max；节点仍每波只执行一次，模块的业务间隔不改变信号继续传播。
