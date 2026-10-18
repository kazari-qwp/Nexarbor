"""Explicit official authority, real Backend reload and v2 SDK loading."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
for path in ('extensions/foundation/capabilities/network_gateway/python',
             'extensions/foundation/capabilities/module_sdk/python'):
    sys.path.insert(0,str(ROOT/path))
import datanet
from pkgutil import extend_path
datanet.__path__=extend_path(datanet.__path__,datanet.__name__)
from test_local_modules import make, mount
from datanet.abilities.network_gateway.services import NetworkGateway,host_operation


def gateway(b, operations=(), targets=()):
    b.modules.factories['network.gateway']=NetworkGateway
    b.components.module_owners['network.gateway']='test'
    b.components.module_extensions['network.gateway']=(NetworkGateway,host_operation)
    access={'strength':0,'channels':['network.extended']}
    if operations or targets:access['extension']={'operations':list(operations),'targets':list(targets)}
    return b.modules.mount('b','network.gateway',access=access)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_gateway_and_default_gateway_grant_nothing(self):
        b=make();mount(b,'a',2,['network.extended']);b.network.nodes['a'].connect('b',channels=['network.extended'])
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'b','module':'network.gateway','operation':'nodes'})
        gateway(b)
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'b','module':'network.gateway','operation':'nodes'})

    async def test_gateway_is_explicit_bounded_service_not_raw_backend(self):
        b=make();mount(b,'a',2,['network.extended']);gateway(b,['nodes','metadata','incoming'],['b','hidden'])
        b.network.nodes['a'].connect('b',channels=['network.extended'])
        b.network.nodes['hidden'].connect('b',channels=['secret'])
        args={'target':'b','module':'network.gateway','operation':'nodes'}
        result=await b.modules.call('a','probe','forward',args)
        self.assertEqual({n['node_id'] for n in result},{'b','hidden'})
        self.assertNotIn('modules',result[0]);self.assertNotIn('interfaces',result[0])
        result[0]['name']='tamper';self.assertEqual(b.network.nodes['b'].name,'b')
        incoming=await b.modules.call('a','probe','forward',{**args,'operation':'incoming','arguments':{'target':'b'}})
        self.assertEqual([edge['source'] for edge in incoming],['hidden'])
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{**args,'operation':'metadata','arguments':{'target':'c'}})
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{**args,'operation':'connect','arguments':{'source':'b','target':'hidden','channels':['x']}})
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'hidden'})

    async def test_gateway_access_still_requires_route_channel(self):
        b=make();mount(b,'a',3,['red']);gateway(b,['nodes'],['*'])
        b.network.nodes['a'].connect('b',channels=['red','network.extended'])
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'b','module':'network.gateway','operation':'nodes'})

    def test_network_edits_are_whitelisted_and_disconnect_preserves_other_channels(self):
        b=make();gateway(b,['connect','disconnect'],['b','c'])
        b.network.nodes['b'].connect('c',channels=['keep'])
        b.modules.call('b','network.gateway','connect',{'source':'b','target':'c','channels':['new']})
        self.assertEqual(set(b.network.nodes['b'].interfaces[0].metadata.channels),{'keep','new'})
        b.modules.call('b','network.gateway','disconnect',{'source':'b','target':'c','channels':['new']})
        self.assertEqual(b.network.nodes['b'].interfaces[0].metadata.channels,('keep',))
        with self.assertRaises(PermissionError):
            b.modules.call('b','network.gateway','connect',{'source':'b','target':'hidden','channels':['new']})
        with self.assertRaises(PermissionError):b.modules.call('b','network.gateway','nodes')

    def test_replacing_factory_cannot_impersonate_the_official_gateway(self):
        from test_local_modules import Probe
        b=make();gateway(b,['nodes'],['*']);b.modules.unmount('b','network.gateway')
        b.modules.factories['network.gateway']=Probe
        with self.assertRaises(PermissionError):b.modules.mount('b','network.gateway')

    def test_optional_gateway_is_not_selected_by_default(self):
        from datanet.component_catalog import resolve
        _,order,_=resolve(ROOT/'extensions/foundation',selection=[])
        self.assertNotIn('capabilities/network_gateway',order)

    def test_real_backend_persists_grant_and_state(self):
        from datanet.core.backend import Backend
        from datanet.core.node import Node
        import datanet.core.component_registry as registry
        env={'DATANET_COMPONENT_ROOT':str(ROOT/'extensions/foundation'),
             'DATANET_COMPONENT_SELECTION':'["capabilities/network_gateway"]'}
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,env),patch.object(registry,'_enabled',None):
            backend=Backend(directory)
            try:
                backend.network.add_node(Node('far','Far',None))
                module=backend.modules.mount('root','network.gateway',access={'strength':0,'channels':['network.extended'],
                    'extension':{'operations':['metadata'],'targets':['far']}})
                module.state['count']=5;backend.dispatch('save',{'full':True})
            finally:backend.close()
            restored=Backend(directory)
            try:
                self.assertEqual(restored.modules.get('root','network.gateway').state['count'],5)
                self.assertEqual(restored.modules.call('root','network.gateway','metadata',{'target':'far'})['name'],'Far')
                with self.assertRaises(PermissionError):restored.modules.call('root','network.gateway','nodes')
            finally:restored.close()

    def test_sdk_v2_rejects_v1_before_executing_module_source(self):
        from datanet.studio.contract import factory
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'module.json').write_text(json.dumps({'format':'nexarbor-module/v1'}))
            (folder/'module.py').write_text("raise AssertionError('must not execute')")
            with self.assertRaisesRegex(ValueError,'v2'):factory(folder)

    async def test_sdk_v2_mount_operations_signal_and_async_schema_validation(self):
        from datanet.studio.contract import factory
        from datanet.core.signals import Signal
        from jsonschema import ValidationError
        spec={'format':'nexarbor-module/v2','id':'test.counter','version':'1.0.0','entry':'module.py:Module',
              'node_types':['node'],'requires':[],'config_schema':{'type':'object'},
              'state_schema':{'type':'object','properties':{'n':{'type':'integer'}}},'tools':[],
              'signals':['tick'],'operations':[{'name':'value','channels':['red'],'parameters':{'type':'object'}},
                                            {'name':'invalid','channels':[],'parameters':{'type':'object'}}]}
        source='''from datanet.studio.contract import StudioModule
class Module(StudioModule):
    def setup(self): self.state.setdefault('n',0)
    async def on_signal(self,context): self.state['n']+=1
    def value(self): return self.state
    async def invalid(self): self.state['n']='bad'
'''
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'module.json').write_text(json.dumps(spec));(folder/'module.py').write_text(source)
            (folder/'example.json').write_text(json.dumps({'config':{}}))
            _,create=factory(folder);b=make();b.modules.factories['test.counter']=create
            module=mount(b,'b',1,['red'],name='test.counter');mount(b,'a',2,['red'])
            b.network.nodes['a'].connect('b',channels=['red','tick'])
            report=await b.signals.propagate(Signal('a',['tick'],2));self.assertEqual(report['status'],'completed')
            result=await b.modules.call('a','probe','forward',{'target':'b','module':'test.counter'})
            self.assertEqual(result,{'n':1});result['n']=9;self.assertEqual(module.state['n'],1)
            with self.assertRaises(ValidationError):await b.modules.call('b','test.counter','invalid')
            env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(ROOT/'python'),
                str(ROOT/'extensions/foundation/capabilities/module_sdk/python')]),DATANET_COMPONENT_SELECTION='[]')
            worker=ROOT/'extensions/development/capabilities/component_studio/python/datanet/studio/worker.py'
            check=await asyncio.to_thread(subprocess.run,[sys.executable,str(worker),str(folder)],
                env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)
            self.assertIn('local v2 contract',check.stdout)


if __name__=='__main__':unittest.main()
