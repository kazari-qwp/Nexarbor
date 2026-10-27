"""制作模型的文件工具仍使用受控副本、只读参考和真实 Git 基线。"""
from hashlib import sha256
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.runtime.backend import Backend
from app.studio.service import Studio
from domain.core import Network
ROOT=Path(__file__).resolve().parents[1]
class Workspaces(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='studio-work-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.backend=Backend(self.temp.name,network=Network());self.addCleanup(self.backend.close)
        self.studio=Studio(self.backend);self.addCleanup(self.studio.close)

    def test_real_git_baseline_paged_files_conflict_and_readonly_guides(self):
        work=self.studio.create({'kind':'module','reference_files':{'需求.md':'保留原要求'}});id=work['id']
        self.assertEqual(json.loads(work['files']['module.json'])['format'],'nexarbor-module/v4')
        self.assertIn('reference/需求.md',work['references']);self.assertNotIn('AGENTS.md',work['files'])
        self.assertTrue((self.studio.root/'history.git/HEAD').is_file())
        original=work['files']['README.md']
        result=self.studio.maker_tool({'id':id,'tool':'edit_file','arguments':{'path':'README.md','old':'# 计数器','new':'# 编辑后计数器'}})
        self.assertEqual(result['saved'],'README.md');current=self.studio.read({'id':id})
        self.assertEqual(current['original']['README.md'],original);self.assertTrue(current['files']['README.md'].startswith('# 编辑后'))
        with self.assertRaisesRegex(ValueError,'changed'):self.studio.save({'id':id,'file':'README.md','content':'失效覆盖','expected':sha256(original.encode()).hexdigest()})
        with self.assertRaises(PermissionError):self.studio.maker_tool({'id':id,'tool':'write_file','arguments':{'path':'AGENTS.md','content':'修改规范'}})
        with self.assertRaises(ValueError):self.studio.path(id,'../../escape.py')
        listing=self.studio.maker_tool({'id':id,'tool':'list_files','arguments':{}})
        self.assertTrue(any(row['readonly'] for row in listing['entries']))
        page=self.studio.maker_tool({'id':id,'tool':'read_file','arguments':{'path':'README.md','line_count':1}})
        self.assertIn('编辑后',page['text'])

    def test_network_work_copy_and_tool_template_have_only_new_formats(self):
        work=self.studio.create({'kind':'network'});document=json.loads(work['files']['network.json'])
        self.assertEqual(document,{'network':{'nodes':[]},'files':{}})
        work=self.studio.create({'kind':'tool'});spec=json.loads(work['files']['module.json'])
        self.assertEqual(spec['entry'],'module.py:Counter');self.assertEqual(spec['agent_tools'][0]['operation'],'increment')

    def test_real_worker_validation_publishes_current_sources_and_mounts_restorable_tools(self):
        work=self.studio.create({'kind':'tool'});id=work['id']
        test="""import unittest
from pathlib import Path
from app.studio.testing import ModuleHarness
class CounterTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_counter(self):
        h=ModuleHarness(Path(__file__).resolve().parents[1])
        try:
            h.add_node('counter');h.mount('counter')
            self.assertEqual((await h.call('counter','increment',{'amount':3}))['data'],3)
        finally:await h.close()
"""
        self.studio.maker_tool({'id':id,'tool':'write_file','arguments':{'path':'tests/test_counter.py','content':test}})
        with self.assertRaisesRegex(ValueError,'Test the current'):self.studio.publish({'id':id})
        job=self.studio.validate({'id':id,'timeout':60});deadline=time.monotonic()+60
        while job['status']=='running' and time.monotonic()<deadline:
            time.sleep(.05);job=self.studio.job({'job':job['id']})
        self.assertEqual(job['status'],'passed',job['log']);self.assertIn('测试数量：1',job['log'])
        release=self.studio.publish({'id':id});self.assertEqual(release['manifest']['format'],'nexarbor-module/v4')
        from domain.core import Node,NodeInfo
        node=Node(NodeInfo('mounted','实际挂载'));self.backend.network.add(node)
        self.studio.modules.mount(node,'example.counter');name=next(iter(node.tools)).name
        self.assertEqual(next(iter(node.tools)).invoke(amount=2),2)
        self.backend.save(full=True);self.backend.restore(self.backend.snapshot())
        tool=next(iter(self.backend.network.get('mounted').tools));self.assertEqual(tool.name,name);self.assertEqual(tool.invoke(amount=3),5)
        self.studio.maker_tool({'id':id,'tool':'write_file','arguments':{'path':'README.md','content':'已变化'}})
        with self.assertRaisesRegex(ValueError,'Test the current'):self.studio.publish({'id':id})

    def test_validation_uses_isolated_current_graph_and_real_candidate(self):
        from domain.core import Node,NodeInfo,MarkdownNode,Link
        file=self.backend.directory/'ledger.md';file.write_text('正式资料',encoding='utf-8')
        reader=Node(NodeInfo('reader','读取者'));data=MarkdownNode(NodeInfo('ledger','资料'),file)
        self.backend.network.add(reader);self.backend.network.add(data);reader.links.add(Link('ledger',['docs']))
        work=self.studio.create({'kind':'module'});id=work['id']
        test="""import unittest
from app.studio.network_testing import NetworkHarness
class CurrentGraph(unittest.IsolatedAsyncioTestCase):
    async def test_current_graph(self):
        h=NetworkHarness()
        try:
            self.assertEqual(h.read('ledger'),'正式资料')
            h.mount('reader',module='example.counter')
            self.assertEqual((await h.call('reader','reader','example.counter','increment',{'amount':7}))['data'],7)
            h.write('ledger','仅修改隔离副本')
            await h.restart()
            self.assertEqual(h.read('ledger'),'仅修改隔离副本')
            self.assertEqual((await h.call('reader','reader','example.counter','increment',{'amount':1}))['data'],8)
        finally:await h.close()
"""
        self.studio.maker_tool({'id':id,'tool':'write_file','arguments':{'path':'tests/test_graph.py','content':test}})
        job=self.studio.validate({'id':id,'timeout':60});deadline=time.monotonic()+60
        while job['status']=='running' and time.monotonic()<deadline:
            time.sleep(.05);job=self.studio.job({'job':job['id']})
        self.assertEqual(job['status'],'passed',job['log']);self.assertIn('测试数量：1',job['log'])
        self.assertEqual(file.read_text(encoding='utf-8'),'正式资料')
        self.assertIsNone(reader.modules.get('example.counter'))
