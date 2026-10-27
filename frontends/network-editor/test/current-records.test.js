import test from 'node:test';
import assert from 'node:assert/strict';
import {assembleResources} from '../../shared/graph/resource-assembly.js';
import {moduleTable,moduleAccess} from '../../shared/graph/node-records.js';
import {edgesOf,layoutNodes,filterGraph,removeNode} from '../src/model.js';
import {mergeDataEdit,mergeClearedData,isDataNode} from '../src/data-edit.js';
const record=(id,type='node')=>({node_id:id,name:id,type,links:[],tables:{modules:[]},...(type==='markdown'?{data:{path:'data/'+id+'.md',directory:false,save_data:true}}:{})});
test('resource assembly preserves live state and tool tables while mounting dependencies, host offers and Skills',()=>{
 const node=record('actor','agent');node.execution={executor:'harness'};
 node.tables.modules=[{module_id:'existing',config:{old:true},state:{count:7},channels:['a'],strength:2,tools:{group:1,members:[{tool:'actual-published-tool'}]}}];
 const document={network:{nodes:[node]},files:{}};
 const catalog={modules:{existing:{node_types:['agent'],requires:[]},base:{node_types:['agent'],requires:[]}},tools:[{ref:'external',channels:['tools']}],skills:{memo:{requires:['base'],tools:['external'],skills:[]}}};
 const before=structuredClone(document),oldTools=structuredClone(node.tables.modules[0].tools);
 const next=assembleResources(document,'actor',[{kind:'module',id:'existing',config:{new:true}},{kind:'skill',id:'memo'}],catalog);
 assert.deepEqual(document,before);const result=next.network.nodes[0];assert.deepEqual(moduleTable(result).existing.state,{count:7});assert.deepEqual(moduleAccess(moduleTable(result).existing),{channels:['a'],strength:2});assert.deepEqual(moduleTable(result).existing.tools,oldTools);
 assert.ok(moduleTable(result).base);assert.deepEqual(result.execution.skills,['memo']);assert.deepEqual(next.network.properties.actor.offered_ports,[{ref:'external',channels:['tools']}]);
 assert.equal(result.modules,undefined);assert.equal(result.offered_tools,undefined);assert.equal(result.skills,undefined);
 assert.throws(()=>assembleResources(document,'actor',[{kind:'module',id:'missing'}],catalog),/缺少/);assert.deepEqual(document,before);
});
test('current Link records preserve channel filtering and deletion removes only selected data and incoming edges',()=>{
 const a=record('a','agent'),b=record('b','markdown');a.links=[{target_id:'b',channels:['context'],threshold:1,processor:{type:'multiplier',factor:2}}];b.links=[{target_id:'a',channels:['tick'],processor:{type:'multiplier',factor:1}}];
 const document={network:{nodes:[a,b],properties:{a:{},b:{management_parent_id:'a'}}},files:{}};
 const edges=edgesOf(document);assert.equal(edges.length,2);assert.equal(edges[0].metadata.multiplier,2);
 assert.equal(filterGraph(layoutNodes(document),edges,{channels:['context']}).edges.length,1);
 assert.equal(layoutNodes(document).find(node=>node.id==='b').data.kind,'文本');
 const remaining=removeNode(document,'a');assert.equal(remaining.network.nodes.length,1);assert.equal(remaining.network.nodes[0].links.length,0);assert.equal(remaining.network.properties.b.management_parent_id,null);assert.equal(document.network.nodes.length,2);
});
test('actual DataNode path guards drafts against concurrent file changes and clear retains pending configuration',()=>{
 const node=record('one','markdown'),before={network:{nodes:[node]},files:{'data/one.md':'old','other.md':'keep'}};
 const value={beforeNode:structuredClone(node),beforeFiles:structuredClone(before.files),node:structuredClone(node),files:{'data/one.md':'new'}};
 const result=mergeDataEdit(before,value);assert.equal(result.files['data/one.md'],'new');assert.equal(before.files['data/one.md'],'old');
 const concurrent=structuredClone(before);concurrent.files['data/one.md']='concurrent';assert.throws(()=>mergeDataEdit(concurrent,value),/数据已经变化/);
 const draft=structuredClone(before);draft.network.nodes[0].name='pending';const clear=mergeClearedData(draft,{beforeNode:node,node,roots:[['data/one.md','file']],files:{'data/one.md':''}});
 assert.equal(clear.network.nodes[0].name,'pending');assert.equal(clear.files['other.md'],'keep');assert.equal(clear.files['data/one.md'],'');assert.ok(isDataNode(node));assert.ok(!isDataNode(record('plain')));
});
