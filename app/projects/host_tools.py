"""把宿主工具装配成真正的 CallableTool；取得后直接调用引用。"""

from copy import deepcopy
from hashlib import sha256

from app.runtime import ports
from app.runtime.requester import requester_id
from domain.core import CallableTool


def host_tool_name(node_id, reference):
    return "ext_" + sha256((node_id + "\0" + reference).encode()).hexdigest()[:24]


class HostTools:
    def __init__(self, tables, backend, official, definitions, *, instantiate=None):
        self.tables = tables
        self.backend = backend
        self.official = official
        self.instantiate = instantiate
        self.definitions = {"harness:" + item["name"]:item for item in definitions}
        self.definitions.update({"runtime:" + item["name"]:item for item in ports.DEFINITIONS})
        if instantiate is not None:
            from app.templates.service import DEFINITION
            self.definitions["templates:instantiate"]=DEFINITION

    def register(self, properties):
        for node_id, metadata in properties.items():
            for offer in metadata.get("offered_ports", []):
                reference = offer["ref"]
                name = host_tool_name(node_id, reference)
                definition = self.definitions[reference]
                self.tables.tool_types[name] = (
                    lambda node, record, reference=reference:
                    self.make(node.info.node_id, reference))

    def make(self, node_id, reference, definition=None):
        definition = self.definitions[reference] if definition is None else definition
        provider, operation = reference.split(":", 1)
        async def execute(**arguments):
            actor = requester_id.get() or node_id
            if provider == "runtime":
                return await ports.execute(self.backend(), actor, operation, arguments)
            if provider == "templates":return await self.instantiate(actor,**arguments)
            return await self.official(actor, operation, arguments)
        tool=CallableTool(host_tool_name(node_id, reference), execute,
                          node_id + " · " + definition["description"], deepcopy(definition["parameters"]))
        tool._host_ref=reference
        return tool

    def ensure(self,network,properties):
        self.register(properties)
        for node in network:
            offers={item['ref'] for item in properties.get(node.info.node_id,{}).get('offered_ports',[])}
            for tool in tuple(node.tools.members):
                if getattr(tool,'_host_ref',None) is not None and tool._host_ref not in offers:node.remove(tool)
            for reference in offers:
                name=host_tool_name(node.info.node_id,reference)
                if not any(tool.name==name for tool in node.tools):node.install(self.make(node.info.node_id,reference))

