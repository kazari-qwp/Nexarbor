"""节点局部快照，保留节点、模块、工具箱及回调身份。"""

from copy import deepcopy
from pathlib import Path

from app.persistence.resource_data import read_bytes, resource_files
from app.persistence.node_resources import resource_roots
from domain.core import DataNode, Multiplier, Tools

_MODULE_FIELDS = ("description", "channels", "strength", "channel_mode", "config", "state", "published")
_DATA_FIELDS = ("node_id", "name", "directory", "storage_path", "storage", "schema_fields",
                "embedding", "embedding_config", "collection_id", "table_name", "_table_sql", "_key_sql", "key_column", "dtype",
                "chunk_size", "chunk_overlap")


def _fields(owner, names):
    return {name: (vars(owner)[name], vars(owner)[name] if callable(vars(owner)[name]) else deepcopy(vars(owner)[name]))
            for name in names if name in vars(owner)}


def _restore_fields(owner, fields):
    for name, (original, saved) in fields.items():
        if callable(original):
            setattr(owner, name, original)
        elif type(original) is dict:
            original.clear()
            original.update(deepcopy(saved))
            setattr(owner, name, original)
        elif type(original) is list:
            original[:] = deepcopy(saved)
            setattr(owner, name, original)
        else:
            setattr(owner, name, deepcopy(saved))


class NodeSnapshots:
    def __init__(self, network, directory, *, execution=None, bindings=None, document=None):
        self.network = network
        self.directory = Path(directory).resolve()
        self.execution = {} if execution is None else execution
        self.bindings = {} if bindings is None else bindings
        self.document = document

    def _root(self, node):
        if not isinstance(node, DataNode):
            return None
        return node.saver.path.resolve()

    @staticmethod
    def _files(root):
        if root is None:
            return []
        return resource_files(root)

    def capture(self, nodes):
        selected = set(nodes)
        roots = {node.info.node_id: resource_roots(node) for node in self.network}
        for node in selected:
            for root, directory in roots[node]:
                if not root.is_relative_to(self.directory):
                    raise ValueError('Transactional node resources must stay in the runtime directory')
                for path in self._files(root):
                    if not path.resolve().is_relative_to(self.directory):
                        raise ValueError('Transactional node resource is outside the runtime directory')
                for other, targets in roots.items():
                    if other in selected:
                        continue
                    for target, target_directory in targets:
                        if root == target or directory and target.is_relative_to(root) or target_directory and root.is_relative_to(target):
                            raise ValueError('Nodes sharing a resource file must be locked together')
        return {node: self._capture(self.network.get(node), self._root(self.network.get(node))) for node in nodes}

    def _capture(self, node, root):
        roots = resource_roots(node)
        groups, tools = {}, {}

        def capture_tools(group):
            if group in groups:
                return
            groups[group] = group.members
            for member in group.members:
                if isinstance(member, Tools):
                    capture_tools(member)
                else:
                    tools[member] = _fields(member, ('name', 'description', 'parameters'))

        capture_tools(node.tools)
        modules = tuple(node.modules)
        for module in modules:
            capture_tools(module.tools)
        image = dict(
            node=node, info=node.info, info_fields=deepcopy(vars(node.info)),
            bias=node.bias, aggregation=node.aggregation, aggregation_fields=_fields(node.aggregation, vars(node.aggregation)),
            links=[(link, _fields(link, (name for name in vars(link) if name != "processor")),
                    link.processor, _fields(link.processor, vars(link.processor)) if isinstance(link.processor, Multiplier) else {})
                   for link in node.links],
            modules=node.modules.copy(), module_fields={module: _fields(module, _MODULE_FIELDS) for module in modules},
            groups=groups, tools=tools, inputs=node.inputs.snapshot() if node.node_type == 'agent' else None,
            execution=deepcopy(self.execution.get(node.info.node_id)),
            binding=deepcopy(self.bindings.get(node.info.node_id)),
            runner=getattr(node, 'runner', None), root=root, directory=root is not None and root.is_dir(),
            resource_roots=roots, files={path: read_bytes(path) for owned, _ in roots for path in self._files(owned)},
        )
        if node.node_type == 'pulse':
            image['pulse_fields'] = _fields(node, ('channels', 'strength', 'content', 'signal_options', 'state'))
        if isinstance(node, DataNode):
            image.update(dataer=node.dataer, saver=node.saver, save_data=node.save_data,
                         data_fields=_fields(node.dataer, _DATA_FIELDS), data_objects=[])
            for owner in (node.dataer, node.saver):
                data = getattr(owner, 'data', None)
                if data is not None:
                    image['data_objects'].append((owner, data, deepcopy(vars(data))))
        return image

    def restore(self, images):
        # 全组恢复完毕后，协调器才释放任何一个节点。
        for node_id, image in images.items():
            node = image['node']
            node.info = image['info']
            vars(node.info).clear()
            vars(node.info).update(deepcopy(image['info_fields']))
            node.bias, node.aggregation = image['bias'], image['aggregation']
            _restore_fields(node.aggregation, image['aggregation_fields'])
            for link, fields, processor, processor_fields in image['links']:
                for name in set(vars(link)) - fields.keys() - {'processor'}:
                    delattr(link, name)
                _restore_fields(link, fields)
                link.processor = processor
                _restore_fields(processor, processor_fields)
            node.links._links[:] = [entry[0] for entry in image['links']]
            node.modules._modules.clear()
            node.modules._modules.update(image['modules']._modules)
            for module, fields in image['module_fields'].items():
                _restore_fields(module, fields)
            for group, members in image['groups'].items():
                group._members[:] = members
            for tool, fields in image['tools'].items():
                _restore_fields(tool, fields)
            if 'pulse_fields' in image:_restore_fields(node, image['pulse_fields'])
            if image['inputs'] is not None:
                node.runner = image['runner']
                with node.inputs.lock:
                    node.inputs.sources.clear()
                    node.inputs.sources.update(deepcopy(image['inputs']))
            if image['binding'] is None:
                self.bindings.pop(node_id, None)
            else:
                binding = self.bindings.setdefault(node_id, {})
                binding.clear()
                binding.update(deepcopy(image['binding']))
            if image['execution'] is None:
                self.execution.pop(node_id, None)
            else:
                state = self.execution.setdefault(node_id, {})
                state.clear()
                state.update(deepcopy(image['execution']))
            if isinstance(node, DataNode):
                node.dataer, node.saver, node.save_data = image['dataer'], image['saver'], image['save_data']
                _restore_fields(node.dataer, image['data_fields'])
                for owner, data, fields in image['data_objects']:
                    owner.data = data
                    vars(data).clear()
                    vars(data).update(deepcopy(fields))
                root = image['root']
                for path in (path for owned, _ in image['resource_roots'] for path in self._files(owned)):
                    if path not in image['files']:
                        if not path.resolve().is_relative_to(self.directory):
                            raise ValueError('Rollback resource is outside the runtime directory')
                        path.unlink(missing_ok=True)
                for path, content in image['files'].items():
                    if not path.resolve().is_relative_to(self.directory):
                        raise ValueError('Rollback resource is outside the runtime directory')
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = path.with_name(path.name + '.node-rollback.tmp')
                        temporary.write_bytes(content)
                        temporary.replace(path)
                restored = getattr(node.dataer, 'resources_restored', None)
                if restored is not None:
                    restored()

    def set_context(self, image, cursor):
        if image['execution'] is None:
            image['execution'] = {}
        image['execution']['context_cursor'] = deepcopy(cursor)

    def set_execution_cursor(self, node, cursor):
        state = self.execution.setdefault(node, {})
        state['context_cursor'] = deepcopy(cursor)
        if cursor.get('session_id'):
            state['session_id'] = cursor['session_id']

    def validate(self, nodes):
        for node_id in nodes:
            for module in self.network.get(node_id).modules:
                validate = getattr(module, 'validate_state', None)
                if validate is not None:
                    validate()
