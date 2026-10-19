"""Existing workspace release tables must not pin old bundled component schemas."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from jsonschema import ValidationError
from datanet.core.backend import Backend
from datanet.studio.contract import factory
from datanet.studio.service import sources,digest,write_json

ROOT=Path(__file__).resolve().parents[1]

class StandardReleaseUpdates(unittest.TestCase):
    def setUp(self):
        base=ROOT/'build/standard-release-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=TemporaryDirectory(dir=base);self.home=Path(self.temp.name);self.b=Backend(self.home)
    def tearDown(self):
        if self.b is not None:self.b.close()
        self.temp.cleanup()
    def older_release(self,origin=None):
        files=sources(ROOT/'extensions/composable/capabilities/messages_box')
        spec=json.loads(files['module.json']);spec['version']='0.0.1';spec['config_schema']['properties'].pop('notify_activity')
        files['module.json']=json.dumps(spec,ensure_ascii=False,indent=2)
        fingerprint=digest(files);folder=self.home/'studio/releases/messages.box/0.0.1'/fingerprint
        for name,text in files.items():
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
        release=dict(id=spec['id'],version=spec['version'],folder=str(folder.relative_to(self.home/'studio')),digest=fingerprint,manifest=spec,defaults={},mount_defaults={})
        if origin is not None:release['origin_kind']=origin
        return release,folder
    def reopen(self):
        self.b.close();self.b=None;self.b=Backend(self.home)
    def test_disk_cache_and_checkpoint_both_upgrade_without_losing_node_data(self):
        state={'messages':[dict(id='saved',**{'from':'root'},to='root',text='保留消息',topic='')],'seen':[]}
        self.b.modules.mount('root','messages.box',config={'send_cost':0},state=state,access={'strength':0,'channels':['chat']})
        old,folder=self.older_release();before=sources(folder)
        with self.assertRaises(ValidationError):factory(folder)[1].validate({'notify_activity':True},old['manifest']['config_schema'])
        saved=self.b.snapshot();saved['studio_releases']['messages.box']=old;self.b.store.commit(saved)
        library=deepcopy(self.b.studio.library);library['messages.box']=old;write_json(self.home/'studio/library.json',library)
        self.reopen()
        release=self.b.studio.library['messages.box'];self.assertEqual(release['origin'],'standard');self.assertNotEqual(release['digest'],old['digest'])
        self.assertIn('notify_activity',self.b.components.module_types['messages.box'].config_schema['properties'])
        self.assertEqual(self.b.network.nodes['root'].modules['messages.box']['state'],state)
        self.assertEqual(sources(folder),before);self.assertTrue(list((self.home/'studio/library-history').glob('*.json')))
        # Loading an old snapshot later must not downgrade the installed standard definition.
        self.b.restore(saved);self.assertEqual(self.b.studio.library['messages.box']['digest'],release['digest'])
        current=self.b.studio.state();doc=current['live']['document'];doc['network']['nodes'][0]['modules']['messages.box']['config']['notify_activity']=True
        self.assertTrue(self.b.studio.apply({'document':doc,'base_commit':current['live']['commit']})['valid'])
        self.b.dispatch('save',{});self.reopen();self.assertTrue(self.b.network.nodes['root'].modules['messages.box']['config']['notify_activity'])
    def test_user_published_override_is_preserved(self):
        old,_=self.older_release('module');library=deepcopy(self.b.studio.library);library['messages.box']=old
        write_json(self.home/'studio/library.json',library)
        saved=self.b.snapshot();saved['studio_releases']['messages.box']=old;self.b.store.commit(saved);self.reopen()
        self.assertEqual(self.b.studio.library['messages.box']['digest'],old['digest'])
        self.assertNotIn('notify_activity',self.b.components.module_types['messages.box'].config_schema['properties'])
    def test_removed_standard_is_not_reinstalled_by_disk_or_snapshot(self):
        write_json(self.home/'studio/removed-modules.json',['messages.box']);self.reopen()
        self.assertNotIn('messages.box',self.b.studio.library);self.assertNotIn('messages.box',self.b.components.module_types)

if __name__=='__main__':unittest.main()
