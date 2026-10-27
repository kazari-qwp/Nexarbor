"""组件静态契约、真实装配预检和作者 unittest；不宣称 Python 沙箱。"""
import ast
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from jsonschema import Draft202012Validator
from .contract import manifest
from .testing import ModuleHarness

async def preflight(folder):
    spec=manifest(folder)
    if os.environ.get('NEXARBOR_MAKER_KIND')=='tool' and not spec.get('agent_tools'):raise ValueError('工具制作必须声明 agent_tools')
    defaults=json.loads((folder/'example.json').read_text(encoding='utf-8'))
    Draft202012Validator(spec['config_schema']).validate(defaults['config'])
    Draft202012Validator(spec['state_schema']).validate(defaults.get('state',{}))
    h=ModuleHarness(folder)
    try:
        kind=spec['node_types'][0]
        if kind=='markdown':h.add_text('subject')
        elif kind=='pulse':
            from domain.pulse_node import PulseNode
            from domain.core import NodeInfo
            h.network.add(PulseNode(NodeInfo('subject','Subject'),channels=['pulse'],strength=3))
        elif kind in ('node','agent'):h.add_node('subject',agent=kind=='agent')
        else:raise ValueError('预检节点类型需要相应项目 DataNode 工厂：'+kind)
        instance=h.mount('subject',config=defaults['config'],state=defaults.get('state',{}),access=defaults.get('access'))
        for operation in spec['operations']:assert callable(getattr(instance,operation['name']))
        Draft202012Validator(spec['state_schema']).validate(getattr(instance,'state',{}))
    finally:await h.close()

def main():
    folder=Path(sys.argv[1]).resolve();os.chdir(folder)
    for file in folder.rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'),filename=str(file))
    asyncio.run(preflight(folder));sys.path.insert(0,str(folder))
    suite=unittest.defaultTestLoader.discover(str(folder/'tests'),pattern='test_*.py') if (folder/'tests').is_dir() else unittest.TestSuite()
    if (folder/'tests').is_dir() and any((folder/'tests').glob('test_*.py')) and not suite.countTestCases():raise ValueError('测试文件未收集到 unittest 用例')
    result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    print('PASS：v4 Module 入口、装配、接收器声明、状态与组件测试；测试数量：'+str(suite.countTestCases()))
if __name__=='__main__':main()
