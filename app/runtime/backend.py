"""新节点的持久化运行状态：原增量日志、节点事务和资源恢复。"""

from copy import deepcopy
from pathlib import Path
from threading import RLock

from app.network_saver import NetworkSaver
from app.persistence.checkpoints import Checkpoints
from app.persistence.node_records import merge_records
from app.persistence.resource_data import decode_data, encode_bytes, read_data, resource_files, write_data
from app.transactions import NodeLocks, NodeSnapshots
from domain.agent import MarkdownAgentNode
from domain.core import DataNode, Network, NodeInfo


class Backend:
    def __init__(self, directory, *, network=None, saver=None, snapshot_interval=100):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._transaction_lock = RLock()
        self.saver = NetworkSaver() if saver is None else saver
        self.store = Checkpoints(self.directory, snapshot_interval=snapshot_interval)
        self.agents, self.bindings, self.extension_state = {}, {}, {}
        self.failed = False
        self.commit_observer = None
        self.snapshot_extra = None
        self._context_port = None
        try:
            previous = self.store.latest()
            if previous is not None:
                self.restore(previous)
            else:
                if network is None:
                    memory = self.directory / 'root-memory.md'
                    if not memory.exists():memory.write_text('', encoding='utf-8')
                    network = Network([MarkdownAgentNode(NodeInfo('root', '起始节点'), memory)])
                self._use_network(network)
                self.store.commit(self.snapshot())
        except BaseException:
            self.store.close()
            raise

    @property
    def context_port(self):
        return self._context_port

    @context_port.setter
    def context_port(self, port):
        self._context_port = port
        self.node_locks.contexts = port

    def _use_network(self, network):
        self.network = network
        snapshots = NodeSnapshots(network, self.directory, execution=self.agents, bindings=self.bindings,
                                  document=self._snapshot)
        self.node_locks = NodeLocks(network, snapshots, contexts=self._context_port,
                                    commit=self.commit_node_transaction)

    def document_files(self):
        return {name: read_data(self._file(name)) for name in self.extension_state.get('document_resources', [])}

    def _file(self, name):
        target = (self.directory / name).resolve()
        if not target.is_relative_to(self.directory):
            raise ValueError('Checkpoint file escapes runtime directory')
        return target

    def write_documents(self, documents):
        files = [(self._file(name), content) for name, content in documents.items()]
        for _, content in files:decode_data(content)
        for target, content in files:write_data(target, content)
        self.extension_state['document_resources'] = sorted(set(self.extension_state.get('document_resources', []))
            | {target.relative_to(self.directory).as_posix() for target, _ in files})

    def snapshot(self, *, committing=None):
        self.node_locks.wait_prepared_sync()
        while True:
            with self.node_locks.condition, self._transaction_lock:
                if self.node_locks._prepared():return self._snapshot(committing=committing)
            self.node_locks.wait_prepared_sync()

    def _snapshot(self, *, committing=None):
        overrides, images = self.node_locks.overrides(committing)
        network = self.saver.document(self.network, self.directory, node_overrides=overrides)
        for entry in network['nodes']:
            if entry['node_id'] not in overrides:
                entry['execution'] = deepcopy(self.bindings.get(entry['node_id']))
        files = self.document_files()
        for node in self.network:
            if node.info.node_id in images or not isinstance(node, DataNode):continue
            root = node.saver.path.resolve()
            if root.is_relative_to(self.directory):
                for path in resource_files(root):
                    if not path.resolve().is_relative_to(self.directory):raise ValueError('Node resource escapes runtime directory')
                    files[path.relative_to(self.directory).as_posix()] = read_data(path)
        extra = deepcopy(self.extension_state)
        if self.snapshot_extra is not None:extra.update(self.snapshot_extra(self))
        files.update(extra.pop('files', {}))
        agents = deepcopy(self.agents)
        for node, image in images.items():
            root = image['root']
            if root is not None:
                files = {name: value for name, value in files.items() if not (
                    self._file(name) == root or image['directory'] and self._file(name).is_relative_to(root))}
            if image['execution'] is None:agents.pop(node, None)
            else:agents[node] = deepcopy(image['execution'])
            files.update({path.relative_to(self.directory).as_posix(): encode_bytes(content)
                          for path, content in image['files'].items()})
        document = dict(version=1, network=network, agents=agents, files=files, **extra)
        return merge_records(document, self.node_locks.records(committing))

    def _notify_commit(self, commit_id):
        if self.commit_observer:
            try:self.commit_observer(commit_id)
            except Exception as error:self.notification_error = str(error)

    def _failed_commit(self):
        self.failed = self.node_locks.failed = True
        self.node_locks._notify()

    def save(self, *, operation_id=None, full=False):
        self.node_locks.wait_prepared_sync()
        while True:
            with self.node_locks.condition, self._transaction_lock:
                if self.failed:raise RuntimeError('Checkpoint failed; restart before further operations')
                self.node_locks._check()
                if self.node_locks._prepared():
                    try:
                        commit_id = self.store.commit(self._snapshot(), operation_id, force_snapshot=full)
                    except BaseException:
                        self._failed_commit()
                        raise
                    break
            self.node_locks.wait_prepared_sync()
        self._notify_commit(commit_id)
        return commit_id

    def commit_node_transaction(self, group):
        if self.failed:raise RuntimeError('Checkpoint failed; restart before further operations')
        try:
            commit_id = self.store.commit(self.snapshot(committing=group))
        except BaseException:
            self._failed_commit()
            raise
        self._notify_commit(commit_id)

    def persistence_info(self):
        from app.persistence.recovery import required_contexts
        with self.node_locks.condition:
            return {**self.store.stats(), 'pending': self.store.pending(),
                    'executor_restore_required': required_contexts(self.store),
                    'bindings': self.node_locks.committed_bindings(), **self.node_locks.context_status()}

    def checkpoint(self, *, contexts, bindings, expected_commit, kind='incremental'):
        with self.node_locks.condition, self._transaction_lock:
            self.node_locks.validate_contexts(contexts)
            if bindings != self.node_locks.committed_bindings() or set(contexts) != set(bindings):
                raise ValueError('Executor bindings changed during cursor capture')
            if type(expected_commit) is not int:raise ValueError('Checkpoint requires an expected core commit')
            if expected_commit != self.store.head:raise RuntimeError('Network changed during executor cursor capture')
            for node, cursor in contexts.items():
                if node not in self.node_locks.exclusive:self.node_locks.snapshots.set_execution_cursor(node, cursor)
            self.save()
            return self.store.mark(contexts, kind, self.store.head, reuse=True)

    def mark(self, *, contexts, kind='incremental', expected_commit=None):
        with self.node_locks.condition, self._transaction_lock:
            self.node_locks.validate_contexts(contexts)
            if set(contexts) != set(self.node_locks.committed_bindings()):
                raise ValueError('Executor cursors must cover exactly all bound Agents')
            return self.store.mark(contexts, kind, expected_commit)

    def restore(self, document):
        if hasattr(self, 'node_locks'):self.node_locks.lifecycle()
        if document.get('version') != 1:raise ValueError('Unsupported checkpoint version')
        # 先校验全部资源地址，再恢复文件。新 DataNode 构造时就使用真实资源。
        files = [(self._file(name), content) for name, content in document['files'].items()]
        for _, content in files:decode_data(content)
        roots = []
        for entry in document['network']['nodes']:
            data = entry.get('data')
            if data is None:continue
            root = (self.directory / data['path']).resolve()
            if root.is_relative_to(self.directory) and data.get('directory'):
                roots.append(root)
        expected = {path for path, _ in files}
        for root in roots:
            root.mkdir(parents=True, exist_ok=True)
            for path in resource_files(root):
                if not path.resolve().is_relative_to(self.directory):raise ValueError('Node resource escapes runtime directory')
                if path not in expected:path.unlink(missing_ok=True)
        for target, content in files:write_data(target, content)
        candidate = self.saver.build(document['network'], self.directory)
        self.agents.clear()
        self.agents.update(deepcopy(document['agents']))
        self.bindings.clear()
        self.bindings.update({entry['node_id']: deepcopy(entry['execution']) for entry in document['network']['nodes']
                              if entry.get('execution') is not None})
        self.extension_state = deepcopy({key: value for key, value in document.items()
            if key not in {'version', 'network', 'agents', 'files', 'tools', 'tool_names', 'node_publications'}})
        self._use_network(candidate)

    def close(self):
        self.store.close()
