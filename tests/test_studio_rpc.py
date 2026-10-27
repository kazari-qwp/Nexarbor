"""实际制作 RPC 装配、核心依赖及制作库冷重开。"""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from adapt.harness.backend.transport import Transport
from app.runtime.backend import Backend
from app.studio.service import Studio
from domain.core import Network,Node,NodeInfo
ROOT=Path(__file__).resolve().parents[1]

class StudioRpc(unittest.TestCase):
    def test_actual_mount_tools_preview_revision_apply_and_cold_reopen(self):
        with TemporaryDirectory(prefix='studio-rpc-',dir=ROOT/'build') as temp:
            root=Path(temp);folder=root/'counter';folder.mkdir()
            files=json.loads((ROOT/'resources/studio/templates/blank.json').read_text(encoding='utf-8'))
            spec=json.loads(files['module.json']);spec['agent_tools']=[dict(id='increment',name='计数',description='增加',operation='increment')]
            files['module.json']=json.dumps(spec)
            for name,text in files.items():(folder/name).write_text(text,encoding='utf-8')
            def configure(backend):Studio(backend,{'example.counter':folder})
            backend=Backend(root/'runtime',network=Network([Node(NodeInfo('counter','计数'))]),configure=configure)
            transport=Transport(backend,StringIO())
            try:
                rpc=transport.dispatch
                self.assertEqual(rpc('studio_catalog',{})['contract'],'nexarbor-module/v4')
                initial=backend.store.head
                rpc('studio_mount',{'node':'counter','module':'example.counter'})
                self.assertGreater(backend.store.head,initial)
                self.assertEqual(next(iter(backend.network.get('counter').tools)).invoke(amount=3),3)
                work=rpc('studio_create',{'kind':'network'});rpc('studio_copy_current',{'id':work['id']})
                observed=rpc('studio_observe',{'id':work['id'],'source':'candidate'})
                self.assertEqual(observed['network']['nodes'][0]['tables']['modules'][0]['state']['count'],3)
                release=rpc('studio_release_read',{'module':'example.counter'})
                revision=rpc('studio_revision',{'kind':'module','source':release,'reference':'修改咨询'})
                self.assertNotEqual(revision['branch_module'],'example.counter')
                self.assertEqual(json.loads(revision['files']['module.json'])['id'],revision['branch_module'])
                self.assertIn('reference/咨询记录.json',revision['references'])
                original=rpc('studio_state',{})['live']['document'];changed=deepcopy(original);changed['network']['nodes'][0]['name']='新名称'
                with self.assertRaisesRegex(ValueError,'reload'):rpc('studio_apply',{'document':changed,'base_commit':-1})
                applied=rpc('studio_apply',{'document':changed,'base_commit':backend.store.head})
                self.assertEqual(applied['commit'],backend.store.head)
                self.assertEqual(backend.network.get('counter').info.name,'新名称')
                self.assertEqual(next(iter(backend.network.get('counter').tools)).invoke(amount=2),5)
                rpc('save',{})
            finally:transport.close()
            backend=Backend(root/'runtime',configure=configure);transport=Transport(backend,StringIO())
            try:
                self.assertEqual(next(iter(backend.network.get('counter').tools)).invoke(amount=1),6)
                transport.dispatch('studio_unmount',{'node':'counter','module':'example.counter'})
                self.assertEqual(list(backend.network.get('counter').tools),[])
                self.assertEqual(backend.store.pending(),[])
            finally:transport.close()

    def test_actual_town_loads_with_studio_before_restoring_modules(self):
        from projects.npc_town.runtime import TownProject
        with TemporaryDirectory(prefix='studio-town-',dir=ROOT/'build') as temp:
            for turn in range(2):
                project=TownProject(temp,studio=True);transport=Transport(project.backend,StringIO())
                try:
                    state=transport.dispatch('studio_state',{});nodes=state['live']['document']['network']['nodes']
                    self.assertEqual(len(nodes),52)
                    self.assertEqual(len(transport.dispatch('studio_catalog',{})['library']),19)
                    actor=next(node for node in nodes if node['name']=='小砾')
                    view=transport.dispatch('executor_prepare',{'actor':actor['node_id']})
                    self.assertTrue(any('memory_query'==tool['name'] for tool in view['tools']))
                    self.assertTrue(any('movement' in tool['description'] or '移动' in tool['description'] for tool in view['tools']))
                    transport.dispatch('save',{})
                finally:transport.close()
