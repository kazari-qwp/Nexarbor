"""原两节点入口与两个预设使用当前工厂、真实文件和检查点。"""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.studio.project import WorkbenchProject
from app.studio.network_work import validate_network
from app.studio.preset_repetition import expand_snapshot
from adapt.harness.backend.transport import Transport
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'项目演示/应用1-讨论协作-初始'

class FinalDemoProject(unittest.TestCase):
    def test_actual_root_tools_context_and_cold_reopen(self):
        with TemporaryDirectory(prefix='final-root-',dir=ROOT/'build') as temp:
            sessions=[]
            for turn in range(2):
                p=WorkbenchProject(Path(temp)/'runtime',PROJECT);t=Transport(p.backend,StringIO())
                try:
                    state=t.dispatch('studio_state',{});nodes=state['live']['document']['network']['nodes']
                    self.assertEqual({n['node_id'] for n in nodes},{'root','administrator'})
                    view=t.dispatch('executor_prepare',{'actor':'root'})
                    self.assertTrue(any('委托制作局部网络' in tool['description'] for tool in view['tools']))
                    self.assertTrue(any(' · datanet_discuss · ' in tool['description'] for tool in view['tools']))
                    self.assertIn('memory_query',{tool['name'] for tool in view['tools']})
                    self.assertTrue(any(getattr(tool,'_host_ref',None)=='harness:pwsh' for tool in p.backend.network.get('root').tools))
                    self.assertTrue(view['context'] or view['system_prompt'])
                    t.dispatch('save',{'full':True})
                finally:t.close()

    def test_original_presets_expand_and_restore_real_modules_files_and_host_tools(self):
        with TemporaryDirectory(prefix='final-presets-',dir=ROOT/'build') as temp:
            p=WorkbenchProject(Path(temp)/'runtime',PROJECT);t=Transport(p.backend,StringIO())
            try:
                definitions={name:release['manifest'] for name,release in p.backend.studio.library.items()}
                for name,count,agents in [('discussion',10,5),('execution',6,4)]:
                    original=json.loads((PROJECT/'network_presets/fragments'/ (name+'.json')).read_text(encoding='utf8'))
                    expanded=expand_snapshot({**original['network'],'files':original['files']},definitions=definitions)
                    document={'network':{key:value for key,value in expanded.items() if key!='files'},'files':expanded['files']}
                    checked=validate_network(document,p.backend,p.backend.studio.library,port_definitions=p.backend.studio.ports)
                    self.assertEqual(len(checked['network']['nodes']),count)
                    self.assertEqual(sum(n['type']=='agent' for n in checked['network']['nodes']),agents)
                    p.register_properties(checked['network']['properties'])
                    for name,content in checked['files'].items():
                        file=p.backend.directory/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content,encoding='utf8')
                    candidate=p.saver.build(checked['network'],p.backend.directory)
                    for node in candidate:
                        self.assertEqual(len([tool.name for tool in node.tools]),len(set(tool.name for tool in node.tools)))
                        if node.node_type=='agent':self.assertTrue(list(node.tools))
                    self.assertNotIn('E:\\DataNet-',json.dumps(checked,ensure_ascii=False))
                self.assertTrue((PROJECT/'workspace/task/INPUTS.md').exists())
                self.assertTrue((PROJECT/'workspace/task/docs/PRD.md').exists())
            finally:t.close()
