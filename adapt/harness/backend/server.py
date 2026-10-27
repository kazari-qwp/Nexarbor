"""并发 stdio RPC 入口；项目装配由应用选择，执行仍走统一原生宿主。"""

import os
import sys

from app.runtime.backend import Backend
from app.runtime.requester import as_requester
from .transport import Transport


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    project = None
    if os.environ.get('NEXARBOR_APPLICATION') == 'npc_town':
        from projects.npc_town.runtime import TownProject
        project = TownProject(sys.argv[1],os.environ.get('NEXARBOR_PROJECT_DIRECTORY'))
        backend = project.backend
    else:
        backend = Backend(sys.argv[1])
    transport = Transport(backend)
    if project is not None:
        def pulse_run(parameters):
            node = backend.network.get(parameters['node_id'])
            if node.node_type != 'pulse':raise ValueError('Expected a pulse node')
            return backend.perform('pulse_run',lambda:transport.runtime.run(node.run(backend.signals,
                cycles=parameters.get('cycles',1),timeout_seconds=parameters.get('timeout_seconds',86400)),timeout=86460))
        async def local(parameters):
            node = backend.network.get(parameters['node_id'])
            module_id = parameters['module_id'];operation = parameters['operation']
            definition = next(item for item in project.module_schemas[module_id].get('operations',[]) if item['name']==operation)
            from jsonschema import Draft202012Validator
            arguments = parameters.get('arguments',{})
            Draft202012Validator(definition.get('parameters',{})).validate(arguments)
            with as_requester(node.info.node_id):
                return await getattr(node.modules.get(module_id),operation)(**arguments)
        transport.routes['pulse_run'] = pulse_run
        transport.routes['module_call'] = lambda parameters:backend.perform('module_call',lambda:transport.runtime.run(local(parameters),timeout=86460))
        transport.routes['template_instantiate'] = lambda parameters:backend.perform('template_instantiate',lambda:transport.runtime.run(project.templates.instantiate(**parameters)))
    transport.run(sys.stdin)


if __name__ == '__main__':
    main()
