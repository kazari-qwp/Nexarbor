"""Single-level helpers; applications configure business scopes and toolboxes."""
from threading import RLock
from uuid import uuid4

from datanet.core.application import Component
from datanet.core.agent_node import AgentNode
from datanet.core.interface import Interface


class Plugin(Component):
    def install(self):
        self.policies, self.lock = {}, RLock()
        self.on('tool/definition', self.definition)
        self.on('tool/available', self.available)
        self.on('agent/ensure-mounted', self.ensure_mounted)

    def register(self, actor, policy):
        if actor not in self.r.backend.agents or self.r.backend.agents[actor].get('worker_parent'):
            raise PermissionError('Only a main Agent may register helper creation')
        self.policies[actor] = policy

    def definition(self, event):
        if event['name'] == 'datanet_spawn_helper' and event['actor'] in self.policies:
            event['spec']['parameters']['properties']['components']['items']['enum'] = list(self.policies[event['actor']]['components'])

    def available(self, event):
        if event['name'] == 'datanet_spawn_helper' and event['actor'] not in self.policies:
            event['allowed'] = False

    def ensure_mounted(self, event):
        target = event['target']
        binding = self.r.backend.agents.get(target, {})
        if not binding.get('worker_parent') or target in self.r.states:
            return
        parent = binding['worker_parent']
        policy = self.policies.get(parent)
        if policy is None:
            raise PermissionError('Helper owner is not available')
        self.r.plugins['capabilities/agent_runtime'].create(target, binding['prompt'], parent,
            binding['maxStrength'], binding['toolboxes'], policy['role'], binding,
            allowed_toolboxes=policy['toolboxes'])

    def tool_datanet_spawn_helper(self, actor, args):
        with self.lock:
            policy = self.policies.get(actor)
            if policy is None or self.r.backend.agents[actor].get('worker_parent'):
                raise PermissionError('Helpers cannot create further Agents')
            docs = self.r.plugins['capabilities/task_documents']
            task = docs.task(actor)
            children = [id for id in task['members'] if self.r.backend.agents.get(id, {}).get('worker_parent') == actor]
            if len(children) >= policy.get('limit', 8):
                raise ValueError('Helper limit reached for this task')
            components = args.get('components')
            if components is None:
                scope = {k: list(v) for k, v in policy['scope'].items()}
                selected = list(policy['components'])
            else:
                if not isinstance(components, list) or not components or len(set(components)) != len(components) or any(c not in policy['components'] for c in components):
                    raise ValueError('Choose a nonempty list of available components')
                selected = components
                scope = {k: [] for k in policy['scope']}
                for c in components:
                    for key, values in policy['components'][c]['scope'].items():
                        if key not in scope or not set(values).issubset(policy['scope'][key]):
                            raise PermissionError('Component exceeds delegable scope')
                        scope[key] = list(dict.fromkeys([*scope[key], *values]))
            # Resolve against the parent's actual tools, never merely installed components.
            grant = self.r.resolve(policy['toolboxes'], policy['toolboxes'], policy['role'])
            if not set(grant['framework']).issubset(self.r.state(actor)['grant']['framework']):
                raise PermissionError('Helper tools exceed parent grants')
            if any(options != self.r.state(actor)['grant']['framework'][name] for name, options in grant['framework'].items()):
                raise PermissionError('Helper tool options must match parent grants')
            if not set(grant['official']['tools']).issubset(self.r.state(actor)['grant']['official']['tools']):
                raise PermissionError('Helper native tools exceed parent grants')
            parent_official = self.r.state(actor)['grant']['official']
            if parent_official['skills'] != '*' and (grant['official']['skills'] == '*' or not set(grant['official']['skills']).issubset(parent_official['skills'])):
                raise PermissionError('Helper skills exceed parent grants')
            if not set(grant['official']['skillProviders']).issubset(parent_official['skillProviders']):
                raise PermissionError('Helper skill providers exceed parent grants')
            id = actor + '/helper-' + uuid4().hex[:12]
            node = AgentNode(id, '任务助手', file_path=self.r.directory / 'agents/memories' / (id.encode().hex() + '.md'))
            node.management_parent_id = actor
            self.r.backend.network.add_node(node)
            self.r.backend.network.nodes[actor].interfaces.append(Interface(id, metadata={'visibility': 'private', 'channels': ['access.read']}))
            # Persist identity/scope before mounting, so bound hooks see the same policy.
            self.r.rpc('bind_agent', target=id, session_id='datanet-' + str(uuid4()), kind='helper', manager_id=actor,
                       creator_node_id=actor, worker_parent=actor, business_scope=scope, worker_components=selected)
            docs.attach(task, id)
            self.r.emit('worker/scoped', actor=id, parent=actor, scope=scope, components=selected)
            self.r.rpc('save')
            prompt = self.r.resource(self.id, 'prompt.md') + '\n' + policy.get('prompt', '')
            mounted = self.r.plugins['capabilities/agent_runtime'].create(id, prompt, actor,
                self.r.state(actor)['strength'], policy['toolboxes'], policy['role'], self.r.backend.agents[id],
                allowed_toolboxes=policy['toolboxes'], resume=False)
            self.r.emit('capabilities/changed', actor=actor)
            return dict(node_id=id, components=selected, scope=scope, **docs.reference(id, task),
                        session_id=mounted['session_id'])
