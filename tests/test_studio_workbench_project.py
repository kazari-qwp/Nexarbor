"""通用工作台加载真实项目与空白项目，模板复制保留真实宿主工具。"""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from app.studio.project import WorkbenchProject
from adapt.harness.backend.transport import Transport
ROOT=Path(__file__).resolve().parents[1]
class WorkbenchProjectTests(unittest.TestCase):
    def test_blank_project_data_templates_and_real_town_use_same_project_loader(self):
        with TemporaryDirectory(prefix='workbench-project-',dir=ROOT/'build') as temp:
            home=Path(temp);blank=home/'blank';blank.mkdir();(blank/'nexarbor.json').write_text(json.dumps({'format':'nexarbor-project/v2','resources':{'modules':{}},'networks':{}}),encoding='utf-8')
            for folder,count,library_count in [(blank,1,9),(ROOT/'resources/examples/npc-town',52,24)]:
                project=WorkbenchProject(home/('runtime-'+str(count)),folder);transport=Transport(project.backend,StringIO())
                try:
                    self.assertEqual(len(transport.dispatch('studio_state',{})['live']['document']['network']['nodes']),count)
                    self.assertEqual(len(transport.dispatch('studio_catalog',{})['library']),library_count)
                    self.assertEqual([row['id'] for row in transport.dispatch('data_templates',{})],['value','csv','sqlite','rag','wiki'])
                finally:transport.close()

    def test_template_copies_actual_host_tool_names_and_keeps_nested_business_tool_keys(self):
        with TemporaryDirectory(prefix='workbench-template-',dir=ROOT/'build') as temp:
            home=Path(temp);folder=home/'project';folder.mkdir()
            metadata={'format':'nexarbor-project/v2','activeNetwork':'main','resources':{'modules':{}},'networks':{'main':{'file':'network.json'}}}
            (folder/'nexarbor.json').write_text(json.dumps(metadata),encoding='utf-8')
            from domain.core import Node,NodeInfo,Network
            from app.network_saver import NetworkSaver
            record=NetworkSaver().document(Network([Node(NodeInfo('caller','入口')),Node(NodeInfo('provider','端口'))]),folder)['nodes']
            manifest={'format':'nexarbor-project-network/v2','nodes':[{'file':'caller.json'},{'file':'provider.json'}],'files':[],'properties':{'provider':{'offered_ports':[{'ref':'runtime:checkpoint','channels':['runtime.checkpoint']}] }},'runtime':{},'signals':{}}
            for item in record:(folder/(item['node_id']+'.json')).write_text(json.dumps(item),encoding='utf-8')
            (folder/'network.json').write_text(json.dumps(manifest),encoding='utf-8')
            project=WorkbenchProject(home/'runtime',folder);transport=Transport(project.backend,StringIO())
            try:
                from app.projects.host_tools import host_tool_name
                provider=project.backend.network.get('provider')
                project.backend.save();snapshot=project.backend.snapshot();prototype=deepcopy(next(node for node in snapshot['network']['nodes'] if node['node_id']=='provider'))
                project.templates.configure([{'id':'provider-copy','callers':['caller'],'document':{'network':{'nodes':[prototype],'properties':manifest['properties']},'files':{}},'arguments_schema':{'type':'object','additionalProperties':False},'bindings':[],'attachments':[]}])
                result=transport.runtime.run(project.templates.instantiate('caller',template='provider-copy',key='one',arguments={}))
                id=result['node_ids']['provider'];tool=next(iter(project.backend.network.get(id).tools));self.assertEqual(tool.name,host_tool_name(id,'runtime:checkpoint'))
                commit=transport.runtime.run(tool.invoke(full=False));self.assertIsInstance(commit,int)
                arbitrary={'node_id':'new','tables':{'modules':[{'module_id':'unknown','config':{'tool':{'path':'business'}},'tools':{'group':1,'members':[]}}]}}
                project.remap_factory_tools(arbitrary,'old');self.assertEqual(arbitrary['tables']['modules'][0]['config']['tool'],{'path':'business'})
            finally:transport.close()
