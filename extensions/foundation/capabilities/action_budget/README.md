# 周期行动预算

按周期共享行动额度，支持可配置操作成本。

节点模块 `action.budget` 可装配在任意节点，无 NPC、时钟、信号或 Agent 依赖，不向 Agent 自动提供工具。配置示例：

```json
{"capacity":10,"default_cost":1,"costs":{"move_here":3,"mine":6,"chop":6,"rest":6,"local_info":0}}
```

`status(period=周期ID)` 查询当前额度；查询不改变已保存周期。`check(action=操作名,period=周期ID)` 检查成本，余额不足明确报错，不执行业务。`charge(action=操作名,period=周期ID)` 在锁内再次检查并扣费，返回 cost/capacity/spent/remaining/period。三个方法均允许第一个可选 context 参数，能作为模块执行图操作。

period 由可信调用方传入非 null JSON 周期标识，切换周期后的第一次成功扣费开始新额度，不结转；调用方应使用自己的单调周期。模块没有自行计时或猜测业务成功的逻辑。调用方应在同一事务锁内依次检查、执行业务、成功后扣费，并负责业务失败回滚；不要跨异步或外部副作用持有该锁。

config/state 使用原有核心持久化。恢复同一周期保留消耗；卸载或禁用后，缓存的方法引用也拒绝执行。

小镇在 scene_action 的现有事务中接入；七名居民和儿童模板均显式装配。余额以短尾部文本反馈，不修改系统提示词来更新余额。
