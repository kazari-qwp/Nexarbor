"""原小镇时钟：去重、一天五 tick、事务回滚与锁外重试存档。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from domain.core import MarkdownNode, Network, NodeInfo
from projects.npc_town.modules.clock_counter import ClockCounterModule
from projects.npc_town.modules.periodic_checkpoint import PeriodicCheckpointModule
from projects.npc_town.modules.world_time import WorldTimeModule

ROOT = Path(__file__).resolve().parents[1]


class TownClockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.town-clock-', dir=ROOT / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.file = self.home / 'time.md'
        self.file.write_text('before', encoding='utf-8')
        self.node = MarkdownNode(NodeInfo('time', 'Time'), self.file)
        self.saver = NetworkSaver()
        self.backend = Backend(self.home, network=Network([self.node]), saver=self.saver)
        self.addCleanup(self.backend.close)
        self.saved = []
        self.fail_save = False

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    async def checkpoint(self, *, full):
        self.assertIsNone(self.backend.node_locks.current)
        self.saved.append(full)
        if self.fail_save:raise OSError('checkpoint fixture failure')
        await self.backend.node_locks.wait_prepared()
        self.backend.save(full=full)

    def clock(self, config=None):
        module = ClockCounterModule(self.transaction, self.checkpoint, config)
        self.saver.tables.module_types['clock.counter'] = lambda spec: ClockCounterModule(self.transaction, self.checkpoint)
        self.node.install(module)
        return module

    async def test_five_unique_ticks_complete_one_day_and_publish_original_clock(self):
        module = self.clock({'write_text': True, 'checkpoint_every': 5})
        for index in range(1, 6):value = await module.receive('tick-' + str(index))
        self.assertEqual(value, dict(tick=5, day=1, slot='夜晚'))
        self.assertEqual(self.file.read_text(encoding='utf-8'), '第1天 夜晚')
        self.assertEqual(module.published, value)
        self.assertEqual(self.saved, [True])
        self.assertFalse(module.state['pending_checkpoint'])
        self.assertEqual(await module.receive('tick-5'), value)
        self.assertEqual(self.saved, [True])
        self.assertEqual(await module.receive('tick-6'), dict(tick=6, day=2, slot='清晨'))

    async def test_write_failure_rolls_back_counter_receipt_publication_and_file(self):
        module = self.clock({'write_text': True})
        with patch.object(self.node.dataer, 'write', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):await module.receive('one')
        self.assertEqual(module.state, {})
        self.assertEqual(module.published, {})
        self.assertEqual(self.file.read_text(encoding='utf-8'), 'before')
        self.assertEqual((await module.receive('one'))['tick'], 1)

    async def test_failed_checkpoint_keeps_committed_tick_and_retries_after_restart(self):
        module = self.clock({'checkpoint_every': 1})
        self.fail_save = True
        with self.assertRaises(OSError):await module.receive('one')
        self.assertEqual(module.state['tick'], 1)
        self.assertTrue(module.state['pending_checkpoint'])
        self.assertEqual((await module.receive('one'))['tick'], 1)
        self.assertEqual(self.saved, [True])
        self.backend.restore(self.backend.store.latest())
        restored = self.backend.network.get('time').modules.get('clock.counter')
        self.assertTrue(restored.state['pending_checkpoint'])
        self.fail_save = False
        self.assertEqual(await restored.flush(), dict(checkpointed=True, tick=1))
        self.assertFalse(restored.state['pending_checkpoint'])
        self.assertEqual(self.saved, [True, True])

    async def test_concurrent_duplicate_ticks_only_increment_once(self):
        module = self.clock()
        values = await asyncio.gather(*(module.receive('one') for _ in range(10)))
        self.assertEqual([value['tick'] for value in values], [1] * 10)
        self.assertEqual(module.state['seen'], ['one'])

    async def test_custom_labels_and_initial_tick_keep_original_rules(self):
        module = self.clock({'labels': ['A', 'B'], 'initial_tick': 2})
        self.assertEqual(await module.read(), dict(tick=2, day=1, slot='B'))
        self.assertEqual(await module.receive(None), dict(tick=3, day=2, slot='A'))
        self.assertEqual(await module.receive(None), dict(tick=4, day=2, slot='B'))
        self.assertEqual(module.state['seen'], [])

    async def test_periodic_checkpoint_duplicate_retries_failed_pending_without_recounting(self):
        module = PeriodicCheckpointModule(self.transaction, self.checkpoint, {'every': 2})
        self.saver.tables.module_types['runtime.periodic_checkpoint'] = lambda spec: PeriodicCheckpointModule(self.transaction, self.checkpoint)
        self.node.install(module)
        await module.receive('one')
        self.fail_save = True
        with self.assertRaises(OSError):await module.receive('two')
        self.assertEqual(await module.read(), dict(count=2, pending=True))
        self.fail_save = False
        self.assertEqual(await module.receive('two'), dict(count=2, pending=False))
        self.assertEqual(self.saved, [True, True])

    async def test_world_time_keeps_its_own_original_labels_and_template(self):
        module = WorldTimeModule(self.transaction)
        self.saver.tables.module_types['world.time'] = lambda spec: WorldTimeModule(self.transaction)
        self.node.install(module)
        for index in range(5):value = await module.receive(str(index))
        self.assertEqual(value, dict(tick=5, day=1, slot='午夜'))
        self.assertEqual(self.file.read_text(encoding='utf-8'), '当前时间：第1天 午夜（总 tick：5）')
        self.assertEqual(await module.receive('4'), value)
