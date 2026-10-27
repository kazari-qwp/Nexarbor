"""集合节点的原公开操作，沿 knowledge 频道转交真实目录模块。"""
from copy import deepcopy
from domain.core import Module
from ..knowledge_catalog.access import CatalogAccess


class KnowledgeCollectionModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__("knowledge.collection", **access_settings)
        self.config, self.state = deepcopy(config or {}), deepcopy(state or {})

    async def execute(self, operation, **parameters):
        return await CatalogAccess(self).call("collection_access", dict(collection=self.config["collection"], operation=operation, arguments=parameters))

    async def collection(self, **parameters):
        return await self.execute("collection", **parameters)

    async def store(self, **parameters):
        return await self.execute("store", **parameters)

    async def fetch(self, **parameters):
        return await self.execute("fetch", **parameters)

    async def search(self, **parameters):
        return await self.execute("search", **parameters)

    async def update(self, **parameters):
        return await self.execute("update", **parameters)

    async def delete(self, **parameters):
        return await self.execute("delete", **parameters)

    async def export(self, **parameters):
        return await self.execute("export", **parameters)

    async def commit_intake(self, **parameters):
        return await self.execute("commit_intake", **parameters)

    async def index(self, **parameters):
        return await self.execute("index", **parameters)

    async def query(self, **parameters):
        return await self.execute("query", **parameters)

    async def wiki(self, **parameters):
        return await self.execute("wiki", **parameters)

