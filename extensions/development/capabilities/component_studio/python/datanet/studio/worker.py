"""Parent enforces a deadline; this executes code with ordinary OS privileges."""
import ast
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from datanet.studio.contract import factory
from datanet.core.node import Node
from datanet.core.text_node import TextFileNode
from datanet.core.network import Network
from datanet.core.signals import Signal
from datanet.core.agent_node import AgentNode
from datanet.core.pulse_node import PulseNode

def main():
    folder=Path(sys.argv[1]).resolve()
    os.chdir(folder)
    for file in folder.rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'),filename=str(file))
    spec,create=factory(folder)
    defaults=json.loads((folder/'example.json').read_text(encoding='utf-8'))
    kind=spec['node_types'][0]
    node=TextFileNode('subject','Subject','text',folder/'test-output.txt') if kind=='text_file' else AgentNode('subject','Subject',file_path=folder/'memory.md') if kind=='agent' else PulseNode('subject','Subject',channels=['world.tick'],strength=3) if kind=='pulse' else Node('subject','Subject',None)
    network=Network();network.add_node(node)
    saves=[]
    backend=SimpleNamespace(network=network,dispatch=lambda *a,**k:saves.append((a,k)) or {'saved':True})
    instance=create(backend,node,defaults['config'],{});instance.install()
    assert set(node.tool_definitions)==set(t['name'] for t in spec['tools'])|({'read','write'} if kind=='text_file' else set())
    for tool in spec['tools']:
        actual=node.tool_definitions[tool['name']]
        assert 'read_only' not in actual and 'access_channels' in actual
    if spec['signals']:
        signal=Signal('origin',spec['signals'],2)
        context=SimpleNamespace(signal=signal,delivery=SimpleNamespace(node_id=node.node_id,strength=1),network=network)
        value=instance.on_signal(context)
        if hasattr(value,'__await__'):asyncio.run(value)
        from jsonschema import validate
        validate(instance.state,spec['state_schema'])
        sample=sys.argv[2] if len(sys.argv)>2 else 'blank'
        sample={'ready_clock':'town_clock','ready_savepoint':'town_savepoint'}.get(sample,sample)
        if sample in ['town_clock','town_savepoint']:
            previous=json.dumps(instance.state,sort_keys=True)
            result=instance.on_signal(context)
            if hasattr(result,'__await__'):asyncio.run(result)
            assert json.dumps(instance.state,sort_keys=True)==previous,'Same signal must not execute twice'
            count=len(defaults['config']['slots']) if sample=='town_clock' else defaults['config']['interval']
            for _ in range(count):
                context.signal=Signal('origin',spec['signals'],2,content={'clock':'same payload'})
                value=instance.on_signal(context)
                if hasattr(value,'__await__'):asyncio.run(value)
            if sample=='town_clock':
                expected=defaults['config']['format'].format(day=2,slot=defaults['config']['slots'][0],tick=count)
                assert node.read({'method':'key','key':'content'}).items[0]['content']==expected,'World clock must wrap to day 2'
            else:
                assert instance.state['count']==count+1,'Savepoint count must persist across signals'
                assert any(args and args[0]=='save' and len(args)>1 and args[1].get('full') for args,kwargs in saves),'Interval must request a full snapshot'
    instance.close()
    sys.path.insert(0,str(folder))
    suite=unittest.defaultTestLoader.discover(str(folder/'tests'),pattern='test_*.py') if (folder/'tests').exists() else unittest.TestSuite()
    result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    print('PASS: v7 contract, mount, tool declarations, signal callback, state schema, module tests')

if __name__=='__main__':main()
