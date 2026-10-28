"""原滑动窗口规则、真实Module工具和状态恢复。"""
import asyncio
from pathlib import Path
from jsonschema.exceptions import ValidationError
import unittest
from app.studio.testing import ModuleHarness

ROOT = Path(__file__).resolve().parents[1]

class NumberWindowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(ROOT / 'projects/workbench/modules/number_window')
        self.addAsyncCleanup(self.h.close)
        self.h.add_node('measurements')
        self.module = self.h.mount('measurements')

    async def test_empty_window_eviction_statistics_and_runtime_resize(self):
        self.assertEqual(await self.module.read(), {'count': 0, 'min': None, 'max': None, 'mean': None, 'window_size': 3, 'values': []})
        for value in [1, 2, 3, 4]:
            await self.module.push(value)
        self.assertEqual(await self.module.read(), {'count': 3, 'min': 2, 'max': 4, 'mean': 3, 'window_size': 3, 'values': [2, 3, 4]})
        self.module.config['window_size'] = 1
        self.assertEqual((await self.module.read())['values'], [4])
        self.module.config['window_size'] = True
        self.assertEqual((await self.module.read())['window_size'], 3)

    async def test_retry_conflict_and_bounded_receipt_history(self):
        for value in range(205):
            await self.module.push(value, key=str(value))
        self.assertEqual(len(self.module.state['receipts']), 200)
        self.assertEqual(self.module.state['receipts'][0]['key'], '5')
        self.assertTrue((await self.module.push(204, key='204'))['duplicate'])
        before = list(self.module.state['window'])
        with self.assertRaisesRegex(ValueError, '相同请求键'):
            await self.module.push(205, key='204')
        self.assertEqual(self.module.state['window'], before)
        self.assertFalse((await self.module.push(0, key='0'))['duplicate'])

    async def test_finite_numbers_and_nonempty_request_keys(self):
        for value in [True, '1', None, float('nan'), float('inf'), -float('inf')]:
            with self.assertRaisesRegex(ValueError, '有限数字'):
                await self.module.push(value)
        for key in ['', False, 3]:
            with self.assertRaisesRegex(ValueError, '请求键'):
                await self.module.push(1, key=key)
        self.assertEqual((await self.module.read())['values'], [])

    async def test_remote_channel_gate_real_tools_and_restore(self):
        self.h.add_node('caller')
        self.h.connect('caller', 'measurements', channels=['measurement'], threshold=2)
        for channels, strength in [(['other'], 2), (['measurement'], 1)]:
            with self.assertRaises(PermissionError):
                await self.h.call('measurements', 'read', actor='caller', channels=channels, strength=strength)
        pushed = await self.h.call('measurements', 'push', {'value': 2.5, 'key': 'one'}, actor='caller', channels=['measurement'], strength=2)
        self.assertEqual(pushed['data']['mean'], 2.5)
        tools = list(self.module.tools)
        self.assertEqual(len(tools), 2)
        await tools[0].invoke(value=3.5, key='two')
        snapshot = self.h.backend.snapshot()
        self.h.backend.restore(snapshot)
        restored = self.h.network.get('measurements').modules.get('number.window')
        self.assertTrue((await list(restored.tools)[0].invoke(value=3.5, key='two'))['duplicate'])
        self.assertEqual((await list(restored.tools)[1].invoke())['values'], [2.5, 3.5])

    async def test_contract_concurrent_retries_and_instance_isolation(self):
        for parameters in [{}, {'value': '1'}, {'value': True}, {'value': 1, 'unknown': 2}, {'value': 1, 'key': ''}]:
            with self.assertRaises(ValidationError):
                await self.h.call('measurements', 'push', parameters)
        with self.assertRaises(ValidationError):
            await self.h.call('measurements', 'read', {'unexpected': 1})
        results = await asyncio.gather(*(self.h.call('measurements', 'push', {'value': 4.5, 'key': 'concurrent'}) for _ in range(6)))
        self.assertEqual(sum(not result['data']['duplicate'] for result in results), 1)
        self.assertTrue(all(result['data']['count'] == 1 for result in results))
        self.h.add_node('independent')
        other = self.h.mount('independent', config={'window_size': 2})
        self.assertEqual((await other.read())['values'], [])
        for value in [1, 2, 3]:
            await other.push(value)
        self.assertEqual((await other.read())['values'], [2, 3])
        self.assertEqual((await other.read())['mean'], 2.5)
        self.assertEqual((await self.module.read())['values'], [4.5])
