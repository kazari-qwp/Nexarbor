"""File-aware claims through the registered component tools, without inference."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import test_application as fixtures
import test_cooperation as cooperation


class ClaimPathTests(unittest.TestCase):
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team

    def setUp(self):
        fixtures.ApplicationTests.setUp(self)
        self.app.plugins['tools/agent_delegation'].start_worker = lambda target: None
        self.group = self.team(count=2)
        self.a, self.b = self.group['members']
        self.invoke('datanet_cooperate', dict(group_id='team', action='start', task='认领路径验证'))

    def claim(self, scope, paths=None, actor=None):
        params = dict(action='claim', scope=scope)
        if paths is not None:
            params['paths'] = paths
        return self.invoke('datanet_team_claim', params, actor or self.a)

    def test_normalization_conflicts_and_visible_state(self):
        first = self.claim('实现解析器', ['src\\parser.py', './src/parser.py', 'src/temp/../parser.py'])
        self.assertEqual(first['paths'], ['src/parser.py'])
        collision = self.claim('重命名解析器', ['src/parser.py'], self.b)
        self.assertEqual(collision['reason'], 'paths')
        self.assertEqual(collision['claim']['actor'], self.a)
        self.assertEqual(collision['overlaps'], [dict(requested='src/parser.py', claimed='src/parser.py')])
        if os.name == 'nt':
            self.assertTrue(self.claim('路径大小写别名', ['SRC./PARSER.PY.'], self.b)['conflict'])
        other = self.claim('测试解析器', ['tests/parser.py'], self.b)
        self.assertIn('id', other)
        definition = self.native.tools[self.a]['datanet_team_claim']['parameters']
        self.assertIn('paths', definition['properties'])
        self.assertIn('extend', definition['properties']['action']['enum'])
        state = self.invoke('datanet_team_status', actor=self.b)
        self.assertEqual(state['claims'][first['id']]['paths'], first['paths'])
        self.assertIn('src/parser.py', state['entries'][0]['content'])
        payload = dict(actor=self.b, texts=[])
        self.app.emit('context/tail', **payload)
        tail = '\n'.join(payload['texts'])
        self.assertIn('src/parser.py', tail)
        self.assertIn('active_claims', tail)

    def test_directory_overlap_in_both_directions(self):
        directory = self.claim('解析模块', ['src/parsers/'])
        self.assertEqual(directory['paths'], ['src/parsers'])
        self.assertTrue(self.claim('子文件', ['src/parsers/csv.py'], self.b)['conflict'])
        self.assertIn('id', self.claim('相邻目录', ['src/parsers2/csv.py'], self.b))
        self.invoke('datanet_team_claim', dict(action='release', claim_id=directory['id']), self.a)
        file = self.claim('单文件', ['src/parsers/csv.py'])
        conflict = self.claim('整个解析目录', ['src/parsers'], self.b)
        self.assertEqual(conflict['claim']['id'], file['id'])

    def test_extend_is_atomic_and_released_paths_are_available(self):
        first = self.claim('代码', ['src/a.py'])
        second = self.claim('测试', ['tests/a.py'], self.b)
        extended = self.invoke('datanet_team_claim', dict(action='extend', claim_id=first['id'], paths=['src/b.py']), self.a)
        self.assertEqual(extended['id'], first['id'])
        self.assertEqual(extended['paths'], ['src/a.py', 'src/b.py'])
        count = len(self.backend.cooperative_groups['team']['entries'])
        self.invoke('datanet_team_claim', dict(action='extend', claim_id=first['id'], paths=['src/./b.py']), self.a)
        self.assertEqual(len(self.backend.cooperative_groups['team']['entries']), count)
        conflict = self.invoke('datanet_team_claim', dict(action='extend', claim_id=first['id'], paths=['src/c.py', 'tests/a.py']), self.a)
        self.assertEqual(conflict['claim']['id'], second['id'])
        self.assertEqual(self.backend.cooperative_groups['team']['claims'][first['id']]['paths'], extended['paths'])
        self.assertEqual(len(self.backend.cooperative_groups['team']['entries']), count)
        with self.assertRaises(PermissionError):
            self.invoke('datanet_team_claim', dict(action='extend', claim_id=first['id'], paths=['x.py']), self.b)
        self.invoke('datanet_team_claim', dict(action='release', claim_id=second['id']), self.b)
        self.invoke('datanet_team_claim', dict(action='extend', claim_id=first['id'], paths=['tests/a.py']), self.a)
        self.invoke('datanet_team_claim', dict(action='complete', claim_id=first['id'], evidence='验证通过'), self.a)
        self.assertIn('id', self.claim('接手后续工作', ['src/a.py', 'tests/a.py'], self.b))
        with self.assertRaises(PermissionError):
            self.invoke('datanet_team_claim', dict(action='extend', claim_id=first['id'], paths=['x.py']), self.a)

    def test_simultaneous_claims_have_one_winner(self):
        barrier = Barrier(2)

        def compete(actor):
            barrier.wait(timeout=5)
            return self.claim('任务-' + actor, ['new-file.md'], actor)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, (self.a, self.b)))
        winners = [r for r in results if 'id' in r]
        losers = [r for r in results if r.get('conflict')]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 1)
        self.assertEqual(losers[0]['claim']['id'], winners[0]['id'])
        self.assertEqual(len(self.backend.cooperative_groups['team']['claims']), 1)

    def test_optional_paths_invalid_paths_and_persistence(self):
        investigation = self.claim('调查任务')
        self.assertEqual(investigation['paths'], [])
        # Snapshots made before this feature have no paths field.
        self.backend.cooperative_groups['team']['claims'][investigation['id']].pop('paths')
        self.assertEqual(self.claim('调查任务', actor=self.b)['reason'], 'scope')
        file = self.claim('持久记录', ['docs/result.md'], self.b)
        before = len(self.backend.cooperative_groups['team']['entries'])
        for path in ('../escape.md', 'C:\\outside.md', '/outside.md', '.git/config', './', 'src/*.py'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.claim('错误路径', [path])
        self.assertEqual(len(self.backend.cooperative_groups['team']['entries']), before)
        # Reopen the actual persisted backend, without starting any model loops.
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        self.backend = fixtures.Backend(self.temp.name)
        claims = self.backend.cooperative_groups['team']['claims']
        self.assertEqual(claims[file['id']]['paths'], ['docs/result.md'])
        self.assertNotIn('paths', claims[investigation['id']])
        findings = self.backend.network.nodes[self.group['entry_points']['findings']].file_path.read_text(encoding='utf-8')
        self.assertIn('docs/result.md', findings)


if __name__ == '__main__':
    unittest.main()
