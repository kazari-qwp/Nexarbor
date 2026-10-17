"""Lifecycle and asynchronous delegation contracts without paid model calls."""
import json
import time
import unittest
from pathlib import Path
from threading import Event, Thread
import test_application as fixtures
from test_application import NativePort, Backend, Application
from datanet.core.agent_node import AgentNode
from datanet.core.interface import Interface


class LifecycleTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    group = fixtures.ApplicationTests.group

    def agent(self, child='worker', **options):
        self.invoke('datanet_create_agent_channel')
        return self.invoke('datanet_create_agent', dict(child_id=child, **options))

    def detach(self, target, choice):
        self.invoke('datanet_interfaces_channel')
        pending = self.invoke('datanet_interfaces', dict(action='remove', arguments=dict(target_node_id=target)))
        self.assertTrue(pending['awaiting_confirmation'])
        result = self.invoke('datanet_interfaces', dict(action='remove', arguments=dict(confirmation_id=pending['confirmation_id'], choice=choice)))
        self.app.plugins['capabilities/agent_lifecycle'].settle()
        return result

    def test_agent_creation_and_private_memory(self):
        result = self.agent()
        self.assertIsInstance(self.backend.network.nodes[result['node_id']], AgentNode)
        self.invoke('datanet_memory_write', dict(content='记住经验'), result['node_id'])
        self.assertEqual(self.invoke('datanet_memory_read', actor=result['node_id'])['content'], '记住经验')
        self.assertEqual(self.invoke('datanet_memory_read')['content'], '')
        self.assertNotIn('target', self.native.tools[result['node_id']]['datanet_memory_write']['parameters']['properties'])
        with self.assertRaises(ValueError):
            self.backend.dispatch('bind_agent', dict(target='root/project', kind='generic', creator_node_id='root'))

    def test_cancel_is_not_applied(self):
        target = self.agent()['node_id']
        result = self.detach(target, 1)
        self.assertTrue(result['cancelled'])
        self.assertIn(target, self.app.states)
        self.assertTrue(any(edge.target_node_id == target for edge in self.backend.root.interfaces))

    def test_directed_detach_retains_structure_and_reconnects(self):
        parent = self.agent()['node_id']
        child = self.agent('operator', parent_node_id=parent)['node_id']
        self.backend.network.nodes[child].interfaces.append(Interface('root/project', metadata={'channels': ['access.read']}))
        self.detach(parent, 2)
        self.assertNotIn(parent, self.app.states)
        self.assertNotIn(child, self.backend.network.nodes)
        self.assertIn('root/project', self.backend.network.nodes)
        self.assertNotIn(parent, self.backend.lifecycle['pool'])
        self.invoke('datanet_interfaces', dict(action='add', arguments=dict(interface={'metadata':{'channels':['access.read']}}, target_node_id=parent)))
        self.assertIn(child, self.app.states)
        self.assertTrue(any(edge.target_node_id == child for edge in self.backend.network.nodes[parent].interfaces))

    def test_decompose_reuses_identity_session_and_memory(self):
        old = self.agent()
        self.invoke('datanet_memory_write', dict(content='老员工的经验'), old['node_id'])
        self.detach(old['node_id'], 3)
        reused = self.agent('new_worker')
        self.assertTrue(reused['reused'])
        self.assertEqual(reused['node_id'], old['node_id'])
        self.assertEqual(reused['session_id'], old['session_id'])
        self.assertEqual(self.invoke('datanet_memory_read', actor=reused['node_id'])['content'], '老员工的经验')

    def test_customized_agent_is_not_reused(self):
        old = self.agent()
        self.app.plugins['capabilities/agent_runtime'].update_prompt('root', old['node_id'], '定制角色')
        self.detach(old['node_id'], 3)
        new = self.agent('new_worker')
        self.assertFalse(new['reused'])
        self.assertNotEqual(new['node_id'], old['node_id'])

    def test_explicit_creation_options_are_part_of_reuse_match(self):
        old = self.agent(name='专用员工')
        self.detach(old['node_id'], 3)
        self.assertFalse(self.agent('ordinary')['reused'])
        self.assertTrue(self.agent('matching', name='专用员工')['reused'])

    def test_detached_network_has_browsable_folder(self):
        old = self.agent()
        self.invoke('datanet_memory_write', dict(content='归档记忆'), old['node_id'])
        detached = self.detach(old['node_id'], 2)
        folder = Path(detached['directory'])
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['entry_node_id'], old['node_id'])
        self.assertEqual(manifest['status'], 'saved')
        self.assertTrue((folder / 'network.json').exists())
        saved = self.invoke('datanet_presets')['saved_networks']
        self.assertEqual(saved[0]['network_id'], detached['saved_network_id'])
        selected = self.invoke('datanet_presets', dict(archived_network_id=detached['saved_network_id']))['saved_networks'][0]
        self.assertEqual(selected['connected_node_count'], 0)
        self.invoke('datanet_interfaces', dict(action='add', arguments=dict(interface={'metadata':{'channels':['access.read']}}, target_node_id=selected['entry_node_id'])))
        self.assertIn(old['node_id'], self.app.states)

    def test_decomposed_archive_lists_available_employees(self):
        old = self.agent()
        detached = self.detach(old['node_id'], 3)
        selected = self.invoke('datanet_presets', dict(archived_network_id=detached['saved_network_id']))['saved_networks'][0]
        self.assertEqual(selected['status'], 'decomposed')
        self.assertEqual(selected['available_agent_ids'], [old['node_id']])
        self.agent('replacement')
        selected = self.invoke('datanet_presets', dict(archived_network_id=detached['saved_network_id']))['saved_networks'][0]
        self.assertEqual(selected['available_agent_ids'], [])

    def test_discussion_pools_and_reuses_members_without_personal_notebooks(self):
        group = self.group()
        members = set(group['members'])
        self.assertFalse(any(id.endswith('_notes') for id in self.backend.network.nodes))
        self.assertTrue(all(isinstance(self.backend.network.nodes[id], AgentNode) for id in members))
        self.detach(group['group_id'] + '/board', 3)
        self.assertEqual(set(self.backend.lifecycle['pool']), members)
        self.invoke('datanet_create_network_channel', dict(preset='discussion_group'))
        new = self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='new_group', project_nodes=['root/project'], rounds=1))
        self.assertEqual(set(new['members']), members)
        result = self.invoke('datanet_discuss', dict(group_id='new_group', task='复用后的新讨论'))
        self.assertEqual(result['status'], 'ok')

    def test_disk_restore_only_mounts_root_connected_nodes(self):
        old = self.agent()
        self.detach(old['node_id'], 2)
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        self.backend = Backend(self.temp.name)
        self.native = NativePort()
        self.app = Application(self.backend, self.native, dict(rootNetwork='project_root', rootToolboxes=['network_access','network_management'], maxSignalStrength=100))
        self.native.app = self.app
        self.app.plugins['capabilities/tools_network_management'].bind_root('root-session')
        self.assertNotIn(old['node_id'], self.app.states)
        self.assertNotIn(old['node_id'], self.backend.network.nodes)
        self.assertIn(old['node_id'], self.backend.lifecycle['archived'])

    def test_sleep_and_wake_restore_connected_agents(self):
        old = self.agent()
        lifecycle = self.app.plugins['capabilities/agent_lifecycle']
        lifecycle.last_activity = time.monotonic() - lifecycle.idle_seconds - 1
        lifecycle.tick()
        self.assertTrue(self.backend.lifecycle['sleeping'])
        self.assertEqual(set(self.backend.network.nodes), {'root'})
        self.app.event('root', 'agent/pre-step', dict(messages=[]))
        self.assertFalse(self.backend.lifecycle['sleeping'])
        self.assertIn(old['node_id'], self.app.states)
        self.assertEqual(self.backend.agents[old['node_id']]['session_id'], old['session_id'])

    def test_stale_confirmation_does_not_remove_link(self):
        target = self.agent()['node_id']
        self.invoke('datanet_interfaces_channel')
        pending = self.invoke('datanet_interfaces', dict(action='remove', arguments=dict(target_node_id=target)))
        self.agent('another')
        result = self.invoke('datanet_interfaces', dict(action='remove', arguments=dict(confirmation_id=pending['confirmation_id'], choice=3)))
        self.assertTrue(result['stale'])
        self.assertIn(target, self.app.states)

    def test_async_fifo_wait_and_no_sleep_while_busy(self):
        target = self.agent()['node_id']
        entered, release = Event(), Event()
        seen = []
        original = self.app.port
        def port(name, params):
            if name == 'run':
                seen.append(params['text'])
                if params['text'] == 'first':
                    self.native.agents[target]['status'] = 'running'
                    entered.set()
                    if not release.wait(10):
                        raise TimeoutError('Test worker was not released')
                    self.native.agents[target]['status'] = 'idle'
            return original(name, params)
        self.app.port = port
        try:
            first = self.invoke('datanet_call_agent', dict(target=target, task='first'))
            self.assertEqual(first['status'], 'accepted')
            self.assertTrue(entered.wait(3))
            second = self.invoke('datanet_call_agent', dict(target=target, task='second'))
            self.assertNotEqual(first['delegation_id'], second['delegation_id'])
            lifecycle = self.app.plugins['capabilities/agent_lifecycle']
            lifecycle.last_activity = time.monotonic() - lifecycle.idle_seconds - 1
            lifecycle.tick()
            self.assertFalse(self.backend.lifecycle['sleeping'])
            release.set()
            result = self.invoke('datanet_wait_agent', dict(delegation_id=second['delegation_id'], timeout_ms=5000))
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(seen, ['first', 'second'])
            queue = self.app.plugins['capabilities/agent_delegation']
            with self.assertRaises(PermissionError):
                queue.tool_datanet_wait_agent(target, dict(delegation_id=first['delegation_id'], wait=False))
            deadline = time.monotonic() + 3
            while queue.workers and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertFalse(queue.workers)
        finally:
            release.set()

    def test_queue_failure_returns_to_delegator(self):
        target = self.agent()['node_id']
        self.native.failure = '模拟执行错误'
        receipt = self.invoke('datanet_call_agent', dict(target=target, task='fail'))
        result = self.invoke('datanet_wait_agent', dict(delegation_id=receipt['delegation_id'], timeout_ms=5000))
        self.assertEqual(result['status'], 'failed')
        self.assertIn('模拟执行错误', result['result']['error'])

    def test_persistent_queue_restores_on_next_root_turn(self):
        target = self.agent()['node_id']
        queue = self.app.plugins['capabilities/agent_delegation']
        queue.start_worker = lambda target: None
        queued = self.invoke('datanet_call_agent', dict(target=target, task='重启后执行'))
        interrupted = self.invoke('datanet_call_agent', dict(target=target, task='中断委托'))
        queue.jobs[interrupted['delegation_id']]['status'] = 'running'
        queue.store.save()
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        self.backend = Backend(self.temp.name)
        self.native = NativePort()
        self.app = Application(self.backend, self.native, dict(rootNetwork='project_root', rootToolboxes=['network_access', 'network_management'], maxSignalStrength=100))
        self.native.app = self.app
        self.app.plugins['capabilities/tools_network_management'].bind_root('root-session')
        self.app.event('root', 'agent/pre-step', dict(messages=[]))
        result = self.invoke('datanet_wait_agent', dict(delegation_id=queued['delegation_id'], timeout_ms=5000))
        self.assertEqual(result['status'], 'completed')
        result = self.invoke('datanet_wait_agent', dict(delegation_id=interrupted['delegation_id'], wait=False))
        self.assertEqual(result['status'], 'interrupted')

    def test_lifecycle_and_delegation_components_can_be_unplugged(self):
        self.app.disable('capabilities/agent_delegation')
        self.app.disable('capabilities/agent_lifecycle')
        target = self.agent()['node_id']
        self.assertIsInstance(self.backend.network.nodes[target], AgentNode)
        result = self.invoke('datanet_call_agent', dict(target=target, task='使用基础委托'))
        self.assertEqual(result['status'], 'ok')
        self.assertNotIn('datanet_wait_agent', self.native.tools['root'])

    def test_decomposition_removes_dangling_links_from_other_archives(self):
        first = self.agent()['node_id']
        self.invoke('datanet_create_node_channel')
        self.invoke('datanet_create_node', dict(child_id='shared', node_spec=dict(type='value', parameters=dict(value=7))))
        self.backend.network.nodes[first].interfaces.append(Interface('root/shared', metadata={'channels': ['access.read']}))
        self.detach(first, 2)
        self.detach('root/shared', 3)
        self.invoke('datanet_interfaces', dict(action='add', arguments=dict(interface={'metadata':{'channels':['access.read']}}, target_node_id=first)))
        self.assertFalse(self.backend.network.nodes[first].interfaces)


if __name__ == '__main__':
    unittest.main()
