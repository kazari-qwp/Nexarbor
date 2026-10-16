"""Loads component-owned RPC services; the bridge has no application route table."""
from importlib import import_module
from pathlib import Path
import json
import os
from datanet.component_catalog import mount_paths
from datanet.core.component_registry import enabled_components

class ComponentServices:

    def __init__(self):
        self.catalog, self.order = mount_paths()
        self.enabled = enabled_components()
        self.binding_validators = []
        self.statusters = []
        self.module_types = {}
        self.module_owners = {}
        self.loading_component = None
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
        for key in self.order:
            m = self.catalog[key]
            if key in self.enabled:
                self.loading_component = key
                for module in m.get('python', {}).get('services', []):
                    import_module(module).register(self)
        for entries in [self.network_presets,self.root_packages,self.network_handlers]:
            for name in list(entries):
                key='network_presets/'+name
                if key in self.catalog and key not in self.enabled:entries.pop(name)

    def node_module(self, name, factory):
        if name in self.module_types:raise ValueError("Duplicate node module: "+name)
        self.module_types[name]=factory
        self.module_owners[name]=self.loading_component

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
