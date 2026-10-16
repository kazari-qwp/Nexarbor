# NPC脉冲最小接线（2026-10-16）

用户要求：真实NPC应用接入核心，验证 pulse -> 时间常驻文本 -> NPC -> pulse；NPC在地点内沿权限调用场所业务，正常结束后自动登记完成，无submit工具。优先复用组件，不运行全世界付费Agent。只改E成品目录。

计划：迁移NPC接口到v4；world_state创建核心PulseNode和foundation resident文本world/time，公有world.tick写边串起脉冲环，所有NPC私有只读时间边，地图边空频道。world_runtime在独立循环上绑定时钟和NPC处理器，宿主原生run正常完成后冻结行动；cycle_complete结算。删除手工提交/就绪屏障和催促。复用agent_runtime与text尾部注入，不迁移前两个应用。

Native正确性：whenIdle后还须检查本次turn/end.reason.kind==completed，错误/取消不自动算完成。离线测试用真应用/图工具；再用真实Harness原生循环+Mock模型验证完整桥接，必要时做单NPC付费测试：请求<=8，输出4096，单NPC<=90秒，总<=180秒，禁止全世界run。只重启已核实属于本任务的客户端。

验收：时间先更新且在每个NPC请求尾部；无时间节点工具/写权限/submit；地点工具真实调用并结算资源；信号layers=[time],[NPC],[pulse]且returned；道路未被脉冲访问；错误/超时不算正常就绪；重启恢复；纯核心回归。Agent文档与描述原文交付。五小时剩余低于8%保存暂停，不使用重置卡。

完成：NPC组件已迁移到v4，闭环执行和自动完成已实现。NPC本地5项、核心19项和原生Harness+Mock均通过。付费单NPC通过，4次NPC+2次根请求，脉冲约7.17秒，其余5人0调用；完整世界未运行。测试副本旧核心同步问题已修正；超时清理收紧为明确测试session ID。详见应用VALIDATION及AGENT_TEXT_REVIEW。

附：旧组件解析检查3通过/2失败，原因分别为类型枚举缺pulse、project_root仍旧格式；按既定范围不迁移。
