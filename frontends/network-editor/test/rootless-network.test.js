import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {currentTownDocument} from '../../../adapters/harness/studio/town-layout.mjs';
import {editorLibrary} from '../../../adapters/harness/framework/editor-library.js';
import {pasteSubnet} from '../src/subnets.js';
import {contentType,matchesType} from '../src/resources.js';
import {removeNode} from '../src/model.js';
const base=path.resolve('build/rootless-library-tests');
test('complete rootless and empty networks can be stored and reopened as real files',async()=>{
 await fs.mkdir(base,{recursive:true});const home=await fs.mkdtemp(path.join(base,'run-')),library=editorLibrary(home);
 for(const nodes of [[],[{node_id:'place',name:'地方',modules:{},management_parent_id:null,connections:{interfaces:[]}}]]){
  const document={network:{version:8,nodes,signals:{},delegations:[]},files:{}};
  const result=await library('editor.library.update',{action:'network.save',name:'网络-'+nodes.length,document});const preset=result.presets.find(p=>p.name==='网络-'+nodes.length);
  assert.equal(preset.storageKind,'network');assert.equal(preset.snapshot.nodes.length,nodes.length);assert.equal(preset.hasRoot,false);assert.deepEqual(JSON.parse(await fs.readFile(preset.file,'utf8')),document);
 }
});
test('deleting any node clears its management, incident edges and explicit delegations',()=>{
 const document={network:{nodes:[{node_id:'root',connections:{interfaces:[]}},{node_id:'a',management_parent_id:'root',connections:{interfaces:[{target_node_id:'root'}]}}],delegations:[{source:'root',target:'a'},{source:'a',target:'root'}]}};
 const result=removeNode(document,'root');assert.equal(result.network.nodes[0].management_parent_id,null);assert.deepEqual(result.network.nodes[0].connections.interfaces,[]);assert.deepEqual(result.network.delegations,[]);assert.equal(document.network.nodes.length,2);
});

test('empty complete presets remain networks rather than standalone edges',()=>{
 const empty={kind:'preset',storageKind:'network',snapshot:{nodes:[]}};
 assert.throws(()=>pasteSubnet({network:{nodes:[]}},empty,{x:0,y:0}),/空网络没有可拖入的节点/);
 assert.equal(contentType(empty),'network');assert.equal(matchesType(empty,'network'),true);
 assert.equal(contentType({snapshot:{nodes:[],edges:[{}]}}),'edge');
});

test('town removes only its unused observer and preserves a configured root',()=>{
 const observer={node_id:'root',type:'node',name:'小镇观察者',description:'',modules:{},parameters:{},connections:{interfaces:[]}};
 const graph={network:{nodes:[observer,{node_id:'place',management_parent_id:'root',connections:{interfaces:[]}}],delegations:[]}};
 const result=currentTownDocument(graph);assert.equal(result.changed,true);assert.equal(result.document.network.nodes.length,1);assert.equal(result.document.network.nodes[0].management_parent_id,null);
 for(const change of [g=>g.network.delegations.push({source:'root',target:'place'}),g=>g.network.nodes[0].description='我自己的观察入口',g=>g.network.nodes[0].modules={'custom':{}}]){
  const copy=structuredClone(graph);change(copy);assert.equal(currentTownDocument(copy).changed,false);
 }
});
