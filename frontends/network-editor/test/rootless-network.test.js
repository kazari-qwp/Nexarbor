import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {readProjectBundle} from '../../../adapt/harness/studio/project.mjs';import {fileURLToPath} from 'node:url';import {editorNode} from '../../../adapt/harness/framework/editor-nodes.js';
import {editorLibrary} from '../../../adapt/harness/framework/editor-library.js';
import {pasteSubnet} from '../src/subnets.js';
import {contentType,matchesType} from '../src/resources.js';
import {removeNode} from '../src/model.js';
const base=path.resolve('build/rootless-library-tests');
test('complete rootless and empty networks can be stored and reopened as real files',async()=>{
 await fs.mkdir(base,{recursive:true});const home=await fs.mkdtemp(path.join(base,'run-')),library=editorLibrary(home);
 for(const nodes of [[],[editorNode('node','place','地方')]]){
  const document={network:{nodes,signals:{}},files:{}};
  const result=await library('editor.library.update',{action:'network.save',name:'网络-'+nodes.length,document});const preset=result.presets.find(p=>p.name==='网络-'+nodes.length);
  assert.equal(preset.storageKind,'network');assert.equal(preset.snapshot.nodes.length,nodes.length);assert.equal(preset.hasRoot,false);assert.deepEqual(JSON.parse(await fs.readFile(preset.file,'utf8')),document);
 }
});
test('deleting a node clears management references and incident edges',()=>{
 const document={network:{nodes:[{node_id:'root',links:[]},{node_id:'a',links:[{target_id:'root'}]}],properties:{root:{},a:{management_parent_id:'root'}}}};
 const result=removeNode(document,'root');assert.equal(result.network.properties.a.management_parent_id,null);assert.deepEqual(result.network.nodes[0].links,[]);assert.equal(document.network.nodes.length,2);
});

test('empty complete presets remain networks rather than standalone edges',async()=>{
 const empty={kind:'preset',storageKind:'network',snapshot:{nodes:[]}};
 await assert.rejects(pasteSubnet({network:{nodes:[]}},empty,{x:0,y:0}),/空网络没有可拖入的节点/);
 assert.equal(contentType(empty),'network');assert.equal(matchesType(empty,'network'),true);
 assert.equal(contentType({snapshot:{nodes:[],edges:[{}]}}),'edge');
});

test('rootless town is already migrated and saved custom observers are preserved',async()=>{
 const bundle=await readProjectBundle(fileURLToPath(new URL('../../../resources/examples/npc-town/',import.meta.url)));assert.ok(!bundle.document.network.nodes.some(n=>n.node_id==='root'));
 const document=structuredClone(bundle.document);document.network.nodes.push(editorNode('node','observer','自定义观察入口'));
 await fs.mkdir(base,{recursive:true});const home=await fs.mkdtemp(path.join(base,'observer-')),library=editorLibrary(home);
 const saved=await library('editor.library.update',{action:'network.save',name:'含自定义观察者',document});
 assert.ok(saved.presets[0].snapshot.nodes.some(n=>n.node_id==='observer'));assert.ok(document.network.nodes.some(n=>n.node_id==='observer'));
});
