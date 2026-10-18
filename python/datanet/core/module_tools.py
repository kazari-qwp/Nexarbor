"""Agent tool adapters for explicitly declared component tool providers."""
import asyncio
from hashlib import sha256
from jsonschema import Draft202012Validator
from .json_values import freeze, thaw


class ModuleTools:
    def __init__(self, backend): self.backend = backend

    def _source(self, actor, node, module, strength, channels):
        return next((source for source in self.backend.modules.tool_sources(actor, node,
            strength=strength, channels=channels) if source['module'] == module), None)

    async def _list(self, actor, source, strength, channels):
        response = await self.backend.modules.access(actor, source['node_id'], source['module'], source['list'],
            strength=strength, channels=channels)
        if response['status'] != 'ok': raise RuntimeError(response['error'])
        data = response['data']
        if not isinstance(data, list): raise ValueError('Tool provider must return a list')
        entries = []; seen = set()
        for item in data:
            if not isinstance(item, dict) or not {'id','name','description','parameters'} <= item.keys():
                raise ValueError('Invalid provided tool descriptor')
            if not all(isinstance(item[key], str) and item[key] for key in ('id','name')):
                raise ValueError('Provided tools require nonempty identities and names')
            if item['id'] in seen: raise ValueError('Duplicate provided tool identity')
            if not isinstance(item['description'], str): raise ValueError('Invalid provided tool description')
            Draft202012Validator.check_schema(item['parameters'])
            if item['parameters'].get('type') != 'object': raise ValueError('Provided tool parameters must be an object')
            seen.add(item['id'])
            source_id = sha256((source['node_id']+'\0'+source['module']).encode()).hexdigest()[:24]
            alias = 'mod_' + sha256((source_id+'\0'+item['id']).encode()).hexdigest()[:24]
            origin = item.get('origin')
            provenance = ' · 来源 '+origin['node_id'] if isinstance(origin,dict) and isinstance(origin.get('node_id'),str) else ''
            entries.append(dict(alias=alias, source_id=source_id, node_id=source['node_id'], module=source['module'],
                tool_id=item['id'], origin=origin, via=item.get('via',[]), definition=dict(name=alias,
                    description=source['node_id']+' · '+item['name']+provenance+' · '+item['description'], parameters=item['parameters'])))
        return entries

    async def visit(self, actor, target, *, strength, channels):
        async with self.backend.node_locks.access([actor,target]):
            return await self._visit_owned(actor,target,strength=strength,channels=channels)

    async def _visit_owned(self, actor, target, *, strength, channels):
        sources = self.backend.modules.tool_sources(actor, target, strength=strength, channels=channels)
        results = await asyncio.gather(*(self._list(actor, source, strength, channels) for source in sources))
        memory = self.backend.agents.setdefault(actor, {})
        known = memory.setdefault('module_tool_sources', {})
        tools = memory.setdefault('module_tools', {})
        result = []
        for source, entries in zip(sources, results):
            source_id = sha256((source['node_id']+'\0'+source['module']).encode()).hexdigest()[:24]
            known[source_id] = dict(node_id=target, module=source['module'])
            for alias in [alias for alias, entry in tools.items() if entry['source_id'] == source_id]: tools.pop(alias)
            for entry in entries:
                tools[entry['alias']] = thaw(freeze(entry)); result.append(entry)
        return result

    async def refresh(self, actor, *, strength, channels):
        sources = list(self.backend.agents.get(actor, {}).get('module_tool_sources', {}).values())
        # Each provider may perform independent access requests concurrently.
        await asyncio.gather(*(self.visit(actor, source['node_id'], strength=strength, channels=channels)
            for source in {source['node_id']:source for source in sources}.values()))

    def acquired(self, actor, *, strength, channels):
        return [thaw(freeze(entry)) for entry in self.backend.agents.get(actor, {}).get('module_tools', {}).values()
            if self._source(actor, entry['node_id'], entry['module'], strength, channels)]

    async def invoke(self, actor, entry, arguments, *, strength, channels):
        async with self.backend.node_locks.access([entry['node_id']]):
            return await self._invoke_owned(actor,entry,arguments,strength=strength,channels=channels)

    async def _invoke_owned(self, actor, entry, arguments, *, strength, channels):
        source = self._source(actor, entry['node_id'], entry['module'], strength, channels)
        if source is None: raise PermissionError('Tool provider is no longer accessible')
        response = await self.backend.modules.access(actor, entry['node_id'], entry['module'], source['invoke'],
            dict(tool_id=entry['tool_id'], arguments=arguments), strength=strength, channels=channels)
        if response['status'] != 'ok': raise PermissionError(response['error'])
        return response['data']
