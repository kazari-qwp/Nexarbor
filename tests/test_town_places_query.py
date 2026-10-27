"""处境仅展示同地公开资料，地图只包含授权普通地点。"""

import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester
from domain.agent import AgentNode
from domain.annotated_link import AnnotatedLink
from domain.core import Network, Node, NodeInfo
from projects.npc_town.modules.place_info import PlaceInfoModule
from projects.npc_town.modules.places_query import PlacesQueryModule
from projects.npc_town.modules.places_query.scene import Roads, map_graph
from projects.npc_town.modules.records_store import RecordsStoreModule

ROOT=Path(__file__).resolve().parents[1]


class PlacesQueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(prefix='.places-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.a=AgentNode(NodeInfo('a','A'));self.b=AgentNode(NodeInfo('b','Private name B'));self.c=AgentNode(NodeInfo('c','Private name C'))
        self.home=Node(NodeInfo('home','Home','Home description'));self.park=Node(NodeInfo('park','Park','Green park'))
        self.net=Network([self.a,self.b,self.c,self.home,self.park]);self.saver=NetworkSaver()
        self.backend=Backend(self.temp.name,network=self.net,saver=self.saver);self.addCleanup(self.backend.close)
        self.a.install(RecordsStoreModule({'initial':{'name':'Alice','ap':3,'secret':'never publish'}}))
        self.b_records=RecordsStoreModule({'initial':{'name':'Public Bob','profession':'baker','secret':'B secret'}})
        self.b.install(self.b_records)
        self.a.install(PlaceInfoModule({'location':'home'}));self.b.install(PlaceInfoModule({'location':'home'}))
        self.c.install(PlaceInfoModule({'location':'park'}))
        self.home.install(PlaceInfoModule({'visitors':['a','b']}));self.park.install(PlaceInfoModule())
        self.query=PlacesQueryModule(strength=3);self.a.install(self.query)
        self.b_query=PlacesQueryModule(strength=3);self.b.install(self.b_query)
        for source,target,relation in [('a','home','location'),('home','a','location'),('home','b','location'),('home','park','road'),('park','home','road'),('park','c','location')]:
            self.net.get(source).links.add(AnnotatedLink(target,['location','road'],attributes={'relation':relation}))
        self.saver.tables.module_types.update({'records.store':lambda spec:RecordsStoreModule(),'place.info':lambda spec:PlaceInfoModule(),'places.query':lambda spec:PlacesQueryModule()})
        with as_requester('b'):await self.b_query.publish()

    async def test_scene_uses_only_registered_visitors_and_published_profile(self):
        with patch.object(self.b_records,'read',side_effect=AssertionError('private records read')):
            with as_requester('a'):scene=await self.query.look()
        self.assertEqual(scene['people'],[{'id':'b','name':'Public Bob','profile':{'name':'Public Bob','profession':'baker'}}])
        self.assertEqual(scene['exits'],[{'id':'park','name':'Park'}])
        self.assertEqual(scene['location'],{'id':'home','name':'Home'})
        self.assertEqual(scene['records']['ap'],3)
        self.assertNotIn('B secret',str(scene));self.assertNotIn('Private name C',str(scene))

    async def test_unpublished_person_name_is_not_inferred_from_node_name(self):
        self.b_query.published={}
        scene=await self.query.look()
        self.assertEqual(scene['people'][0]['name'],'姓名未公开')
        self.assertEqual(scene['people'][0]['profile'],{})

    async def test_explicit_publication_and_owner_permission(self):
        self.assertEqual(await self.query.publish(),{'name':'Alice'})
        with as_requester('b'):
            for operation in (self.query.publish,self.query.look,self.query.map):
                with self.assertRaises(PermissionError):await operation()

    async def test_place_lookup_current_name_ambiguity_and_private_targets(self):
        self.assertEqual((await self.query.place())['id'],'home')
        self.assertEqual((await self.query.place('Park'))['id'],'park')
        with self.assertRaises(ValueError):await self.query.place('b')
        duplicate=Node(NodeInfo('other','Park'));duplicate.install(PlaceInfoModule());self.net.add(duplicate)
        self.home.links.add(AnnotatedLink('other','road',attributes={'relation':'road'}))
        with self.assertRaisesRegex(ValueError,'同名'):await self.query.place('Park')

    async def test_map_preserves_original_renderer_and_excludes_agents(self):
        views=await Roads(self.query).collect();graph=await map_graph(self.query,self.a,views)
        self.assertEqual([node['id'] for node in graph['places']],['home','park'])
        self.assertEqual(graph['roads'],[{'from':'home','to':'park','bidirectional':True}])
        result=await self.query.map()
        self.assertEqual(result['format'],'nexarbor-tool-content/v1')
        self.assertTrue(base64.b64decode(result['content'][1]['data']).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertIn('Home=home',result['content'][0]['text'])

    async def test_channel_and_strength_limits_restrict_map(self):
        self.query.config['road_channels']=['blocked']
        with self.assertRaisesRegex(ValueError,'没有可绘制'):await self.query.map()
        self.query.config['road_channels']=['location','road'];self.park.bias=-10
        views=await Roads(self.query).collect()
        self.assertNotIn('park',views);self.assertNotIn('c',views)
