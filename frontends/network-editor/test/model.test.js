import test from 'node:test';
import assert from 'node:assert/strict';
import {edgesOf,filterGraph,layoutNodes,removeNode} from '../src/model.js';
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
