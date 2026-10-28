import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {storedNetworks} from '../../../adapt/harness/framework/stored-networks.js';
import {editorLibrary} from '../../../adapt/harness/framework/editor-library.js';
import {editorNodes} from '../../../adapt/harness/framework/editor-nodes.js';
const root=path.resolve('build/startup-resource-tests');
async function setup(){await fs.mkdir(root,{recursive:true});const directory=await fs.mkdtemp(path.join(root,'run-')),store=storedNetworks(directory),snapshot=structuredClone(editorNodes()[0].snapshot);snapshot.nodes[0].tables.modules=[{module_id:'example.module',config:{},state:{},strength:0,channels:[]}];const document={network:{nodes:snapshot.nodes,signals:{},delegations:[]},files:{'large.txt':'独立数据'.repeat(100000)}};const saved=await store.save({storageKind:'network',document,editor:{name:'按需完整网络'}});return {directory,store,saved,document};}

test('directory index excludes payload; hydration keeps full data and validates changed source',async()=>{
 const {directory,store,saved,document}=await setup(),library=editorLibrary(directory);
 const index=await library('editor.library.index');assert.equal(index.presets[0].snapshot,undefined);assert.equal(index.presets[0].lazySnapshot,true);assert.equal(index.presets[0].nodeCount,1);assert.ok(JSON.stringify(index).length<3000);
 const full=await library('editor.resource.load',{kind:'preset',id:saved.id});assert.deepEqual(full.snapshot.files,document.files);
 // 摘要不是校验缓存。正文被改坏时，真正使用必须重新检查并拒绝。
 await fs.writeFile(saved.file,'{broken');assert.ok((await store.list({summary:true})).errors.length);await assert.rejects(library('editor.resource.load',{kind:'preset',id:saved.id}));
 await assert.rejects(store.load('network:../outside.json'),/编号无效/);
});

test('index updates stay small; archive stores independent payload and deletion still checks disk references',async()=>{
 const {directory,saved,document}=await setup();let purged=false;
 const library=editorLibrary(directory,{catalog:async()=>({modules:{'example.module':{label:'示例',defaults:{config:{}}}}}),inspect:async()=>({canDelete:true}),purge:async()=>purged=true});
 const view=await library('editor.library.update',{summary:true,action:'settings.save',settings:{bookmarkView:'icons'}});assert.equal(view.presets[0].snapshot,undefined);
 const info=await library('editor.resource.inspect',{kind:'module',id:'example.module'});assert.equal(info.canDelete,false);
 await library('editor.library.update',{summary:true,action:'asset.archive',kind:'module',entries:[{id:'example.module'}]});
 await assert.rejects(library('editor.library.update',{summary:true,action:'asset.purge',kind:'module',id:'example.module',confirm:'example.module'}),/仍引用/);assert.equal(purged,false);
 const archived=await library('editor.library.update',{summary:true,action:'asset.archive',kind:'preset',entries:[{id:saved.id}]});assert.deepEqual(archived.assets.preset.items[saved.id].resource.snapshot.files,document.files);
});


test('raw stored network loads before caller templates; reopening keeps edited checkpoint and real template instance',async t=>{
 const {startStudio}=await import('../../../adapt/harness/studio/host.mjs'),{editorNode}=await import('../../../adapt/harness/framework/editor-nodes.js');
 const base=await fs.mkdtemp(path.resolve('../../build/initial-network-order-')),directory=path.join(base,'project'),source=path.join(base,'network.json');
 const document={network:{nodes:[editorNode('node','caller','完整网络调用者')]},files:{}};await fs.writeFile(source,JSON.stringify(document));
 const child=editorNode('node','new','实际模板子项');child.tables.tools={group:0,members:[{modules:true}]};
 const templates=[{id:'child',callers:['caller'],document:{network:{nodes:[child]},files:{}},arguments_schema:{type:'object',properties:{},additionalProperties:false},bindings:[],attachments:[]}];
 let host;try{
  host=await startStudio({directory,initialNetwork:source,templates});let state=await host.request('state',{});assert.deepEqual(state.live.document.network.nodes.map(n=>n.node_id),['caller']);
  const result=await host.rpc('template_instantiate',{actor:'caller',template:'child',key:'created',arguments:{}});const id=result.node_ids.new;assert.ok(id);
  state=await host.request('state',{});state.live.document.network.nodes.find(n=>n.node_id==='caller').name='保存后的名称';await host.request('apply',{document:state.live.document,base_commit:state.live.commit});
  await host.close();host=null;host=await startStudio({directory,initialNetwork:source,templates});const cold=await host.request('state',{});assert.equal(cold.live.document.network.nodes.find(n=>n.node_id==='caller').name,'保存后的名称');assert.ok(cold.live.document.network.nodes.some(n=>n.node_id===id));
  assert.equal((await host.rpc('template_instantiate',{actor:'caller',template:'child',key:'created',arguments:{}})).duplicate,true);
 }finally{await host?.close();}
});
