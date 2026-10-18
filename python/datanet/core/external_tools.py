"""Registered host tools offered by graph nodes, acquired through authorized visits."""
import inspect
from hashlib import sha256
from jsonschema import Draft202012Validator
from .json_values import freeze, thaw, names
from .interface import validate_strength


def validate_offers(value):
    if not isinstance(value, list): raise ValueError('offered_tools must be a list')
    seen = set()
    for offer in value:
        if not isinstance(offer, dict) or set(offer) != {'ref', 'channels'}:
            raise ValueError('Tool offer requires ref and channels only')
        if not isinstance(offer['ref'], str) or not offer['ref'] or offer['ref'] in seen:
            raise ValueError('Invalid or duplicate tool reference')
        names(offer['channels'], 'tool offer channels', allow_empty=False)
        seen.add(offer['ref'])
    return thaw(freeze(value))


class ExternalTools:
    def __init__(self, backend):
        self.backend = backend
        self._catalog, self._providers = {}, {}

    def register(self, provider, definitions, execute):
        if not isinstance(provider, str) or not provider or ':' in provider: raise ValueError('Invalid provider')
        if not callable(execute): raise TypeError('Tool provider requires an executor')
        pending = {}
        for item in definitions:
            if set(item) != {'name', 'description', 'parameters'}: raise ValueError('Invalid host tool descriptor')
            name = item['name']
            if not isinstance(name, str) or not name or ':' in name: raise ValueError('Invalid host tool name')
            if not isinstance(item['description'], str): raise ValueError('Invalid tool description')
            Draft202012Validator.check_schema(item['parameters'])
            if item['parameters'].get('type') != 'object': raise ValueError('Tool parameters must be an object')
            ref = provider + ':' + name
            if ref in pending: raise ValueError('Duplicate host tool')
            pending[ref] = freeze(dict(ref=ref, provider=provider, **item))
        # Replace a provider atomically. Removed definitions cannot be acquired/executed.
        self._catalog = {ref: d for ref, d in self._catalog.items() if d['provider'] != provider} | pending
        self._providers[provider] = execute

    def catalog(self): return [thaw(value) for value in self._catalog.values()]

    def validate_node(self, node):
        validate_offers(node.offered_tools)
        for item in node.offered_tools:
            if item['ref'] not in self._catalog: raise ValueError('Unregistered external tool: ' + item['ref'])

    def _resolve(self, actor, target, ref, strength, channels):
        from contextlib import nullcontext
        locks = getattr(self.backend,'node_locks',None)
        with locks.access_sync([target],mutable=False) if locks else nullcontext():
            return self._resolve_owned(actor,target,ref,strength,channels)

    def _resolve_owned(self, actor, target, ref, strength, channels):
        validate_strength(strength); channels = names(channels, 'tool access channels')
        node = self.backend.network.nodes.get(target)
        descriptor = self._catalog.get(ref)
        if node is None or descriptor is None: raise PermissionError('Tool provider or registered reference is unavailable')
        offer = next((o for o in node.offered_tools if o['ref'] == ref), None)
        if offer is None: raise PermissionError('Tool is no longer offered by this node')
        selected = tuple(c for c in channels if c in offer['channels'])
        if not selected: raise PermissionError('Tool offer channel is not granted')
        if not any(n.node_id == target for n, _, _ in self.backend.network.walk_states(actor, channels=selected, strength=strength)):
            raise PermissionError('Tool provider is outside the current graph view')
        from .component_registry import node_enabled
        if not node_enabled(node): raise PermissionError('Tool provider is disabled')
        return descriptor

    def visit(self, actor, target, *, strength, channels, acquire=True):
        from contextlib import nullcontext
        locks = getattr(self.backend,'node_locks',None)
        with locks.access_sync([actor,target],mutable=acquire) if locks else nullcontext():
            return self._visit_owned(actor,target,strength=strength,channels=channels,acquire=acquire)

    def _visit_owned(self, actor, target, *, strength, channels, acquire):
        # Validate the visit even if the node offers no tools.
        if not any(n.node_id == target for n, _, _ in self.backend.network.walk_states(actor, strength=strength, channels=channels)):
            raise PermissionError('Visit target is outside the current graph view')
        node = self.backend.network.nodes[target]; result = []
        from .agent_node import AgentNode
        for offer in node.offered_tools:
            try: descriptor = self._resolve(actor, target, offer['ref'], strength, channels)
            except PermissionError: continue
            alias = 'ext_' + sha256((target+'\0'+offer['ref']).encode()).hexdigest()[:24]
            entry = dict(alias=alias, target=target, ref=offer['ref'], channels=list(channels), strength=strength)
            result.append(dict(**thaw(descriptor), alias=alias, node_id=target))
            if acquire and isinstance(self.backend.network.nodes[actor], AgentNode):
                self.backend.agents.setdefault(actor, {}).setdefault('external_tools', {})[alias] = entry
        return result

    def acquired(self, actor, *, strength, channels):
        result = []
        for entry in self.backend.agents.get(actor, {}).get('external_tools', {}).values():
            selected = tuple(c for c in entry['channels'] if c in channels)
            try: descriptor = self._resolve(actor, entry['target'], entry['ref'], min(strength, entry['strength']), selected)
            except PermissionError: continue
            result.append(dict(**entry, definition=dict(name=entry['alias'],
                description=self.backend.network.nodes[entry['target']].name+' · '+descriptor['description'],
                parameters=thaw(descriptor['parameters']))))
        return result

    async def invoke(self, actor, target, ref, arguments, *, strength, channels):
        locks = getattr(self.backend,'node_locks',None)
        if locks:
            async with locks.access([target]):
                return await self._invoke_owned(actor,target,ref,arguments,strength=strength,channels=channels)
        return await self._invoke_owned(actor,target,ref,arguments,strength=strength,channels=channels)

    async def _invoke_owned(self, actor, target, ref, arguments, *, strength, channels):
        descriptor = self._resolve(actor, target, ref, strength, channels)
        arguments = thaw(freeze(arguments))
        Draft202012Validator(thaw(descriptor['parameters'])).validate(arguments)
        execute = self._providers[descriptor['provider']]
        # No credentials/host objects are returned to component code.
        value = execute(actor, descriptor['name'], arguments)
        if inspect.isawaitable(value): value = await value
        return thaw(freeze(value))
