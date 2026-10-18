import math

from datanet.core.module_protocol import ComponentResult

MAX_RECEIPTS = 200


def _window_size(ctx):
    raw = ctx.config.get("window_size", 3)
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 1000:
        return 3
    return raw


def _list_state(ctx, name):
    value = ctx.state.get(name)
    if isinstance(value, list):
        return value
    if value is None:
        value = []
    else:
        value = list(value)
    ctx.state[name] = value
    return value


def _keep_recent(values, limit):
    if len(values) > limit:
        del values[: len(values) - limit]


def _stats(values, window_size):
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "window_size": window_size,
        }
    return {
        "count": count,
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / count,
        "window_size": window_size,
    }


def _is_finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="不支持的请求类型")

    operation = activation.operation
    window_size = _window_size(ctx)
    window = _list_state(ctx, "window")
    receipts = _list_state(ctx, "receipts")

    # 配置容量可能在运行中调小，此时只保留最近的值，避免状态超出声明上限。
    _keep_recent(window, window_size)
    _keep_recent(receipts, MAX_RECEIPTS)

    if operation == "push":
        parameters = activation.parameters
        value = parameters.get("value")
        if not _is_finite_number(value):
            return ComponentResult(
                status="error",
                error="数值必须是有限数字，不能是 NaN 或 Infinity",
            )

        key = parameters.get("key")
        if key is not None:
            if not isinstance(key, str) or not key:
                return ComponentResult(status="error", error="请求键必须是非空字符串")
            for receipt in receipts:
                if receipt.get("key") != key:
                    continue
                if receipt.get("value") == value:
                    return ComponentResult(
                        data={**_stats(window, window_size), "duplicate": True}
                    )
                return ComponentResult(
                    status="error",
                    error="相同请求键已用于不同数值，不能重复提交不同值",
                )
            receipts.append({"key": key, "value": value})
            _keep_recent(receipts, MAX_RECEIPTS)

        window.append(value)
        _keep_recent(window, window_size)
        ctx.state["window"] = window
        ctx.state["receipts"] = receipts
        return ComponentResult(data={**_stats(window, window_size), "duplicate": False})

    if operation == "read":
        return ComponentResult(
            data={**_stats(window, window_size), "values": list(window)}
        )

    return ComponentResult(status="error", error="不支持的操作")
