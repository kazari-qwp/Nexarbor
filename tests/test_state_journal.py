"""Incremental values, full snapshots, integrity and executor-neutral recovery boundaries."""
import json,sqlite3,tempfile,unittest
from pathlib import Path
from datanet.core.checkpoints import Checkpoints
from datanet.core.state_journal import diff,apply,checksum
from datanet.core.backend import Backend
from datanet.core.recovery import restore_bundle,required_contexts

class JournalTests(unittest.TestCase):
    def test_deltas_nested_arrays_and_removed_values(self):
        old={'nodes':[{'id':'a','coins':8},{'id':'b','coins':2}],'files':{'a':'old'},'obsolete':True}
        new={'nodes':[{'id':'a','coins':6},{'id':'b','coins':4},{'id':'c'}],'files':{'a':'new'},'new':None}
        patch=diff(old,new);self.assertEqual(apply(old,patch),new)
        self.assertFalse(any(op.get('value')==new for op in patch));self.assertEqual(apply(new,diff(new,old)),old)
        self.assertEqual(apply([1,2,3],diff([1,2,3],[9])),[9])
        self.assertTrue(diff({'n':-0.0},{'n':0.0}))
    def test_small_changes_noop_full_interval_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
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
        with tempfile.TemporaryDirectory() as folder:
            store=Checkpoints(Path(folder));store.commit({'value':0});store.begin('unfinished','mutate');store.close()
            store=Checkpoints(Path(folder));self.assertEqual(store.pending()[0]['status'],'uncertain')
            with self.assertRaises(RuntimeError):store.mark({})
            store.reconcile('unfinished','verified no external replay is needed')
            with self.assertRaises(RuntimeError):store.mark({},expected_commit=0)
            first=store.mark({},expected_commit=1);second=store.mark({},kind='full')
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(second['commit_id'],1)
            self.assertEqual(store.stats()['full_snapshot_count'],1);store.close()
    def test_corruption_and_missing_chain_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Checkpoints(Path(folder));store.commit({'n':0});store.commit({'n':1})
            with store.db:store.db.execute('UPDATE commits SET delta=? WHERE id=2',(json.dumps([{'op':'set','path':['n'],'value':99}]),))
            with self.assertRaises(ValueError):store.read(2)
            store.close()
            with self.assertRaises(ValueError):Checkpoints(Path(folder))
    def test_recovery_points_reference_opaque_executor_cursors(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Checkpoints(Path(folder));store.commit({'network':'one'})
            marker={'npc':{'adapter':'example','session':'native-session','position':{'seq':12,'generation':'log-a'}}}
            point=store.mark(marker,kind='full');store.commit({'network':'two'})
            marker['npc']['position']['seq']=99
            bundle=store.bundle(point['id']);self.assertEqual(bundle['document'],{'network':'one'})
            self.assertEqual(bundle['point']['contexts']['npc']['position']['seq'],12)
            self.assertEqual(len(store.points()),1);store.close()
    def test_backend_restore_memory_state_and_executors_must_be_acknowledged(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);b=Backend(base/'source');b.dispatch('bind_agent',dict(target='root',session_id='old-session',manager_id=None))
            b.root.write_memory('before');b.dispatch('save',{})
            info=b.dispatch('persistence_info',{})
            with self.assertRaises(ValueError):b.dispatch('persistence_mark',dict(contexts={}))
            point=b.dispatch('persistence_mark',dict(contexts={'root':{'adapter':'fake','session':'old-session','seq':7}},expected_commit=info['commit_id'],kind='full'))
            b.root.write_memory('after');b.dispatch('save',{})
            bundle=b.dispatch('persistence_export',dict(point_id=point['id']))
            result=b.dispatch('persistence_restore',dict(point_id=point['id'],directory=str(base/'branch')))
            self.assertEqual(result['executor_restore']['status'],'pending')
            branch=Backend(base/'branch')
            self.assertEqual(branch.root.read_memory()['content'],'before');self.assertEqual(b.root.read_memory()['content'],'after')
            self.assertEqual(required_contexts(branch.store)['root']['seq'],7)
            from datanet.core.application import Application
            with self.assertRaises(RuntimeError):Application(branch,lambda *args:None,{}).bind_session('wrong-latest-session')
            with self.assertRaises(ValueError):branch.dispatch('persistence_executor_restored',dict(sessions={}))
            branch.dispatch('persistence_executor_restored',dict(sessions={'root':'forked-at-seq-7'}))
            self.assertEqual(branch.agents['root']['session_id'],'forked-at-seq-7');self.assertFalse(required_contexts(branch.store))
            self.assertTrue(branch.dispatch('persistence_executor_restored',dict(sessions={'root':'forked-at-seq-7'}))['ready'])
            branch.close()
            with self.assertRaises(ValueError):restore_bundle(bundle,base/'branch')
            bundle['point']['contexts']['root']['seq']=999
            with self.assertRaises(ValueError):restore_bundle(bundle,base/'tampered')
            b.close()
    def test_cursor_objects_and_unchanged_points_are_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Checkpoints(Path(folder));s.commit({'n':0});a={'a':{'session':'one','seq':2},'b':{'session':'two','seq':5}}
            first=s.mark(a,reuse=True);self.assertEqual(s.mark(a,reuse=True)['id'],first['id'])
            s.commit({'n':1});second=s.mark(a,reuse=True)
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(s.stats()['executor_cursor_count'],2)
            a['a']['seq']=3;third=s.mark(a,reuse=True)
            self.assertEqual(third['commit_id'],second['commit_id']);self.assertEqual(s.stats()['executor_cursor_count'],3)
            self.assertEqual(s.point(first['id'])['contexts']['a']['seq'],2)
            s.close();s=Checkpoints(Path(folder));self.assertEqual(s.point(third['id'])['contexts']['a']['seq'],3);s.close()

    def test_caught_internal_failure_is_committed_not_left_uncertain(self):
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder)
            def fail(backend,p):backend.extension_state['partial']=1;raise ValueError('known failure')
            b.components.rpc('fixture_fail',fail,mutation=True)
            with self.assertRaises(ValueError):b.dispatch('fixture_fail',{})
            self.assertEqual(b.store.pending(),[]);self.assertEqual(b.store.latest()['partial'],1)
            self.assertTrue(b.dispatch('persistence_checkpoint',dict(contexts={},bindings={},expected_commit=b.store.head)))
            b.close()

    def test_automatic_checkpoint_validates_core_version_and_bindings(self):
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);b.dispatch('bind_agent',dict(target='root',session_id='native',manager_id=None))
            info=b.dispatch('persistence_info',{});args=dict(expected_commit=info['commit_id'],bindings=info['bindings'],contexts={'root':{'session':'native','seq':3}})
            point=b.dispatch('persistence_checkpoint',args)
            self.assertEqual(b.dispatch('persistence_checkpoint',args)['id'],point['id'])
            b.dispatch('agent_progress',dict(target='root',status='ready'))
            with self.assertRaises(RuntimeError):b.dispatch('persistence_checkpoint',args)
            args['expected_commit']=b.store.head;args['bindings']={'root':'wrong'}
            with self.assertRaises(ValueError):b.dispatch('persistence_checkpoint',args)
            b.close()

    def test_full_request_is_durable_until_consistent_point_and_does_not_duplicate_cursors(self):
        with tempfile.TemporaryDirectory() as folder:
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
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'checkpoints.sqlite3';db=sqlite3.connect(file);db.execute('CREATE TABLE checkpoints(id INTEGER PRIMARY KEY,document TEXT)');db.commit();db.close()
            for attempt in range(2):
                with self.assertRaisesRegex(ValueError,'Legacy checkpoint'):Checkpoints(Path(folder))

if __name__=='__main__':unittest.main()
