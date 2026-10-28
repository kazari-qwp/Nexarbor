from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.runtime.backend import Backend
from app.network_saver import NetworkSaver
from app.studio.reachable import reachable_view
from domain.core import CallableTool, Link, Network, Node, NodeInfo
from domain.agent import AgentNode
from modules.tool_discovery import ToolDiscoveryModule

ROOT=Path(__file__).resolve().parents[1]

class ReachableViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_uses_actual_channels_strength_and_no_ownership_shortcuts(self):
        with TemporaryDirectory(dir=ROOT/'build') as folder:
            actor=AgentNode(NodeInfo('actor','Actor'))
            actor.install(ToolDiscoveryModule('tools',2))
            target=Node(NodeInfo('target','Target'));target.install(CallableTool('read_number',lambda:42))
            isolated=Node(NodeInfo('isolated','Isolated'))
            actor.links.add(Link('target',('tools','a'),threshold=2))
            saver=NetworkSaver();saver.tables.tool_types['read_number']=lambda node,record:next(iter(node.tools))
            backend=Backend(folder,network=Network([actor,target,isolated]),saver=saver)
            try:
                view=await reachable_view(backend,dict(actor='actor',strength=2))
                self.assertEqual([n['id'] for n in view['reachable']['a']],['actor','target'])
                self.assertEqual([t['name'] for t in view['tools']],['read_number'])
                self.assertNotIn('isolated',repr(view['reachable']))
                self.assertTrue(all('path' not in n and 'remaining' not in n for nodes in view['reachable'].values() for n in nodes))
                blocked=await reachable_view(backend,dict(actor='actor',strength=1))
                self.assertEqual([n['id'] for n in blocked['reachable']['a']],['actor'])
            finally:backend.close()
