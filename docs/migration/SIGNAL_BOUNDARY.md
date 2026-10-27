# 信号独立运行，不复用 access

## 当前决定（D015）

用户撤回 D014 的共享方案。access 已恢复到 e79b09e 的父提交版本：删除 deduplicate 参数，保留原有节点去重、频道/强度、同层并发、分层屏障与遇锁等待。不再增加信号层钩子或回源参数。

共享方案尚未接入实际信号运行器，因此本次没有需要删除的共享信号运行路径。信号运行器将独立迁入 app，保留原业务；不通过改动 core 实现兼容。

## 原业务必须保留

1. 同层全部节点处理完成后，还要等待这层延后投递的通知/回应，才能进入下一层。
   - 原 python/datanet/core/signal_runtime.py:185 在节点 gather 后调用 work.drain()。
   - messages.box 通过 LayerWork 向 agents.activity.notify 投递延后工作，后者可能继续运行模型。
2. 脉冲可沿真实回边返回起点一次，作为本轮回源回执，不重新执行起点处理器。
   - 原 python/datanet/core/pulse_node.py:74 固定构造 close_loop=True。
   - 原 tests/test_core_signals.py:157 断言层次 [[clock], [a,b], [s]]、只回源一次。
3. 原信号预算、取消、故障、身份与日志/恢复协议继续迁移；访问锁定节点遵守 D001 等待解锁后的状态。

## 保留与待完成

app/runtime/signal_work.py 是先前迁入的原 LayerWork，消息模块已经使用其延后任务接口，保留供独立信号运行器使用。私人记忆、消息箱、私信中继与已验证的 DSH/RPC/JSONL 恢复链路不受本次撤回影响。

独立信号运行器、脉冲接线及三个完整应用（小镇先一天）的最终验收仍未完成。D014 的 7 项专属重访测试随参数撤回；277 项是该历史阶段的结果，不作为当前测试数。
