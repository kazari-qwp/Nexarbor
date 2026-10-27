"""原 JournalTests 的 8 项独立存储断言；Backend/DSH 集成测试仍待迁移。"""
import json, sqlite3, tempfile, unittest
from pathlib import Path
from app.persistence.checkpoints import Checkpoints
from app.persistence.state_journal import diff, apply, checksum
PROJECT = Path(__file__).resolve().parents[1]

class JournalStoreTests(unittest.TestCase):
    def test_deltas_nested_arrays_and_removed_values(self):
        old={'nodes':[{'id':'a','coins':8},{'id':'b','coins':2}],'files':{'a':'old'},'obsolete':True}
        new={'nodes':[{'id':'a','coins':6},{'id':'b','coins':4},{'id':'c'}],'files':{'a':'new'},'new':None}
        patch=diff(old,new);self.assertEqual(apply(old,patch),new)
        self.assertFalse(any(op.get('value')==new for op in patch));self.assertEqual(apply(new,diff(new,old)),old)
        self.assertEqual(apply([1,2,3],diff([1,2,3],[9])),[9])
        self.assertTrue(diff({'n':-0.0},{'n':0.0}))

    def test_small_changes_noop_full_interval_and_restart(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            store=Checkpoints(Path(folder),snapshot_interval=3)
            first={'large':'x'*10000,'counter':0};store.commit(first)
            for i in range(1,5):store.commit(dict(first,counter=i))
            self.assertEqual(store.stats()['full_snapshot_count'],2)
            self.assertEqual(store.stats()['incremental_count'],5)
            self.assertLess(len(store.db.execute('SELECT delta FROM commits WHERE id=2').fetchone()[0]),150)
            store.begin('noop','test');head=store.commit(dict(first,counter=4),'noop')
            self.assertEqual(head,5);self.assertEqual(store.pending(),[])
            store.commit(dict(first,counter=4),force_snapshot=True);self.assertEqual(store.stats()['full_snapshot_count'],3)
            self.assertEqual(store.read(2)['counter'],1);store.close()
            store=Checkpoints(Path(folder));self.assertEqual(store.latest()['counter'],4);self.assertEqual(store.head,5);store.close()

    def test_uncertain_operation_and_optimistic_marker(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            store=Checkpoints(Path(folder));store.commit({'value':0});store.begin('unfinished','mutate');store.close()
            store=Checkpoints(Path(folder));self.assertEqual(store.pending()[0]['status'],'uncertain')
            with self.assertRaises(RuntimeError):store.mark({})
            store.reconcile('unfinished','verified no external replay is needed')
            with self.assertRaises(RuntimeError):store.mark({},expected_commit=0)
            first=store.mark({},expected_commit=1);second=store.mark({},kind='full')
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(second['commit_id'],1)
            self.assertEqual(store.stats()['full_snapshot_count'],1);store.close()

    def test_corruption_and_missing_chain_are_detected(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            store=Checkpoints(Path(folder));store.commit({'n':0});store.commit({'n':1})
            with store.db:store.db.execute('UPDATE commits SET delta=? WHERE id=2',(json.dumps([{'op':'set','path':['n'],'value':99}]),))
            with self.assertRaises(ValueError):store.read(2)
            store.close()
            with self.assertRaises(ValueError):Checkpoints(Path(folder))

    def test_recovery_points_reference_opaque_executor_cursors(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            store=Checkpoints(Path(folder));store.commit({'network':'one'})
            marker={'npc':{'adapter':'example','session':'native-session','position':{'seq':12,'generation':'log-a'}}}
            point=store.mark(marker,kind='full');store.commit({'network':'two'})
            marker['npc']['position']['seq']=99
            bundle=store.bundle(point['id']);self.assertEqual(bundle['document'],{'network':'one'})
            self.assertEqual(bundle['point']['contexts']['npc']['position']['seq'],12)
            self.assertEqual(len(store.points()),1);store.close()

    def test_cursor_objects_and_unchanged_points_are_reused(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            s=Checkpoints(Path(folder));s.commit({'n':0});a={'a':{'session':'one','seq':2},'b':{'session':'two','seq':5}}
            first=s.mark(a,reuse=True);self.assertEqual(s.mark(a,reuse=True)['id'],first['id'])
            s.commit({'n':1});second=s.mark(a,reuse=True)
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(s.stats()['executor_cursor_count'],2)
            a['a']['seq']=3;third=s.mark(a,reuse=True)
            self.assertEqual(third['commit_id'],second['commit_id']);self.assertEqual(s.stats()['executor_cursor_count'],3)
            self.assertEqual(s.point(first['id'])['contexts']['a']['seq'],2)
            s.close();s=Checkpoints(Path(folder));self.assertEqual(s.point(third['id'])['contexts']['a']['seq'],3);s.close()

    def test_full_request_is_durable_until_consistent_point_and_does_not_duplicate_cursors(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            s=Checkpoints(Path(folder));s.commit({'n':0})
            contexts={'agent':{'session':'native','seq':7}}
            first=s.mark(contexts,reuse=True)
            s.commit({'n':1},force_snapshot=True)
            self.assertTrue(s.stats()['full_snapshot_requested']);s.close()
            s=Checkpoints(Path(folder));self.assertTrue(s.stats()['full_snapshot_requested'])
            s.commit({'n':2}) # Late internal changes before native tool results become durable.
            with self.assertRaises(RuntimeError):s.mark(contexts,expected_commit=1,reuse=True)
            self.assertTrue(s.stats()['full_snapshot_requested'])
            point=s.mark(contexts,expected_commit=s.head,reuse=True)
            self.assertEqual(point['kind'],'full');self.assertEqual(s.read(point['commit_id']),{'n':2})
            self.assertFalse(s.stats()['full_snapshot_requested']);self.assertEqual(s.stats()['executor_cursor_count'],1)
            self.assertEqual(s.mark(contexts,reuse=True)['id'],point['id'])
            # A full request with no changes can reuse a confirmed full point.
            s.commit({'n':2},force_snapshot=True)
            self.assertEqual(s.mark(contexts,reuse=True)['id'],point['id'])
            self.assertFalse(s.stats()['full_snapshot_requested']);s.close()

    def test_legacy_database_is_explicitly_rejected_and_lock_released(self):
        with tempfile.TemporaryDirectory(dir=PROJECT) as folder:
            file=Path(folder)/'checkpoints.sqlite3';db=sqlite3.connect(file);db.execute('CREATE TABLE checkpoints(id INTEGER PRIMARY KEY,document TEXT)');db.commit();db.close()
            for attempt in range(2):
                with self.assertRaisesRegex(ValueError,'Legacy checkpoint'):Checkpoints(Path(folder))
