"""时钟与计数触发器：把信号安全地转换为可读的轮次时钟。"""

from datanet.core.module_protocol import ComponentResult

_DEFAULT_LABELS = ("清晨", "上午", "下午", "傍晚", "夜晚")
_SEEN_LIMIT = 200
_CHECKPOINT_CHANNEL = "runtime.checkpoint"


def _labels(config):
    labels = config.get("labels") or _DEFAULT_LABELS
    result = [str(label) for label in labels if str(label)]
    return result or list(_DEFAULT_LABELS)


def _clock(config, tick):
    """返回公开时钟；初始计数 0 视为第一天的第一个时刻。"""
    labels = _labels(config)
    tick = max(0, int(tick))
    if tick == 0:
        day = 1
        slot = labels[0]
    else:
        day = (tick - 1) // len(labels) + 1
        slot = labels[(tick - 1) % len(labels)]
    return {"tick": tick, "day": day, "slot": slot}


def _signal_id(activation):
    signal = getattr(activation, "signal", None)
    if signal is None:
        return None
    if isinstance(signal, dict):
        value = signal.get("signal_id")
    else:
        value = getattr(signal, "signal_id", None)
    if value is None:
        return None
    value = str(value)
    return value or None


def _node_result_status(result):
    if isinstance(result, dict):
        return result.get("status")
    return getattr(result, "status", None)


async def _write_text(ctx, text):
    result = ctx.write("content", text)
    if hasattr(result, "__await__"):
        result = await result
    status = _node_result_status(result)
    if status != "ok":
        errors = getattr(result, "errors", None) or getattr(result, "error", None)
        detail = "；".join(str(item) for item in errors) if isinstance(errors, (list, tuple)) else errors
        raise RuntimeError("写入本地文本失败" + ("：" + detail if detail else ""))


async def _run_pending_checkpoint(ctx):
    """在节点锁外使用本节点自己的授权重试待办存档。"""
    if not ctx.state.get("pending_checkpoint", False):
        return False
    await ctx.network.invoke(
        ctx.node_id,
        "runtime:checkpoint",
        {"full": True},
        channels=[_CHECKPOINT_CHANNEL],
    )
    async with ctx.network.lock_nodes([ctx.node_id], timeout=10):
        ctx.state["pending_checkpoint"] = False
    return True


async def _on_signal(ctx, activation):
    config = ctx.config
    checkpoint_every = int(config.get("checkpoint_every", 0) or 0)
    signal_id = _signal_id(activation)
    clock = None
    checkpoint_due = False

    async with ctx.network.lock_nodes([ctx.node_id], timeout=10):
        seen = [str(item) for item in (ctx.state.get("seen") or ())]
        if signal_id is not None and signal_id in seen:
            tick = int(ctx.state.get("tick", config.get("initial_tick", 0) or 0))
            return ComponentResult(data=_clock(config, tick))

        tick = int(ctx.state.get("tick", config.get("initial_tick", 0) or 0)) + 1
        if signal_id is not None:
            seen = (seen + [signal_id])[-_SEEN_LIMIT:]
        ctx.state["tick"] = tick
        ctx.state["seen"] = seen
        clock = _clock(config, tick)
        ctx.publish_metadata(dict(clock))

        if config.get("write_text", False):
            await _write_text(ctx, ctx.config.get('text_template', '第{day}天 {slot}').format(**clock))

        if checkpoint_every > 0 and tick % checkpoint_every == 0:
            # 先登记待办，确保调用失败时状态仍然保留。
            ctx.state["pending_checkpoint"] = True
            checkpoint_due = True

    if checkpoint_due:
        # 已释放节点锁；调用失败时让异常穿出信号分支，由传播器标记失败。
        await _run_pending_checkpoint(ctx)

    return ComponentResult(data=clock)


async def execute(ctx, activation):
    if activation.kind == "access":
        if activation.operation == "read":
            tick = int(ctx.state.get("tick", ctx.config.get("initial_tick", 0) or 0))
            return ComponentResult(data=_clock(ctx.config, tick))
        if activation.operation == "flush":
            checkpointed = await _run_pending_checkpoint(ctx)
            tick = int(ctx.state.get("tick", ctx.config.get("initial_tick", 0) or 0))
            return ComponentResult(
                data={"checkpointed": checkpointed, "tick": tick}
            )
        return ComponentResult(status="error", error="不支持的访问操作")

    if activation.kind == "signal":
        return await _on_signal(ctx, activation)

    return ComponentResult(status="error", error="不支持的请求类型")
