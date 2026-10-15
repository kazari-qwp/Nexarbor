"""Exercise Python-owned workflows through a fake native session port, without a model."""
import os, sys, json, unittest, tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
os.environ['DATANET_PRODUCT_ROOT'] = str(ROOT)
os.environ['DATANET_COMPONENT_ROOT'] = str(ROOT / 'extensions/multi_agent')
sys.path.insert(0, str(ROOT / 'adapters/harness/backend'))
import config
from server import Backend
from datanet.core.application import Application


class NativePort:
    def __init__(self):
        self.agents = {'root': dict(session_id='root-session', status='idle', options={})}
        self.documents, self.tools, self.messages, self.calls = {}, {}, {}, []
        self.app = None
        self.failure = None

    def __call__(self, name, p):
        self.calls.append((name, p))
        actor = p.get('actor')
        if name == 'component-extension':
            return {'ok': True}
        if name == 'tools':
            self.tools[actor] = {d['name']: d for d in p['definitions']}
            return {'ok': True}
        if name == 'load-document':
            key = (actor, p['document'])
            before = self.documents.get(key)
            self.documents[key] = p['text']
            return before != p['text']
        if name == 'document-present':
            return (actor, p['document']) in self.documents
        if name == 'inspect':
            return self.agents[actor]
        if name == 'create':
            self.agents[actor] = dict(session_id=p['binding']['session_id'], status='idle', options=p['binding']['agentOptions'])
            return self.agents[actor]
        if name == 'make-message':
            return dict(id=str(uuid4()), role='user', content=[dict(type='text', text=p['text'])])
        if name == 'steer':
            self.messages.setdefault(actor, []).append(p.get('message', dict(id=str(uuid4()), role='user', content=[dict(type='text', text=p['text'])]) if 'text' in p else p['message']))
            return {'ok': True}
        if name in ('messages', 'inbox-snapshot'):
            return self.messages.get(actor, [])
        if name in ('view-update', 'conclude', 'capabilities', 'cancel-agent'):
            return {'ok': True}
        if name == 'dispose-agent':
            self.agents.pop(actor)
            return {'ok': True}
        if name == 'run':
            if self.failure:
                raise RuntimeError(self.failure)
            discussion = self.app.plugins['capabilities/discussion_group']
            turn = discussion.turns.get(actor)
            if turn and turn['final']:
                self.app.invoke(actor, 'node_write', dict(target=turn['expected_output'], key='content', value='全部测试完成'))
            elif turn:
                self.app.invoke(actor, 'submit_round', dict(content='测试'))
            message = dict(id=str(uuid4()), role='assistant', content=[dict(type='text', text='完成')])
            self.messages.setdefault(actor, []).append(message)
            return dict(messages=[message], session_id=self.agents[actor]['session_id'])
        raise AssertionError(name)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        from datanet.core import component_registry
        component_registry._enabled = None
        test_directory = ROOT / 'build/test-data'
        test_directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_directory)
        self.backend = Backend(self.temp.name)
        self.native = NativePort()
        self.app = Application(self.backend, self.native, dict(rootNetwork='project_root', rootToolboxes=['network_access', 'node_creation', 'agent_management', 'interface_management', 'discussion', 'self_repair', 'network_management_skill'], maxSignalStrength=100))
        self.native.app = self.app
        self.app.plugins['capabilities/tools_network_management'].bind_root('root-session')

    def tearDown(self):
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        resolved = Path(self.temp.name).resolve()
        assert resolved.is_relative_to((ROOT / 'build/test-data').resolve())
        if os.name == 'nt':
            self.temp.name = '\\\\?\\' + str(resolved)
        self.temp.cleanup()

    def invoke(self, name, p=None, actor='root'):
        return self.app.invoke(actor, name, p or {})

    def test_management_skill_registers_new_channel_entries(self):
        state = self.app.state('root')
        state['grant'] = self.app.resolve(['node_operations', 'network_management_skill'])
        state['dynamic'].clear()
        state['channels'].clear()
        self.app.refresh('root')
        self.assertNotIn('datanet_create_node_channel', self.native.tools['root'])
        self.invoke('datanet_skill', dict(action='load', name='network_management'))
        self.assertIn('datanet_create_node_channel', self.native.tools['root'])
        self.assertNotIn('datanet_create_node', self.native.tools['root'])
        self.invoke('datanet_create_node_channel')
        self.assertIn('datanet_create_node', self.native.tools['root'])
        self.invoke('datanet_skill', dict(action='load', name='network_management'))
        self.assertIn('datanet_create_node', self.native.tools['root'])

    def group(self):
        self.invoke('datanet_create_network_channel', dict(preset='discussion_group'))
        return self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='test', project_nodes=['root/project', 'root/progress'], rounds=1))

    def test_python_discussion_and_report_permissions(self):
        group = self.group()
        for member in group['members']:
            self.assertIn('submit_round', self.native.tools[member])
            self.assertNotIn('datanet_send_message', self.native.tools[member])
        result = self.invoke('datanet_discuss', dict(group_id=group['group_id'], task='每个人输出测试然后归档'))
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['output'][0]['content'], '全部测试完成')
        self.assertTrue(self.backend.groups['test']['completed'])
        recorder = group['recorder_id']
        self.invoke('datanet_reports_channel', actor=recorder)
        root_id = result['report_reference']['root_request_id']
        index = self.invoke('datanet_report_read', dict(root_request_id=root_id, path='node-index.json', limit=20000), recorder)
        self.assertTrue(all(member in json.loads(index['content'])['nodes'] for member in group['members']))
        self.assertEqual(self.invoke('datanet_discuss', dict(group_id='test'))['status'], 'ok')

    def test_message_reply_once_and_resident_tail(self):
        group = self.group()
        member = group['members'][2]
        receipt = self.invoke('datanet_send_message', dict(target=member, content='请回复'))
        message = self.app.plugins['capabilities/agent_messaging'].store.data['messages'][receipt['message_id']]
        reply = message['reply_tool']
        self.assertEqual(self.native.tools[member][reply]['description'], '仅用来回复此条消息，调用一次后失效')
        self.invoke(reply, dict(content='已收到'), member)
        with self.assertRaises(PermissionError):
            self.invoke(reply, dict(content='再回复'), member)
        with self.assertRaises(PermissionError):
            self.invoke('datanet_send_message', dict(target='root', content='主动消息'), member)
        recorder = group['recorder_id']
        self.invoke('write_resident_text', dict(content='简短笔记'), recorder)
        payload = dict(actor=member, texts=[])
        for owner, handler in self.app.listeners['context/tail']:
            handler(payload)
        self.assertIn('简短笔记', '\n'.join(payload['texts']))
        self.assertNotIn('简短笔记', json.dumps(self.native.messages, ensure_ascii=False))
        query = next(name for name in self.native.tools[member] if name.startswith('query_text_'))
        self.assertTrue(self.invoke(query, actor=member)['instructions_added'])
        self.assertFalse(self.invoke(query, actor=member)['instructions_added'])
        self.native.documents.clear()
        self.assertTrue(self.invoke(query, actor=member)['instructions_added'])

    def test_failure_channel_and_cumulative_limit(self):
        group = self.group()
        member = group['members'][2]
        self.assertNotIn('datanet_resolve_feedback', self.native.tools['root'])
        self.invoke('handle_problem', dict(problem='没有终端工具', origin='self'), member)
        self.invoke('experience_query', actor=member)
        self.invoke('datanet_feedback', dict(category='missing_tool', task_blocker='无法操作终端完成当前委托'), member)
        self.assertIn('datanet_resolve_feedback', self.native.tools['root'])
        self.assertIn(('root', 'tool:datanet_resolve_feedback'), self.native.documents)
        self.invoke('handle_problem', dict(problem='下属未完成操作', origin='subordinate', origin_node_id=member))
        self.invoke('problem_defer', dict(reason='下属没有工具', impact='操作部分未完成', continuation='当前任务允许正常报告失败'))
        self.assertFalse(self.app.plugins['capabilities/problem_handling'].active('root'))
        self.assertEqual(len(self.backend.feedback), 1)
        problem = self.app.plugins['capabilities/problem_handling']
        for _ in range(3):
            problem.reserve('root', member, 'execute')
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY_LIMIT_REACHED'):
            problem.reserve('root', member, 'execute')
        removed = self.app.disable('capabilities/experience')
        self.assertIn('capabilities/problem_handling', removed)
        with self.assertRaises(PermissionError):
            self.invoke('datanet_resolve_feedback', dict(target=member, action='inspect'))
        self.assertIn('node_read', self.native.tools['root'])

    def test_reports_unplug_keeps_execution_and_discussion(self):
        self.app.disable('capabilities/reports')
        group = self.group()
        result = self.invoke('datanet_discuss', dict(group_id=group['group_id'], task='独立于报告模块完成讨论'))
        self.assertEqual(result['status'], 'ok')
        self.assertIsNone(result['report_reference'])
        self.assertEqual(result['output'][0]['content'], '全部测试完成')
        records = self.app.plugins['capabilities/execution_records']
        self.assertTrue(records.last_completed)
        self.assertNotIn('capabilities/reports', self.app.plugins)


if __name__ == '__main__':
    unittest.main()
