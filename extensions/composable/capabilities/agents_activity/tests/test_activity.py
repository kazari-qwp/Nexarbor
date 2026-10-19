import asyncio
import contextvars
import json
import unittest
from pathlib import Path

from jsonschema.exceptions import ValidationError

from datanet.core.module_protocol import ComponentResult, ModuleDefinition
from datanet.studio.testing import ModuleHarness


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node('npc', name='测试角色', agent=True)
        self.node = self.h.network.nodes['npc']
        self.records = self.h.mount(
            'npc',
            module='records.store',
            config={'initial': {'ap': 3}, 'minimum': {}},
            access={'strength': 2, 'channels': ['records']},
        )
        self.place = self.h.mount(
            'npc',
            module='place.info',
            config={'location': None, 'description': '测试广场', 'visitors': []},
            access={'strength': 2, 'channels': ['movement']},
        )
        self.context = self.h.mount(
            'npc',
            module='agents.context',
            config={'persona': '谨慎的守夜人', 'opening': '集合时间到了', 'common': '测试世界'},
            access={'strength': 2, 'channels': ['self', 'records', 'movement']},
        )
        self.calls = []
        self.lock_available = None
        self.prepare_before_run = None

    async def asyncTearDown(self):
        await self.h.close()

    def mount_activity(self, config=None, state=None):
        activity_config = {
            'signal_channels': ['tick'],
            'budget_field': 'ap',
            'budget': 10,
            'prompt': '现在开始你这一时刻的行动。',
            'enabled': True,
        }
        if config:
            activity_config.update(config)
        return self.h.mount(
            'npc',
            config=activity_config,
            state=state or {},
            access={'strength': 3, 'channels': ['records', 'self', 'runtime.agent', 'tick', 'activity']},
        )

    def mount_example(self, enabled=None):
        example = json.loads(
            (Path(__file__).resolve().parents[1] / 'example.json').read_text(encoding='utf-8'))
        config = dict(example['config'])
        if enabled is not None:
            config['enabled'] = enabled
        return self.h.mount(
            'npc',
            config=config,
            state={},
            access=dict(example['access']),
        )

    def install_runtime(self, failing=False):
        async def execute(actor, name, args):
            self.calls.append({'actor': actor, 'name': name, 'args': dict(args)})
            self.lock_available = False
            async with self.h.network.node_locks.transaction(
                    'npc', ['npc'], strength=0, timeout=2):
                self.lock_available = True
            self.prepare_before_run = bool(self.context.state.get('opening_queued'))
            if failing:
                raise RuntimeError('模拟模型运行失败')
            return {'ok': True, 'message': args.get('message')}

        self.h.register_tools(
            'runtime',
            [{
                'name': 'agent_run',
                'description': '测试用本节点 Agent 运行端口',
                'parameters': {
                    'type': 'object',
                    'properties': {'message': {'type': 'string'}},
                    'required': ['message'],
                    'additionalProperties': False,
                },
            }],
            execute,
        )
        self.node.offered_tools = [{
            'ref': 'runtime:agent_run',
            'channels': ['runtime.agent'],
        }]

    async def activate(self, key):
        return await self.h.call('npc', 'activate', {'key': key}, channels=['tick'])

    async def records_values(self):
        result = await self.h.call(
            'npc', 'read', {}, module='records.store', channels=['records'])
        self.assertEqual(result['status'], 'ok', result)
        return result['data']['values']

    async def set_ap(self, value):
        result = await self.h.call(
            'npc', 'apply', {'set': {'ap': value}},
            module='records.store', channels=['records'])
        self.assertEqual(result['status'], 'ok', result)

    async def test_different_key_cannot_start_a_second_model_on_same_node(self):
        self.mount_activity();started,release=asyncio.Event(),asyncio.Event()
        async def execute(actor,name,args):started.set();await release.wait();return {'ok':True}
        self.h.register_tools('runtime',[{'name':'agent_run','description':'测试模型','parameters':{'type':'object'}}],execute)
        self.node.offered_tools=[{'ref':'runtime:agent_run','channels':['runtime.agent']}]
        first=asyncio.create_task(self.activate('first'));await started.wait()
        second=await self.activate('second');self.assertEqual(second['status'],'error');self.assertIn('重叠',second['error'])
        release.set();self.assertEqual((await first)['status'],'ok')

    async def test_repeated_notifications_are_bounded_and_do_not_reset_budget(self):
        from datanet.core.signal_work import current_work
        activity=self.mount_activity(config={'max_reactions':2});calls=[]
        async def execute(actor,name,args):
            calls.append(actor)
            await self.set_ap(7)
            result=await self.h.call('npc','notify',{'key':current_work.get().signal_id},channels=['activity'])
            self.assertEqual(result['status'],'ok')
            return {'ok':True}
        self.h.register_tools('runtime',[{'name':'agent_run','description':'测试模型','parameters':{'type':'object'}}],execute)
        self.node.offered_tools=[{'ref':'runtime:agent_run','channels':['runtime.agent']}]
        self.h.add_node('source');self.h.connect('source','npc',channels=['tick'])
        await self.h.emit('source',['tick'])
        self.assertEqual(len(calls),3);self.assertEqual((await self.records_values())['ap'],7)
        self.assertEqual(activity.state['completed_total'],1);self.assertFalse(activity.state['activities'][-1]['pending'])

    async def test_01_信号触发重置预算_准备上下文_再运行且无独占锁(self):
        activity = self.mount_activity()
        self.install_runtime()
        self.h.add_node('source', name='信号源')
        self.h.add_node('observer', name='后继观察者')
        observer = self.h.mount(
            'observer',
            module='clock.counter',
            config={'signal_channels': ['tick'], 'initial_tick': 0},
            access={'strength': 1, 'channels': ['tick']},
        )
        self.h.connect('source', 'npc', channels=['tick'])
        self.h.connect('npc', 'observer', channels=['tick'])

        await self.h.emit('source', ['tick'], strength=3, content={'tick': 1})

        self.assertEqual(len(self.calls), 1, self.calls)
        self.assertEqual(self.calls[0]['actor'], 'npc')
        self.assertEqual(self.calls[0]['args']['message'], '现在开始你这一时刻的行动。')
        self.assertIs(self.lock_available, True, '运行回调时不应持有本节点独占锁')
        self.assertIs(self.prepare_before_run, False, '活动模块不得绕过执行器偷偷准备角色上下文')
        values = await self.records_values()
        self.assertEqual(values['ap'], 10)
        self.assertEqual(observer.state['tick'], 1)
        self.assertEqual(activity.state['completed_total'], 1)
        self.assertEqual(activity.state['activities'][0]['status'], 'completed')

    async def test_02_相同完成键重复不重置预算且不调用模型(self):
        activity = self.mount_activity()
        self.install_runtime()

        first = await self.activate('same-key')
        self.assertEqual(first['status'], 'ok', first)
        self.assertFalse(first['data']['duplicate'])
        await self.set_ap(3)

        second = await self.activate('same-key')

        self.assertEqual(second['status'], 'ok', second)
        self.assertTrue(second['data']['duplicate'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((await self.records_values())['ap'], 3)
        self.assertEqual(activity.state['completed_total'], 1)

    async def test_03_不同活动键继续重置预算并再次运行(self):
        self.mount_activity()
        self.install_runtime()

        first = await self.activate('key-one')
        self.assertEqual(first['status'], 'ok', first)
        await self.set_ap(3)
        second = await self.activate('key-two')

        self.assertEqual(second['status'], 'ok', second)
        self.assertFalse(second['data']['duplicate'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual((await self.records_values())['ap'], 10)
        self.assertEqual(second['data']['completed_total'], 2)

    async def test_04_缺少runtime授权时信号失败且后继不运行(self):
        activity = self.mount_activity()
        self.h.add_node('source', name='信号源')
        self.h.add_node('observer', name='后继观察者')
        observer = self.h.mount(
            'observer',
            module='clock.counter',
            config={'signal_channels': ['tick'], 'initial_tick': 0},
            access={'strength': 1, 'channels': ['tick']},
        )
        self.h.connect('source', 'npc', channels=['tick'])
        self.h.connect('npc', 'observer', channels=['tick'])

        try:
            await self.h.emit('source', ['tick'], strength=3, content={})
        except Exception:
            pass

        self.assertEqual(len(self.calls), 0)
        self.assertEqual(observer.state.get('tick', 0), 0)
        self.assertEqual(activity.state['activities'][0]['status'], 'failed')
        self.assertIn('runtime:agent_run', activity.state['activities'][0]['error'])
        self.assertEqual(activity.state.get('completed_total', 0), 0)

    async def test_05_禁用后跳过且不扣预算不调用模型(self):
        activity = self.mount_activity(config={'enabled': False})
        self.install_runtime()

        result = await self.activate('disabled-key')

        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['status'], 'skipped')
        self.assertEqual(result['data']['reason'], '角色活动已禁用')
        self.assertEqual(len(self.calls), 0)
        self.assertEqual((await self.records_values())['ap'], 3)
        self.assertEqual(activity.state.get('activities', []), [])

    async def test_06_失败后保留failed且相同键不自动重放(self):
        activity = self.mount_activity()
        self.install_runtime(failing=True)

        first = await self.activate('failed-key')
        self.assertEqual(first['status'], 'error', first)
        self.assertEqual(len(self.calls), 1)
        await self.set_ap(4)

        second = await self.activate('failed-key')

        self.assertEqual(second['status'], 'error', second)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((await self.records_values())['ap'], 4)
        self.assertEqual(activity.state['activities'][0]['status'], 'failed')
        self.assertIn('模拟模型运行失败', activity.state['activities'][0]['error'])
        self.assertEqual(activity.state.get('completed_total', 0), 0)

    async def test_07_运行中键拒绝重放且不调用模型(self):
        activity = self.mount_activity(state={'activities': [{
            'key': 'busy-key',
            'status': 'running',
            'completed_count': 0,
        }]})
        self.install_runtime()

        result = await self.activate('busy-key')

        self.assertEqual(result['status'], 'error', result)
        self.assertIn('正在执行', result['error'])
        self.assertEqual(len(self.calls), 0)
        self.assertEqual((await self.records_values())['ap'], 3)
        self.assertEqual(activity.state['activities'][0]['status'], 'running')

    async def test_08_空活动键在预检阶段被拒绝(self):
        self.mount_activity()
        self.install_runtime()

        with self.assertRaises(ValidationError):
            await self.h.call('npc', 'activate', {'key': ''}, channels=['tick'])

        self.assertEqual(len(self.calls), 0)

    async def test_09_按example装配收到tick会明确skip且不调用模型(self):
        activity = self.mount_example()
        self.install_runtime()
        self.h.add_node('source', name='信号源')
        self.h.connect('source', 'npc', channels=['tick'])

        report = await self.h.emit('source', ['tick'], strength=3, content={'tick': 1})

        self.assertIsNotNone(report)
        self.assertEqual(len(self.calls), 0)
        self.assertEqual((await self.records_values())['ap'], 3)
        self.assertEqual(activity.state.get('activities', []), [])
        self.assertEqual(activity.state.get('completed_total', 0), 0)

    async def test_10_显式启用后按原行为运行模型(self):
        activity = self.mount_example(enabled=True)
        self.install_runtime()
        self.h.add_node('source', name='信号源')
        self.h.connect('source', 'npc', channels=['tick'])

        await self.h.emit('source', ['tick'], strength=3, content={'tick': 1})

        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]['actor'], 'npc')
        self.assertEqual(self.calls[0]['args']['message'], '现在开始你这一时刻的行动。')
        self.assertIs(self.lock_available, True)
        self.assertIs(self.prepare_before_run, False)
        self.assertEqual((await self.records_values())['ap'], 10)
        self.assertEqual(activity.state['completed_total'], 1)
        self.assertEqual(activity.state['activities'][0]['status'], 'completed')

    async def test_11_A等待B聊天时B完成记录不形成独占锁依赖环(self):
        self.h.add_node('a', name='角色甲', agent=True)
        self.h.add_node('b', name='角色乙', agent=True)
        for node_id, persona in (('a', '甲'), ('b', '乙')):
            self.h.mount(
                node_id,
                module='records.store',
                config={'initial': {'ap': 3}, 'minimum': {}},
                access={'strength': 2, 'channels': ['records']},
            )
            self.h.mount(
                node_id,
                module='place.info',
                config={'location': None, 'description': '测试广场', 'visitors': []},
                access={'strength': 2, 'channels': ['movement']},
            )
            self.h.mount(
                node_id,
                module='agents.context',
                config={'persona': persona, 'opening': '开始', 'common': '测试世界'},
                access={'strength': 2, 'channels': ['self', 'records', 'movement']},
            )

        b_model_started = asyncio.Event()
        a_chat_entered = asyncio.Event()
        b_activity_done = asyncio.Event()

        async def peer_execute(ctx, activation):
            if activation.kind == 'access' and activation.operation == 'chat':
                a_chat_entered.set()
                # A 的聊天调用进入 B 后，等待 B 整轮 activity 回调和完成记录退出。
                await b_activity_done.wait()
                return ComponentResult(data={'ok': True})
            return ComponentResult(status='error', error='不支持的请求')

        self.h.modules.factories['test.peer'] = ModuleDefinition(
            peer_execute,
            operations=[{
                'name': 'chat',
                'channels': ['chat'],
                'parameters': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {},
                },
                'result': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {'ok': {'type': 'boolean'}},
                },
            }],
        )
        self.h.mount(
            'b',
            module='test.peer',
            config={},
            access={'strength': 2, 'channels': ['chat']},
        )
        self.h.connect('a', 'b', channels=['chat'])

        def activity_config():
            return {
                'signal_channels': ['tick'],
                'budget_field': 'ap',
                'budget': 10,
                'prompt': '执行这一时刻。',
                'enabled': True,
            }

        activity_a = self.h.mount(
            'a',
            config=activity_config(),
            state={},
            access={'strength': 3, 'channels': ['records', 'self', 'runtime.agent', 'tick', 'activity']},
        )
        activity_b = self.h.mount(
            'b',
            config=activity_config(),
            state={},
            access={'strength': 3, 'channels': ['records', 'self', 'runtime.agent', 'tick', 'activity']},
        )

        # 仿官方端口：从工具回调发起外部调用前清理宿主调用上下文。
        external_call_context = contextvars.Context()

        async def execute(actor, name, args):
            if actor == 'b':
                b_model_started.set()
                # B 的模型部分先结束，但必须先等 A 真正进入 B 的聊天调用。
                await a_chat_entered.wait()
                return {'ok': True, 'message': args.get('message')}
            call_task = external_call_context.run(
                asyncio.create_task,
                self.h.call(
                    'b', 'chat', {}, actor='a', strength=2, channels=['chat'],
                    module='test.peer'),
            )
            await call_task
            return {'ok': True, 'message': args.get('message')}

        self.h.register_tools(
            'runtime',
            [{
                'name': 'agent_run',
                'description': '测试用本节点 Agent 运行端口',
                'parameters': {
                    'type': 'object',
                    'properties': {'message': {'type': 'string'}},
                    'required': ['message'],
                    'additionalProperties': False,
                },
            }],
            execute,
        )
        for node_id in ('a', 'b'):
            self.h.network.nodes[node_id].offered_tools = [{
                'ref': 'runtime:agent_run',
                'channels': ['runtime.agent'],
            }]

        b_task = asyncio.create_task(self.h.call(
            'b', 'activate', {'key': 'b-key'}, channels=['tick']))
        started = asyncio.create_task(b_model_started.wait())
        done, _ = await asyncio.wait(
            {b_task, started}, timeout=2,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if b_task in done:
            self.fail(f'B 活动在模型开始前结束：{b_task.result()}')
        self.assertIn(started, done, 'B 的模型部分没有开始')
        a_task = asyncio.create_task(self.h.call(
            'a', 'activate', {'key': 'a-key'}, channels=['tick']))
        try:
            await asyncio.wait_for(b_task, timeout=3)
        except asyncio.TimeoutError:
            a_task.cancel()
            self.fail('B 完成记录等待 A 已进入的 B 聊天调用，形成依赖环')
        b_activity_done.set()
        a_result = await asyncio.wait_for(a_task, timeout=3)

        self.assertEqual(a_result['status'], 'ok', a_result)
        self.assertEqual(activity_a.state['activities'][0]['status'], 'completed')
        self.assertEqual(activity_b.state['activities'][0]['status'], 'completed')
        self.assertEqual(activity_a.state['completed_total'], 1)
        self.assertEqual(activity_b.state['completed_total'], 1)


if __name__ == '__main__':
    unittest.main()
