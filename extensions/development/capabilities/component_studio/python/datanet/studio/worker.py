"""Bounded contract worker. Ordinary OS privileges, no claimed Python sandbox."""
import ast
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from datanet.studio.contract import factory
from datanet.core.node import Node
from datanet.core.node_modules import NodeModules
from datanet.core.text_node import TextFileNode
from datanet.core.network import Network
from datanet.core.signals import Signal
from datanet.core.agent_node import AgentNode
from datanet.core.pulse_node import PulseNode


def main():
    folder=Path(sys.argv[1]).resolve()
    os.chdir(folder)
    for file in folder.rglob('*.py'):
        ast.parse(file.read_text(encoding='utf-8'),filename=str(file))
    spec,create=factory(folder)
    defaults=json.loads((folder/'example.json').read_text(encoding='utf-8'))
    kind=spec['node_types'][0]
    if kind=='text_file':node=TextFileNode('subject','Subject','text',folder/'test-output.txt')
    elif kind=='agent':node=AgentNode('subject','Subject',file_path=folder/'memory.md')
    elif kind=='pulse':node=PulseNode('subject','Subject',channels=['pulse'],strength=3)
    else:node=Node('subject','Subject',None)
    baseline=set(node.tool_definitions)
    network=Network();network.add_node(node)
    backend=SimpleNamespace(network=network,metadata_registry=network.metadata_registry,
        _transaction_lock=RLock(),components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
    backend.signals=network.signals
    backend.modules=NodeModules(backend,{spec['id']:create})
    try:
        instance=backend.modules.mount(node.node_id,spec['id'],defaults['config'],defaults.get('state',{}),
            access=defaults.get('access'))
        assert set(instance.operations) == {op['name'] for op in spec['operations']}
        assert set(node.tool_definitions) == baseline
        if spec['signals']:
            origin=Node('contract-origin','Contract origin',None);network.add_node(origin)
            origin.connect(node.node_id,channels=spec['signals'])
            report=asyncio.run(network.propagate(Signal(origin.node_id,spec['signals'],2,
                node_timeout_seconds=10,timeout_seconds=15)))
            assert report['status']=='completed',report
        from jsonschema import validate
        validate(instance.state,spec['state_schema'])
    finally:
        backend.modules.clear()
    sys.path.insert(0,str(folder))
    suite=unittest.defaultTestLoader.discover(str(folder/'tests'),pattern='test_*.py') if (folder/'tests').exists() else unittest.TestSuite()
    result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    print('PASS: fixed v3 contract, mount, declarations, data-only signal, state schema, module tests')


if __name__=='__main__':main()
