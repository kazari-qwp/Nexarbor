"""将来源目录编译为模型别名，调用仍由工具发现模块重新验证。"""

from copy import deepcopy
from hashlib import sha256

from jsonschema import Draft202012Validator


class ToolCatalog:
    def __init__(self, discovery):
        self.discovery = discovery
        self.entries = {}
        self.history = {}

    async def refresh(self):
        # 先完整校验，再替换目录；半途失败不能发布半份目录。
        entries = {}
        node_id = self.discovery._access_origin.info.node_id
        module_id = self.discovery.module_id
        source_id = sha256((node_id + "\0" + module_id).encode()).hexdigest()[:24]
        for item in await self.discovery.collect():
            Draft202012Validator.check_schema(item["parameters"])
            if item["parameters"].get("type") != "object":
                raise ValueError("工具参数声明必须是 object")
            alias = "mod_" + sha256((source_id + "\0" + item["id"]).encode()).hexdigest()[:24]
            if alias in entries:
                raise ValueError("工具来源标识重复")
            definition = dict(name=alias, description=(
                node_id + " · " + item["name"] + " · 来源 " + item["origin"]["node_id"] + " · " + item["description"]
            ), parameters=deepcopy(item["parameters"]))
            entries[alias] = dict(alias=alias, source_id=source_id, node_id=node_id, module=module_id,
                                  tool_id=item["id"], origin=deepcopy(item["origin"]), via=list(item["via"]),
                                  definition=definition)
        self.entries = entries
        self.history.update(deepcopy(entries))
        return [deepcopy(entry["definition"]) for entry in entries.values()]

    async def invoke(self, alias, arguments):
        # 未获得的别名不能靠猜测调用。历史只用于提示，不授予执行权。
        if alias not in self.entries:
            raise PermissionError("该工具未取得或已被撤销")
        if not isinstance(arguments, dict):
            raise TypeError("工具参数必须是对象")
        await self.refresh()
        entry = self.entries.get(alias)
        if entry is None:
            raise PermissionError("该工具已离开当前可达范围")
        Draft202012Validator(entry["definition"]["parameters"]).validate(arguments)
        return await self.discovery.invoke(entry["tool_id"], arguments)

    def snapshot(self):
        # 保存的内容全部是描述，不保存 Python 回调或可执行权限。
        return dict(history=deepcopy(self.history))

    def restore(self, state):
        self.history = deepcopy(state.get("history", {}))
        self.entries = {}
