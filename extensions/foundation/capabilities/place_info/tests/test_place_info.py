import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness


class PlaceInfoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node('home', name='家', description='家庭住所')
        self.h.add_node('family', name='家人', agent=True)

    async def asyncTearDown(self):
        await self.h.close()

    async def test_info_only_edge_allows_read(self):
        self.h.mount(
            'home',
            config={'description': '家庭住所', 'location': 'home'},
            access={'strength': 1, 'channels': ['info']},
        )
        self.h.connect('family', 'home', channels=['info'])
        result = await self.h.call(
            'home', 'read', {}, actor='family', strength=1, channels=['info']
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['node_id'], 'home')
        self.assertEqual(result['data']['description'], '家庭住所')
        self.assertEqual(result['data']['location'], 'home')

    async def test_info_only_edge_cannot_modify(self):
        self.h.mount(
            'home',
            access={'strength': 1, 'channels': ['info']},
        )
        self.h.connect('family', 'home', channels=['info'])
        calls = (
            ('arrive', {'visitor': 'family'}),
            ('leave', {'visitor': 'family'}),
            ('set_location', {'location': 'family', 'description': '新地点'}),
        )
        for operation, parameters in calls:
            with self.subTest(operation=operation):
                with self.assertRaises(PermissionError):
                    await self.h.call(
                        'home',
                        operation,
                        parameters,
                        actor='family',
                        strength=1,
                        channels=['info'],
                    )

    async def test_read_rejects_missing_path(self):
        self.h.mount(
            'home',
            access={'strength': 1, 'channels': ['movement', 'info']},
        )
        with self.assertRaises(PermissionError):
            await self.h.call(
                'home', 'read', {}, actor='family', strength=1, channels=['info']
            )

    async def test_read_rejects_unrelated_channel(self):
        self.h.mount(
            'home',
            access={'strength': 1, 'channels': ['movement', 'info', 'social']},
        )
        self.h.connect('family', 'home', channels=['social'])
        with self.assertRaises(PermissionError):
            await self.h.call(
                'home', 'read', {}, actor='family', strength=1, channels=['social']
            )

    async def test_normal_movement_read_still_works(self):
        self.h.mount(
            'home',
            access={'strength': 1, 'channels': ['movement']},
        )
        self.h.connect('family', 'home', channels=['movement'])
        result = await self.h.call(
            'home', 'read', {}, actor='family', strength=1, channels=['movement']
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['node_id'], 'home')


if __name__ == '__main__':
    unittest.main()
