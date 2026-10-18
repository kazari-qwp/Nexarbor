from collections.abc import Mapping

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

SIGNAL_NAME = "metadata.refresh"
READ_OPERATION = "read"


def _configured_fields(config):
    """读取本实例配置中的字段映射，缺失时按空对象处理。"""
    fields = config.get("fields", {})
    if not isinstance(fields, Mapping):
        raise ValueError("配置项 fields 必须是对象。")
    return fields


def _publish_and_return(ctx, fields):
    """把冻结字段转成可发布的 JSON 副本，并在本节点发布一次。"""
    published = thaw(fields)
    ctx.publish_metadata(published)
    return ComponentResult(data={"fields": published})


def _signal_channels(activation):
    """读取真实 Signal 的频道集合；缺失时返回空元组。"""
    signal = activation.signal
    if signal is None:
        return ()
    channels = getattr(signal, "channels", ())
    if not isinstance(channels, (list, tuple)):
        return ()
    return tuple(channels)


async def execute(ctx, activation):
    try:
        fields = _configured_fields(ctx.config)
    except ValueError as error:
        return ComponentResult(status="error", error=str(error))

    if activation.kind == "signal":
        channels = _signal_channels(activation)
        if SIGNAL_NAME not in channels:
            shown = "、".join(str(channel) for channel in channels) or "未提供"
            return ComponentResult(
                status="error",
                error="不支持的信号频道：%s；本组件只响应 %s。" % (shown, SIGNAL_NAME),
            )
        return _publish_and_return(ctx, fields)

    if activation.kind != "access":
        return ComponentResult(
            status="error",
            error="不支持的激活方式：%s" % (activation.kind or "未提供"),
        )

    if activation.operation != READ_OPERATION:
        return ComponentResult(
            status="error",
            error="不支持的操作：%s" % (activation.operation or "未提供"),
        )

    return _publish_and_return(ctx, fields)
