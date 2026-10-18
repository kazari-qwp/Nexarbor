"""Declarative installation of standard modules, independent of the workbench."""
from pathlib import Path
from .contract import factory

def bind_modules(backend):
    backend.modules.bind_signals()

def register(services):
    services.standard_modules={}
    services.graph_loaders.append(bind_modules)
    owner=services.loading_component
    for key in services.order:
        entry=services.catalog[key]
        if key not in services.enabled or 'nodeModule' not in entry:continue
        folder=(Path(entry['implementation_directory'])/entry['nodeModule']).resolve()
        if not folder.is_relative_to(entry['implementation_directory']):raise ValueError('Standard module source escapes component')
        manifest,create=factory(folder)
        services.loading_component=key;services.node_module(manifest['id'],create)
        services.standard_modules[manifest['id']]=dict(folder=folder,manifest=manifest)
    services.loading_component=owner
