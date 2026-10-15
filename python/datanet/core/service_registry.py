"""Loads component-owned RPC services; the bridge has no application route table."""
from importlib import import_module
from pathlib import Path
import json
import os
from datanet.core.component_registry import manifests, component_root

class ComponentServices:

    def __init__(self):
        self.catalog = {m['id']: m for m in manifests()}
        profile_file = component_root() / 'profile.json'
        profile = json.loads(profile_file.read_text(encoding='utf-8')) if profile_file and profile_file.exists() else {}
        profile.update(json.loads(os.environ.get('DATANET_COMPONENT_PROFILE', '{}')))
        self.enabled = {key for key, m in self.catalog.items() if profile.get(key, m.get('enabled', True))}
        changed = True
        while changed:
            changed = False
            for key in list(self.enabled):
                if any((dep not in self.enabled for dep in self.catalog[key].get('requires', []))):
                    self.enabled.remove(key)
                    changed = True
        self.binding_validators = []
        self.statusters = []
        self.routes = {}
        self.mutations = set()
        self.node_presets = {}
        self.network_presets = {}
        self.toolkit_factories = []
        self.initializers = []
        self.graph_loaders = []
        self.snapshotters = []
        self.restorers = []
        self.node_restorers = []
        self.root_packages = {}
        self.network_handlers = {}
        for key, m in self.catalog.items():
            if key in self.enabled:
                for module in m.get('python', {}).get('services', []):
                    import_module(module).register(self)

    def rpc(self, name, function, mutation=False):
        if name in self.routes:
            raise ValueError('Duplicate component route: ' + name)
        self.routes[name] = function
        if mutation:
            self.mutations.add(name)

    def install(self, backend):
        for fn in self.initializers:
            fn(backend)

    def graph_loaded(self, backend):
        for fn in self.graph_loaders:
            fn(backend)

    def snapshot(self, backend):
        result = {}
        for fn in self.snapshotters:
            result.update(fn(backend))
        return result

    def restore(self, backend, document):
        for fn in self.restorers:
            fn(backend, document)

    def restore_node(self, backend, node, document):
        for fn in self.node_restorers:
            fn(backend, node, document)

    def toolkits(self, backend):
        result = {}
        for fn in self.toolkit_factories:
            result.update(fn(backend))
        return result

    def status(self, backend):
        result = {}
        for fn in self.statusters:
            result.update(fn(backend))
        return result
