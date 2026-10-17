"""Declarative installation of standard modules, independent of the workbench."""
from pathlib import Path
from .contract import factory
from jsonschema import Draft202012Validator

def bind_modules(backend):
    for node,runtime in getattr(backend,'_standard_module_bindings',[]):runtime.unbind(node)
    bindings=[];runtime=backend.network.signals
    for node in backend.network.nodes.values():
        modules=[m for (owner,_),m in backend.modules.instances.items() if owner==node.node_id and hasattr(m,'manifest')]
        if not modules:continue
        async def receive(context,modules=modules):
            results=[]
            for module in modules:
                if set(module.manifest['signals']).intersection(context.signal.channels):
                    result=module.on_signal(context)
                    if hasattr(result,'__await__'):result=await result
                    Draft202012Validator(module.manifest['state_schema']).validate(module.state)
                    results.append(result)
            return results
        runtime.bind(node.node_id,receive,access_strength=(node.execution_binding or {}).get('strength',0));bindings.append((node.node_id,runtime))
    backend._standard_module_bindings=bindings

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
