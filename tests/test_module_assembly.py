"""递归装配与清单预检；使用真实工作室及模块运行时，不调用模型。"""
from copy import deepcopy
import json
from pathlib import Path
from pkgutil import extend_path
import sys
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'extensions/development/capabilities/component_studio/python'),
              str(ROOT/'extensions/foundation/capabilities/module_sdk/python')]
import datanet
datanet.__path__=extend_path(datanet.__path__,datanet.__name__)
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.node_modules import NodeModules
from datanet.studio.assembly import assemble,assemble_document
from datanet.studio.contract import manifest,factory
from datanet.studio.service import Studio

class ModuleAssemblyTests(unittest.TestCase):
    def test_nested_dependencies_preserve_existing_instances_and_do_not_mutate_input(self):
        def release(requires):return dict(manifest=dict(node_types=['node'],requires=requires),mount_defaults=dict(config={},state={},access={'strength':1,'channels':['x']}))
        library={'a':release(['b']),'b':release(['c']),'c':release([])}
        existing=dict(config={'custom':True},state={'count':7},access={'strength':9,'channels':['private']})
        node=dict(type='node',modules={'a':deepcopy(existing),'c':deepcopy(existing)});before=deepcopy(node)
        result=assemble(node,library)
        self.assertEqual(set(result),{'a','b','c'});self.assertEqual(result['c'],existing)
        self.assertEqual(result['b'],library['b']['mount_defaults']);self.assertEqual(node,before)
        document={'network':{'nodes':[node]},'files':{'note.md':'资料'}}
        self.assertEqual(set(assemble_document(document,library)['network']['nodes'][0]['modules']),{'a','b','c'})
        self.assertEqual(document['network']['nodes'][0],before)
        official=dict(type='node',modules={'network.gateway':deepcopy(existing)})
        self.assertEqual(assemble(official,library,{'network.gateway'}),official['modules'])
        with self.assertRaisesRegex(ValueError,'缺少'):assemble(official,library)
        for change in ('missing','cycle','wrong_type'):
            broken=deepcopy(library)
            if change=='missing':del broken['c']
            elif change=='cycle':broken['c']['manifest']['requires']=['a']
            else:broken['c']['manifest']['node_types']=['agent']
            with self.subTest(change=change),self.assertRaises(ValueError):assemble(node,broken)
            self.assertEqual(node,before)

    def test_workbench_mount_and_reload_fill_dependencies_without_resetting_config(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            standards={}
            for folder in ('move_here','place_info'):
                path=ROOT/'extensions/foundation/capabilities'/folder;spec=manifest(path)
                standards[spec['id']]=dict(folder=path,manifest=spec)
            backend=SimpleNamespace(directory=Path(directory),network=Network(),_transaction_lock=RLock(),
                components=SimpleNamespace(standard_modules=standards,module_types={},module_owners={},module_extensions={},enabled={'capabilities/component_studio'}))
            backend.network.add_node(Node('place','地点',None));backend.modules=NodeModules(backend,backend.components.module_types)
            studio=Studio(backend);studio.state=lambda:{}
            try:
                studio.mount({'node':'place','module':'movement.here'})
                node=backend.network.nodes['place'];self.assertEqual(set(node.modules),{'movement.here','place.info'})
                info=backend.modules.get('place','place.info');info.state['visitors']=['NPC']
                studio.mount({'node':'place','module':'movement.here','config':{'timeout_seconds':7}})
                self.assertIs(backend.modules.get('place','place.info'),info);self.assertEqual(info.state['visitors'],['NPC'])
                with self.assertRaisesRegex(ValueError,'依赖'):studio.unmount({'node':'place','module':'place.info'})
                studio.unmount({'node':'place','module':'movement.here'});studio.unmount({'node':'place','module':'place.info'})
                # 模拟从磁盘载入仅声明根模块的网络，图加载回调补齐依赖。
                backend.modules.mount('place','movement.here',access={'strength':2,'channels':['movement','tools']})
                studio._bind();self.assertEqual(set(node.modules),{'movement.here','place.info'})
            finally:backend.modules.clear();studio.close()

    def test_invalid_agent_tool_metadata_is_rejected_before_python_import(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            folder=Path(directory);spec=manifest(ROOT/'extensions/foundation/capabilities/move_here')
            (folder/'module.py').write_text("raise RuntimeError('不应导入此源码')\n",encoding='utf-8')
            for change in ('duplicate','unknown','mixed'):
                broken=deepcopy(spec)
                if change=='duplicate':broken['agent_tools']*=2
                elif change=='unknown':broken['agent_tools'][0]['operation']='missing'
                else:broken['tool_provider']={'list':'move','invoke':'move'}
                (folder/'module.json').write_text(json.dumps(broken),encoding='utf-8')
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'工具'):factory(folder)

if __name__=='__main__':unittest.main()
