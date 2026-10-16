"""Offline core demo: pulse -> text clock -> two Agents -> pulse. No model calls."""
import asyncio
import json
import tempfile
from pathlib import Path
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.interface import Interface
from datanet.core.pulse_node import PulseNode
from datanet.core.text_node import TextFileNode
from datanet.core.agent_node import AgentNode
from datanet.core.serialization import save_network,load_network

async def demo():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);network=Network()
        pulse=PulseNode('pulse','Pulse',channels=['demo.tick'],strength=3)
        clock=TextFileNode('clock','Time','text',root/'clock.md');clock.expose=[]
        network.add_node(pulse);network.add_node(clock)
        workers=[AgentNode(id,id,file_path=root/(id+'.md')) for id in ['worker-a','worker-b']]
        for worker in workers:network.add_node(worker)
        def link(source,target):network.nodes[source].write_interfaces.append(Interface(target,{'channels':['demo.tick'],'threshold':1}))
        link('pulse','clock')
        for worker in workers:
            link('clock',worker.node_id);link(worker.node_id,'pulse')
            # Private read edges expose the text to each worker, not to signal routing.
            worker.read_interfaces.append(Interface('clock',{'visibility':'private','threshold':1}))
        observations=[]
        async def update_clock(context):
            tick=context.signal.sequence-1;slots=['早','午','下午','傍晚','午夜']
            clock.write('content',f'第{tick//5+1}天-{slots[tick%5]}')
        async def work(context):
            await asyncio.sleep(.005)
            value=network.read(context.delivery.node_id,{'method':'key','key':'content'},strength=2)
            text=value.items[0]['content'];observations.append(dict(sequence=context.signal.sequence,worker=context.delivery.node_id,time=text))
            network.nodes[context.delivery.node_id].write_memory(text)
        network.signals.bind('clock',update_clock)
        for worker in workers:network.signals.bind(worker.node_id,work,access_strength=2)
        settled=[]
        async def settle(pulse,report):
            assert sum(x['sequence']==pulse.state['sequence'] for x in observations)==2
            settled.append(pulse.state['sequence'])
        result=await pulse.run(network.signals,cycles=2,cycle_complete=settle)
        assert result['cycles']==2 and all(r['returned'] for r in result['reports'])
        assert [x['time'] for x in observations]==['第1天-早','第1天-早','第1天-午','第1天-午']
        save_network(network,root/'network.json');restored=load_network(root/'network.json')
        assert restored.nodes['pulse'].state['sequence']==2
        await network.signals.close()
        return dict(cycles=result['cycles'],settled=settled,observations=observations,restored_sequence=restored.nodes['pulse'].state['sequence'])

if __name__=='__main__':print(json.dumps(asyncio.run(demo()),ensure_ascii=False,indent=2))
