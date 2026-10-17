# 行动值与测试客户端验证

2026-10-17。实现可配置的通用行动预算，替代“一次主要行动、三次交谈、移动后结束”的旧规则。没有修改核心节点或核心信号传播。

## 当前规则

每名 NPC 每个 tick 共用 10 点行动值，不结转。移动 3；挖矿、砍树、休息 6；交谈、交易、赠送、修理、喝饮料、家庭业务默认 1；查询与私人记忆免费。所有成功业务即时生效，业务异常在原事务内恢复状态与连接，不扣费。余额不足在业务执行前拒绝，给出所需成本、余额和未执行反馈。

七名初始 NPC 与未来儿童模板均显式装配 foundation 的 action.budget；容量、默认成本和特定成本由各自配置确定。模块只认识可信调用方传入的周期 ID，不认识 NPC、地点、时间信号或模型。预算随核心原有日志和快照保存，同一 tick 恢复不补满。

成功工具结果给出 action_budget 回执；world_look 提供余额，下一次模型请求尾部显示“行动值：剩余/总额”。余额不会更新系统提示词或反复追加历史通知。

移动者装配的 event.trigger 在成功事件后并行收集信息、装配新地点工具，汇合后更新上下文。同一节点不同命名绑定可在 Agent 图等待原生循环时运行独立准备图，同一绑定仍禁止重入；残留同步线程阻止节点再次开启图。NPC 可以继续使用新地点工具，正常结束回复后才视为本 tick 完成。其他居民现场信息的全局同步、场所共用动态文本不属于本次改动。

## 已通过的测试

| 测试文件 | 项数 | 结果 |
|---|---:|---|
| test_action_budget.py | 5 | 通过 |
| test_npc_world.py | 13 | 通过 |
| test_neighborhood_inputs.py | 6 | 通过；修正一条过时地点断言后重跑该项 |
| test_module_execution.py | 5 | 通过 |
| test_event_trigger_components.py | 5 | 通过 |
| 合计 | 34 | 通过 |

预算测试覆盖独立普通节点装配、可配置容量与成本、免费操作、周期重置、恢复同周期余额、禁用/卸载拒绝；同一 NPC 并发 12 次交谈只成功 10 次、接收端只有 10 条消息；失败移动奖励回滚、失败修理不扣费。

完整信号 Agent 循环内验证“移动3→砍树6→交谈1”，余额恰为0；继续工作被拒绝且没有副作用，查询与私人记忆仍可使用，下个 tick 恢复10。另验证移动后修理与交谈，以及儿童继承预算与移动刷新配置。

原生 Harness Mock 持久模式验证移动参数纠错、同批旧入口停用、移动后砍树（合计9）、移动后到商店卖货、正常结束、全量与增量检查点、上下文日志位置。没有付费 API 调用。

## 左侧会话列表

测试使用真实 SessionTitleService 与原生 JSONL 持久化，不再用空标题服务。为根节点和全部7名 NPC 各执行一次有界 Mock 确认，使原生 UI 通过真实 turn/start 判断为非空会话；没有伪造事件或修改会话来源。每个会话标题明确包含“Mock”。

独立测试客户端读取同一批原生日志。测试专用小插件只调用官方 sessionQuery、sessionProjectionCache 生成标题投影并通知原生侧栏，不加载本项目业务插件、不运行 NPC、不修改日志或模拟输出。通过真实客户端 API 验证8条会话的可见性、标题投影和历史读取，重复检查会复用当前客户端。用户自己的客户端不受影响。

本次记录：build/npc-action-budget-20261017-142547/，其中 sessions-manifest.json 列出8条会话，sidebar-verification.json 保存检查结果，native-logs 保存原生日志，client-home/client-user-data 为独立测试配置。测试目录被 Git 忽略。

复现（Windows、已安装 Harness、依赖已配置）：

```powershell
.venv/Scripts/python.exe scripts/run_npc_minimal_test.py --open-client
```

只检查已经打开的这次客户端：

```powershell
.venv/Scripts/python.exe scripts/open_harness_test_client.py build/npc-action-budget-20261017-142547
```

Python 客户端辅助脚本使用 PyYAML 读取 Harness 可能自动格式化的配置。首个脚本最多150秒，并有原生120秒截止。客户端标题投影、列表和历史检查不发模型请求。当前复用命令要求对应客户端仍在运行；失联时会明确报错，避免另启客户端覆盖原配置。

之前六天世界存档未做迁移；新规则装配在当前预设和儿童模板。既有世界若要采用此规则，需由宿主明确升级模块与常识资源，不能把修改预设当作自动修改旧存档。

文案原文见 [审阅](ACTION_BUDGET_TEXT_REVIEW_20261017.md)，通用模块接口见 [action_budget](../../../extensions/foundation/capabilities/action_budget/README.md)。
