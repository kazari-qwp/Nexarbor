"""资源缓存必须保留原规范 JSON 的哈希和失效边界。"""
from copy import deepcopy
import unittest
from app.persistence.state_hash import StateHash
from app.persistence.state_journal import checksum,diff

class StateHashTests(unittest.TestCase):
    def test_resource_changes_and_replay_match_original_protocol(self):
        old=None;cached=StateHash()
        states=[{'files':{'说明.md':'中文😀\n'*1000,'db':{'encoding':'base64','data':'AAAB'}}},
                {'files':{'说明.md':'中文😀\n'*1000,'db':{'encoding':'base64','data':'AAAB'}},'actor':2},
                {'files':{'说明.md':'new','empty':None},'actor':3},
                {'files':{},'actor':4}, {'files':None}, {'files':{'float':-0.0}}, {'files':{'float':0.0}}]
        for state in states:
            self.assertEqual(cached.digest(state,diff(old,state)),checksum(state));old=deepcopy(state)

    def test_rejected_work_does_not_corrupt_previous_cache(self):
        saved={'files':{'a':'original'},'actor':1};cached=StateHash();cached.digest(saved)
        failed={'files':{'a':'temporary'},'actor':2};trial=cached.copy();trial.digest(failed,diff(saved,failed))
        next_state={'files':{'a':'original'},'actor':3}
        self.assertEqual(cached.digest(next_state,diff(saved,next_state)),checksum(next_state))

    def test_changed_invalid_json_is_rejected_and_generic_documents_keep_existing_hashes(self):
        cached=StateHash();initial={'files':{'a':1}};cached.digest(initial)
        changed={'files':{'a':float('nan')}}
        with self.assertRaises(ValueError):cached.copy().digest(changed,diff(initial,changed))
        for document in [None,[],{'files':['normal','list']},{3:'numeric key'},{'files':{3:'numeric file key'}}]:
            self.assertEqual(StateHash().digest(document),checksum(document))

if __name__=='__main__':unittest.main()
