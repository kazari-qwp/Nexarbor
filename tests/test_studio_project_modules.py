"""制作 Agent 交付的 v4 类在真实新核心中装配、调用和保存重开。"""
import asyncio,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.runtime.backend import Backend
from app.studio.modules import ProjectModules
from domain.core import Network,Node,NodeInfo,Link
ROOT=Path(__file__).resolve().parents[1]
SOURCE="""from domain.core import Module,access
class Counter(Module):
    def __init__(self,config=None,state=None,**settings):
        super().__init__('counter',**settings);self.config=config or {};self.state=state or {}
    def increment(self,amount=1):return next(iter(self._increment(amount).values()))
    @access(channels=())
    def _increment(self,node,amount):
        self.state['count']=self.state.get('count',0)+amount
        return {'count':self.state['count']}
"""
class ProjectModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='studio-module-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.module=self.root/'counter';self.module.mkdir()
        self.spec=dict(format='nexarbor-module/v4',id='counter',name='计数',description='增加计数',entry='module.py:Counter',version='1.0.0',node_types=['node'],requires=[],config_schema={'type':'object'},state_schema={'type':'object'},operations=[{'name':'increment','parameters':{'type':'object','properties':{'amount':{'type':'integer'}}},'result':{}}],agent_tools=[{'id':'increment','name':'计数','operation':'increment'}],signals=[])
        (self.module/'module.json').write_text(json.dumps(self.spec),encoding='utf-8');(self.module/'module.py').write_text(SOURCE,encoding='utf-8')
        self.backend=Backend(self.root/'runtime',network=Network([Node(NodeInfo('a','A')),Node(NodeInfo('b','B'))]));self.addCleanup(self.backend.close)
        self.library=ProjectModules(self.backend,{'counter':self.module})

    def test_actual_class_tools_are_unique_per_instance_and_survive_cold_restore(self):
        a=self.backend.network.get('a');b=self.backend.network.get('b');one=self.library.mount(a,'counter');two=self.library.mount(b,'counter')
        names=[next(iter(n.tools)).name for n in (a,b)];self.assertNotEqual(*names)
        self.assertEqual(next(iter(a.tools)).invoke(amount=3),{'count':3});self.assertEqual(two.state,{})
        self.backend.save(full=True);document=self.backend.snapshot();self.backend.restore(document)
        restored=self.backend.network.get('a');self.assertEqual(next(iter(restored.tools)).name,names[0]);self.assertEqual(next(iter(restored.tools)).invoke(amount=2),{'count':5})

    def test_v3_function_entry_is_rejected_instead_of_running_old_ctx(self):
        self.library.manifests['counter']['format']='nexarbor-module/v3'
        with self.assertRaisesRegex(ValueError,'v4'):self.library.mount(self.backend.network.get('a'),'counter')

    def test_dependency_cycle_is_reported_by_existing_core_installer(self):
        self.library.manifests['counter']['requires']=['counter']
        with self.assertRaises(ValueError):self.library.mount(self.backend.network.get('a'),'counter')
        self.assertEqual(list(self.backend.network.get('a').modules),[])

    def test_module_folder_keeps_relative_imports_to_project_shared_helpers(self):
        helper=self.root/'shared';helper.mkdir();(helper/'__init__.py').write_text('',encoding='utf8');(helper/'values.py').write_text('OFFSET=7\n',encoding='utf8')
        (self.module/'module.py').write_text('from ..shared.values import OFFSET\n'+SOURCE.replace("self.state.get('count',0)+amount","self.state.get('count',0)+amount+OFFSET"),encoding='utf8')
        module=self.library.mount(self.backend.network.get('a'),'counter');self.assertEqual(module.increment(amount=3),{'count':10})
