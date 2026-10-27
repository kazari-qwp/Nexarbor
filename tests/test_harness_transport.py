"""宿主入口保留恢复门禁、逆向 owner ticket 与事务日志约束。"""

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adapt.harness.backend.transport import Transport
from app.persistence.recovery import restore_bundle
from app.runtime.backend import Backend

ROOT = Path(__file__).resolve().parents[1]


class HarnessTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.rpc-', dir=ROOT / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def transport(self, name='runtime'):
        backend = Backend(self.directory / name)
        transport = Transport(backend, StringIO())
        self.addCleanup(transport.close)
        return transport

    def test_prepare_bind_and_ack_commit_through_new_runtime(self):
        transport = self.transport()
        backend = transport.backend
        backend.network.get('root').update_inputs('rpc', inputs=[dict(id='one', text='event')])
        view = transport.dispatch('executor_prepare', dict(actor='root'))
        self.assertEqual([tool['name'] for tool in view['tools']], ['memory_query', 'memory_modify', 'memory_append'])
        transport.dispatch('executor_bind', dict(actor='root', session_id='native'))
        transport.dispatch('executor_ack', dict(actor='root', executor_session_id='native', events=[dict(source='rpc', id='one')]))
        state = backend.store.latest()
        self.assertEqual(state['agents']['root']['session_id'], 'native')
        self.assertEqual(state['network']['nodes'][0]['agent']['inputs']['rpc']['inputs'][0]['status'], 'delivered')
        self.assertEqual(backend.store.pending(), [])

    def test_expired_native_ticket_is_not_a_business_access_grant(self):
        transport = self.transport()
        with self.assertRaises(PermissionError):
            transport.dispatch('executor_prepare', dict(actor='root', node_access_ticket='expired'))
        self.assertEqual(transport.backend.store.pending(), [])

    def test_pending_recovery_blocks_agent_mount_and_read_before_acknowledgement(self):
        transport = self.transport()
        backend = transport.backend
        backend.agents['root'] = {'session_id': 'old'}
        backend.save()
        point = backend.mark(contexts={'root': dict(session_id='old', seq=1)})
        restore_bundle(backend.store.bundle(point['id']), self.directory / 'branch')
        branch = self.transport('branch')
        for method in ('executor_run', 'executor_prepare', 'executor_bind', 'executor_read'):
            with self.subTest(method=method), self.assertRaisesRegex(RuntimeError, 'restored'):
                branch.dispatch(method, dict(actor='root', session_id='must-not-mount'))
        branch.dispatch('persistence_executor_restored', dict(sessions={'root': 'restored'}))
        self.assertEqual(branch.dispatch('executor_prepare', dict(actor='root'))['actor'], 'root')
