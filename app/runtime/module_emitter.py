"""宿主授予模块从本节点发布信号的端口；不等待信号完成。"""

from domain.signals import Signal
from .requester import as_requester
from .signal_authority import signal_authority


def emit_module_signal(runtime, node, *, access_strength, **parameters):
    node_id = node.info.node_id
    with as_requester(node_id), signal_authority(node_id, access_strength):
        return runtime.emit(Signal(origin=node_id, **parameters))
