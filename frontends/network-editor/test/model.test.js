import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionChannels,edgesOf,filterGraph,layoutNodes,removeNode,stackVisible} from '../src/model.js';
const document={network:{nodes:[{node_id:'root',name:'Root',type:'agent',modules:{},connections:{read_interfaces:[{target_node_id:'b',metadata:{channels:[]}}],write_interfaces:[]}},{node_id:'b',name:'Clock',type:'text_file',modules:{},connections:{read_interfaces:[],write_interfaces:[{target_node_id:'root',metadata:{channels:['tick']}}]}}]}};
test('filters never invent reach or mutate actual graph',()=>{
 const nodes=layoutNodes(document),edges=edgesOf(document);assert.equal(edges.length,2);
 assert.equal(filterGraph(nodes,edges,{channels:['tick']}).edges.length,1);
 assert.equal(filterGraph(nodes,edges,{kinds:['文本']}).nodes[0].id,'b');
 const local={actor:'root',paths:{read:[],write:[]}};
 assert.equal(filterGraph(nodes,edges,{local}).nodes.length,1);
 assert.equal(document.network.nodes[0].connections.read_interfaces.length,1);
});
test('deleting a node cleans edges and keeps root',()=>{
 const next=removeNode(document,'b');assert.equal(next.network.nodes.length,1);assert.equal(next.network.nodes[0].connections.read_interfaces.length,0);
 assert.throws(()=>removeNode(document,'root'));assert.equal(document.network.nodes.length,2);
});
test('visibility switches distinguish all, none and ordinary connections',()=>{
 const nodes=[...layoutNodes(document),{id:'isolated',data:{kind:'节点',node:{name:'Isolated'}}}],edges=edgesOf(document);
 const kinds=['Agent','文本','节点'],channels=connectionChannels(edges);
 assert.equal(filterGraph(nodes,edges,{kinds,channels}).nodes.length,3);
 assert.equal(filterGraph(nodes,edges,{kinds:[],channels}).nodes.length,0);
 assert.equal(filterGraph(nodes,edges,{kinds,channels:[]}).nodes.length,0);
 assert.equal(filterGraph(nodes,edges,{kinds,channels:[]}).edges.length,0);
 const ordinary=filterGraph(nodes,edges,{kinds,channels:[null]});
 assert.equal(ordinary.edges.length,1);assert.equal(ordinary.edges[0].direction,'read');
 assert.equal(ordinary.nodes.length,2);
 assert.equal(filterGraph(nodes,edges,{kinds:['Agent','节点'],channels}).nodes.some(n=>n.id==='b'),false);
 assert.deepEqual(document.network.nodes[0].connections.read_interfaces[0].metadata.channels,[]);
});

test('new nodes and re-enabled filters rise above existing nodes and edges',()=>{
 const a=stackVisible(null,[{id:'a'},{id:'b'}],[{id:'ab'}]);
 const b=stackVisible(a,[{id:'a'}],[]),c=stackVisible(b,[{id:'a'},{id:'b'},{id:'c'}],[{id:'ab'}]);
 assert.equal(c.nodes.a,a.nodes.a);assert.ok(c.edges.ab>a.nodes.b);assert.ok(c.nodes.b>c.edges.ab);assert.ok(c.nodes.c>c.nodes.b);
});
