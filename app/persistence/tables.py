"""模块配置和工具箱的配置重建；函数实现由应用注册，不序列化 Python 回调。"""

from copy import deepcopy

from domain.core import Tools
from modules.context_assembler import ContextAssemblerModule
from modules.tool_discovery import ToolDiscoveryModule


class ModuleTables:
    def __init__(self, *, read_text=None):
        self.module_types = {
            "tool_discovery": lambda record: ToolDiscoveryModule(record["channels"], record["strength"],
                                                               channel_mode=record["channel_mode"]),
            "context.assembler": lambda record: ContextAssemblerModule(record.get("config"), read_text=read_text,
                **{field:record[field] for field in ("channels", "strength", "channel_mode") if field in record}),
        }
        self.tool_types = {name: (lambda node, record, name=name: next(tool for tool in node.tools if tool.name == name))
                           for name in ("memory_query", "memory_modify", "memory_append")}

    def encode(self, node):
        modules = list(node.modules)
        records = []
        references = {node.modules.tools: {"modules": True}}
        for module in modules:
            if module.module_id not in self.module_types and not getattr(module,"unavailable_reason",None):
                raise ValueError("尚未登记的模块：" + module.module_id)
            references[module.tools] = {"module": module.module_id}
            for tool in module.tools:
                references[tool] = {"factory_module": module.module_id}
            records.append(dict(module_id=module.module_id, description=module.description,
                                channels=list(module.channels), strength=module.strength, channel_mode=module.channel_mode,
                                modules=getattr(module,"saved_dependencies",[dependency.module_id for dependency in module.modules]),
                                **{field: deepcopy(getattr(module, field)) for field in ("config", "state", "published")
                                   if hasattr(module, field)}))

        groups = {}

        def encode_group(group):
            if group in groups:
                return {"group_ref": groups[group]}
            key = groups[group] = len(groups)
            return {"group": key, "members": [encode(member) for member in group.members]}

        def encode(item):
            if isinstance(item, Tools):
                return references[item] if item in references else encode_group(item)
            function = {} if item.name in self.tool_types else references.get(item, {})
            if not function and item.name not in self.tool_types:
                raise ValueError("尚未登记的工具实现：" + item.name)
            return dict(tool=item.name, description=item.description, parameters=deepcopy(item.parameters),
                        modules=[dependency.module_id for dependency in item.modules], **function,
                        **({"host_ref":item._host_ref} if hasattr(item,"_host_ref") else {}))

        for module, record in zip(modules, records):
            record["tools"] = encode_group(module.tools)
        return dict(modules=records, tools=encode_group(node.tools))

    def restore(self, node, record):
        if record is None:
            return
        initial_tools = {tool.name: tool for tool in node.tools}
        loader = getattr(self, "restore_modules", None)
        modules = loader(node, record["modules"]) if loader else {}
        for spec in record["modules"]:
            module = modules[spec["module_id"]] if loader else self.module_types[spec["module_id"]](spec)
            for field in ("description", "strength", "channel_mode", "config", "state", "published"):
                if field in spec:
                    setattr(module, field, deepcopy(spec[field]))
            module.channels = tuple(spec["channels"])
            modules[module.module_id] = module
        for spec in record["modules"]:
            module = modules[spec["module_id"]]
            module._dependencies = tuple(modules[key] for key in spec["modules"] if key in modules)
            module._bind(node)
            if hasattr(module,'_tool_specs'):
                from app.projects.module_tools import bind_tools
                bind_tools(module,node,module._tool_specs)
            node.modules._add(module)
        factory_tools = {key: {tool.name: tool for tool in module.tools} for key, module in modules.items()}
        tools = {(None, name): tool for name, tool in initial_tools.items()}
        groups = {}

        def restore(item):
            if "modules" in item and item.get("modules") is True:
                return node.modules.tools
            if "module" in item:
                return modules[item["module"]].tools
            if "group_ref" in item:
                return groups[item["group_ref"]]
            if "group" in item:
                group = groups[item["group"]] = Tools()
                group._members[:] = [restore(member) for member in item["members"]]
                return group
            name = item["tool"]
            owner = item.get("factory_module")
            key = (owner, name)
            if key not in tools:
                tools[key] = factory_tools[owner][name] if owner is not None else self.tool_types[name](node, item)
            tool = tools[key]
            tool.description, tool.parameters = item["description"], deepcopy(item["parameters"])
            tool.modules = tuple(modules[key] for key in item["modules"])
            return tool

        for spec in record["modules"]:
            modules[spec["module_id"]].tools._members[:] = restore(spec["tools"]).members
        node.tools._members[:] = restore(record["tools"]).members
