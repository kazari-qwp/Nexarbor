"""沿 knowledge 频道调用首个可见目录；动作在 access 节点门禁内执行。"""
from domain.core import access


class CatalogAccess:
    def __init__(self, owner):
        self._access_origin = owner._access_origin
        self.strength = owner.strength
        self.called = False

    async def call(self, operation, parameters):
        return next(value for value in (await self._call(operation, parameters)).values() if value is not None)

    @access(channels=["knowledge"])
    async def _call(self, node, operation, parameters):
        if self.called:
            return
        catalog = node.modules.get("knowledge.catalog")
        if catalog is not None:
            self.called = True
            return await getattr(catalog, operation)(**parameters)
