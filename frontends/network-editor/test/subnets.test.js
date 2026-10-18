import test from 'node:test';import assert from 'node:assert/strict';
import {copySubnet,pasteSubnet,selectionStep,bookmarkChanges} from '../src/subnets.js';
import {keyMatches,pointerMatches} from '../src/shortcuts.js';
const edge=target=>({target_node_id:target,metadata:{channels:['tools'],threshold:1,multiplier:1,attributes:{label:'边参数'}}});
const node=id=>({node_id:id,name:id,type:'agent',parameters:{file_path:id+'.md'},management_parent_id:null,context_cursor:{session_id:'old'},connections:{interfaces:[]},modules:{}});
const a=node('a'),b=node('b'),c=node('c');a.connections.interfaces=[edge('b'),edge('c')];b.connections.interfaces=[edge('a')];
const document={network:{nodes:[a,b,c]},files:{'a.md':'a记忆','b.md':'b记忆','c.md':'c记忆','unused.md':'不复制'}};
test('A trims external links; B keeps them; neither changes source or copies unrelated documents',()=>{
 const internal=copySubnet(document,['a','b'],'internal'),external=copySubnet(document,['a','b'],'external');
 assert.deepEqual(internal.nodes[0].connections.interfaces.map(e=>e.target_node_id),['b']);assert.equal(external.nodes[0].connections.interfaces.length,2);
 assert.deepEqual(Object.keys(external.files),['a.md','b.md']);assert.equal(a.context_cursor.session_id,'old');assert.equal(internal.nodes[0].context_cursor,null);
 const paste=pasteSubnet(document,{snapshot:external},{x:300,y:400});const copied=paste.document.network.nodes.slice(3);
 assert.notEqual(copied[0].node_id,'a');assert.equal(copied[0].connections.interfaces[0].target_node_id,copied[1].node_id);assert.equal(copied[0].connections.interfaces[1].target_node_id,'c');
 assert.notEqual(copied[0].parameters.file_path,'a.md');assert.equal(paste.document.files[copied[0].parameters.file_path],'a记忆');assert.equal(copied[0].context_cursor,null);
});
test('pure edge A has no endpoints, B only retains destination',()=>{
 const x=copySubnet(document,[],'internal',{},['a|0']),y=copySubnet(document,[],'external',{},['a|0']);
 assert.deepEqual(Object.keys(x.edges[0]),['metadata']);assert.deepEqual(Object.keys(y.edges[0]),['metadata','target']);assert.equal(y.edges[0].target,'b');
 assert.equal(x.edges[0].metadata.attributes.label,'边参数');assert.deepEqual(pasteSubnet(document,{snapshot:x},{x:0,y:0}).edges,x.edges);
});
test('selection wheel advances one incidence layer at a time',()=>{
 const nodes=['a','b','c'].map(id=>({id})),edges=[{id:'ab',source:'a',target:'b'},{id:'bc',source:'b',target:'c'}];
 let selected=selectionStep(nodes,edges,{nodes:['a'],edges:[]});assert.deepEqual(selected,{nodes:['a'],edges:['ab']});
 selected=selectionStep(nodes,edges,selected);assert.deepEqual(selected,{nodes:['a','b'],edges:['ab']});
 selected=selectionStep(nodes,edges,selected);assert.deepEqual(selected.edges,['ab','bc']);
 assert.deepEqual(selectionStep(nodes,edges,{nodes:['a'],edges:[]},false),{nodes:[],edges:[]});
});
test('bookmark undo patch touches only changed entries and key bindings match modifiers',()=>{
 const x={id:'x',name:'x'},y={id:'y',name:'y'};assert.deepEqual(bookmarkChanges([x],[x,y]),[{id:'y',expected:null,value:y}]);
 assert.equal(keyMatches({key:'z',ctrlKey:true},'Ctrl+Z'),true);assert.equal(keyMatches({key:'z',ctrlKey:true,shiftKey:true},'Ctrl+Z'),false);
 assert.equal(pointerMatches({button:2,altKey:true},{button:2,modifier:'Alt'}),true);
});
