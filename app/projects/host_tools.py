"""把宿主工具装配成真正的 CallableTool；取得后直接调用引用。"""

from copy import deepcopy
from hashlib import sha256

from app.runtime import ports
from app.runtime.requester import requester_id
from domain.core import CallableTool


def host_tool_name(node_id, reference):
    return "ext_" + sha256((node_id + "\0" + reference).encode()).hexdigest()[:24]


class HostTools:
    def __init__(self, tables, backend, official, definitions):
        self.tables = tables
        self.backend = backend
        self.official = official
        self.definitions = {"harness:" + item["name"]:item for item in definitions}
        self.definitions.update({"runtime:" + item["name"]:item for item in ports.DEFINITIONS})

    def register(self, properties):
        for node_id, metadata in properties.items():
            for offer in metadata.get("offered_ports", []):
                reference = offer["ref"]
                name = host_tool_name(node_id, reference)
                definition = self.definitions[reference]
                self.tables.tool_types[name] = (
                    lambda node, record, reference=reference, definition=definition:
                    self.make(node.info.node_id, reference, definition))

    def make(self, node_id, reference, definition=None):
        definition = self.definitions[reference] if definition is None else definition
        provider, operation = reference.split(":", 1)
        async def execute(**arguments):
            actor = requester_id.get() or node_id
            if provider == "runtime":
                return await ports.execute(self.backend(), actor, operation, arguments)
            return await self.official(actor, operation, arguments)
        return CallableTool(host_tool_name(node_id, reference), execute,
                            node_id + " · " + definition["description"], deepcopy(definition["parameters"]))
