"""应用编排器：只负责阶段衔接，下游业务仍由各模块执行。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller
from app.transactions.locks import require_transaction_node
from domain.core import CallableTool, Module, access
from . import operations
from .state import _Fail, _state, _error, _instance_lock

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class Target:
    def __init__(self, module, channels):
        self._access_origin = module._access_origin
        self.channels = channels
        self.strength = module.strength

    @access()
    async def call(self, node, target, module_id, operation, parameters):
        if node.info.node_id != target:
            return None
        module = node.modules.get(module_id)
        if module is None:
            raise _Fail(f"节点 {target} 未安装模块 {module_id}")
        with as_caller(self._access_origin.info.node_id):
            return await getattr(module, operation)(**parameters)


class AppCoordinatorModule(Module):
    def __init__(self, emit, config=None, state=None, **access_settings):
        super().__init__("app.coordinator.entry", **access_settings)
        self.emit = emit
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec["id"], getattr(self, spec["operation"]),
                                         spec["description"], deepcopy(spec["parameters"])))

    def _bind(self, node):
        super()._bind(node)
        source_id = sha256((node.info.node_id + "\0" + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = "mod_" + sha256((source_id + "\0" + spec["id"]).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + " · " + spec["name"] + " · " + spec["description"]

    async def downstream(self, field, module_id, operation, parameters, channels):
        target = self.config.get(field)
        if not isinstance(target, str) or not target.strip():
            raise _Fail(f"未配置{field}，无法找到下游节点")
        results = await Target(self, channels).call(target, module_id, operation, parameters)
        if target not in results:
            raise _Fail(f"下游节点不可达：{target}")
        return results[target]

    async def _call(self, operation, parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        require_transaction_node(node.info.node_id)
        _state(self)
        async def run():
            if operation in ("start", "stop"):
                return await getattr(operations, "_" + operation)(self, parameters)
            if operation == "integrate":
                return await operations._integrate(self, node, parameters)
            return await getattr(operations, "_" + operation)(self)
        try:
            if operation == "status":
                return await run()
            async with _instance_lock(self):
                return await run()
        except _Fail as error:
            _error(self.state, operation, str(error))
            raise
        except Exception as error:
            message = f"操作失败：{error}"
            _error(self.state, operation, message)
            raise _Fail(message) from error

    async def start(self, task, rounds=None, key=None):
        return await self._call("start", {"task":task, "rounds":rounds, "key":key})

    async def handoff(self):
        return await self._call("handoff", {})

    async def integrate(self, reason=None):
        return await self._call("integrate", {"reason":reason})

    async def promote(self):
        return await self._call("promote", {})

    async def status(self):
        return await self._call("status", {})

    async def stop(self, reason=None):
        return await self._call("stop", {"reason":reason})
