import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {editorLibrary} from '../../../adapters/harness/framework/editor-library.js';
import {editorNode,editorNodes} from '../../../adapters/harness/framework/editor-nodes.js';
import {storedNodes} from '../../../adapters/harness/framework/stored-networks.js';
import {copySubnet,pasteSubnet} from '../src/subnets.js';
const root=fileURLToPath(new URL('../../../build/stored-node-tests/',import.meta.url));
const setup=async()=>{await fs.mkdir(root,{recursive:true});const directory=await fs.mkdtemp(path.join(root,'run-'));const catalog={nodes:editorNodes(),modules:{},tools:[]};let purged=0;const library=editorLibrary(directory,{catalog:async()=>catalog,inspect:async()=>({canDelete:true}),purge:async()=>purged++});return {directory,catalog,library,mutate:p=>library('editor.library.update',p),purged:()=>purged};};
const configured=()=>{
 const node=editorNode('agent','configured','带数据的节点');node.description='保存全部单节点配置';node.divergence=7;
 node.parameters={file_path:'data/memory.md',metadata:{age:25,inventory:['面包'],location:'广场'}};
 node.agent={model:'test',instructions:'当地行动'};node.execution={adapter:'test',parameters:{temperature:0.2}};node.inputs={pending:[{kind:'task',message:'等待处理'}]};
 node.modules={'example.local':{config:{note_path:'data/module.md',target:'configured'},state:{count:12,nested:{items:['保留状态']}},access:{strength:2,channels:['info','tools']}}};
 node.offered_tools=[{ref:'harness:Read',channels:['tools','private']}];node.toolboxes=['local'];node.expose=['local'];
 node.connections.interfaces=[{target_node_id:'configured',metadata:{channels:['self']}},{target_node_id:'outside',metadata:{channels:['tools']}}];
 return {network:{nodes:[node,editorNode('node','outside')]},files:{'data/memory.md':'节点记忆正文','data/module.md':'模块附带数据','unrelated.md':'不属于本节点'}};
};
const saveBook=async(mutate,id,snapshot,mode='external')=>{const book={id,name:'配置节点',category:'default',createdAt:1,mode,snapshot};await mutate({action:'bookmark.patch',changes:[{id,value:book}]});return book;};
test('saved single nodes preserve complete local data on disk and each placement owns fresh IDs and files',async()=>{
 const {directory,library,mutate}=await setup(),source=configured(),schemas={'example.local':{schema:{properties:{target:{format:'node-id'}}}}};
 for(const mode of ['internal','external']){
  const snapshot=copySubnet(source,['configured'],mode,{configured:{x:100,y:200}}),book=await saveBook(mutate,mode,snapshot,mode);
  const value=await mutate({action:'node.save',bookId:book.id}),saved=value.nodeTemplates.find(n=>n.originBookmark===book.id);
  assert.equal(saved.storageKind,'node');assert.equal(value.assets.node.items[saved.id].folder,'stored-nodes');assert.equal(path.dirname(saved.file),path.join(directory,'node_presets','nodes'));
  const raw=JSON.parse(await fs.readFile(saved.file,'utf8'));assert.deepEqual(raw.network.nodes,snapshot.nodes);assert.deepEqual(raw.files,snapshot.files);assert.deepEqual(saved.snapshot,snapshot);assert.equal(saved.description,source.network.nodes[0].description);
  const first=pasteSubnet(source,saved,{x:0,y:0},schemas),second=pasteSubnet(first.document,saved,{x:20,y:40},schemas),a=first.document.network.nodes.at(-1),b=second.document.network.nodes.at(-1);
  assert.notEqual(a.node_id,b.node_id);assert.notEqual(a.node_id,'configured');assert.equal(a.name,source.network.nodes[0].name);
  assert.deepEqual(a.modules['example.local'].state,source.network.nodes[0].modules['example.local'].state);assert.equal(a.modules['example.local'].config.target,a.node_id);
  for(const key of ['offered_tools','toolboxes','expose','agent','execution','inputs'])assert.deepEqual(a[key],source.network.nodes[0][key]);
  assert.deepEqual(a.parameters.metadata,source.network.nodes[0].parameters.metadata);assert.equal(first.document.files[a.parameters.file_path],'节点记忆正文');assert.equal(first.document.files[a.modules['example.local'].config.note_path],'模块附带数据');
  assert.notEqual(a.parameters.file_path,b.parameters.file_path);assert.deepEqual(a.connections.interfaces.map(e=>e.target_node_id),mode==='internal'?[a.node_id]:[a.node_id,'outside']);
  const withoutOutside={network:{nodes:[source.network.nodes[0]]},files:{}};assert.equal(pasteSubnet(withoutOutside,saved,{x:0,y:0},schemas).document.network.nodes.at(-1).connections.interfaces.length,1);
 }
 const before=await library('editor.library'),metadata=JSON.parse(await fs.readFile(path.join(directory,'editor-library.json'),'utf8'));assert.equal(metadata.nodeTemplates,undefined);assert.equal(metadata.nodeErrors,undefined);
 await fs.unlink(path.join(directory,'editor-library.json'));const rescanned=await library('editor.library');assert.deepEqual(rescanned.nodeTemplates,before.nodeTemplates);assert.deepEqual(rescanned.presets,[]);assert.equal(rescanned.assets.node.items.node.folder,'official-nodes');
});
test('node save uses the current virtual folder, protects official resources, and never changes use history',async()=>{
 const {library,mutate}=await setup(),book=await saveBook(mutate,'book',copySubnet(configured(),['configured'],'external'));
 await mutate({action:'history.push',entries:[{kind:'node',id:'configured',label:'带数据的节点',snapshot:book.snapshot}]});const history=(await library('editor.library')).history;
 await mutate({action:'asset.folder.create',kind:'node',id:'custom',name:'居民',parent:'stored-nodes'});
 let value=await mutate({action:'node.save',bookId:book.id,folder:'custom'}),first=value.nodeTemplates[0];assert.equal(value.assets.node.items[first.id].folder,'custom');
 const changed={...book,snapshot:structuredClone(book.snapshot)};changed.snapshot.nodes[0].modules['example.local'].state.count=99;
 await mutate({action:'bookmark.patch',changes:[{id:book.id,expected:book,value:changed}]});value=await mutate({action:'node.save',bookId:book.id,folder:'custom'});assert.equal(value.nodeTemplates.length,1);assert.equal(value.nodeTemplates[0].id,first.id);assert.equal(value.nodeTemplates[0].snapshot.nodes[0].modules['example.local'].state.count,99);
 value=await mutate({action:'node.save',bookId:book.id,folder:'official-nodes'});assert.equal(value.nodeTemplates.length,2);assert.equal(value.assets.node.items[value.nodeTemplates.find(n=>n.id!==first.id).id].folder,'stored-nodes');
 await assert.rejects(mutate({action:'asset.move',kind:'node',entries:[{type:'item',id:first.id}],target:'official-nodes'}),/官方节点目录/);
 await assert.rejects(mutate({action:'asset.move',kind:'node',entries:[{type:'item',id:'node'}],target:'custom'}),/官方节点保留/);
 await assert.rejects(mutate({action:'asset.folder.delete',kind:'node',id:'custom'}),/仍有资源/);
 await assert.rejects(mutate({action:'asset.folder.delete',kind:'node',id:'official-nodes'}),/系统分类/);
 await assert.rejects(mutate({action:'asset.folder.create',kind:'node',id:'bad',name:'错放',parent:'official-nodes'}),/自定义节点目录/);
 assert.deepEqual((await library('editor.library')).history,history);
});
test('custom node archive, restore and confirmed purge keep independent bookmarks/history and protect shared dependencies',async()=>{
 const {library,mutate,purged}=await setup(),book=await saveBook(mutate,'book',copySubnet(configured(),['configured'],'external'));
 const saved=(await mutate({action:'node.save',bookId:book.id})).nodeTemplates[0];await mutate({action:'history.push',entries:[{kind:'node',id:saved.id,label:saved.name,snapshot:saved.snapshot}]});
 await mutate({action:'asset.archive',kind:'node',entries:[{id:saved.id}]});assert.ok(await fs.stat(saved.file));assert.equal((await library('editor.library')).assets.node.items[saved.id].resource.storageKind,'node');
 await mutate({action:'asset.restore',kind:'node',entries:[{id:saved.id}]});assert.equal((await library('editor.library')).assets.node.items[saved.id].folder,'stored-nodes');
 await mutate({action:'asset.archive',kind:'node',entries:[{id:saved.id},{id:'node'}]});assert.equal((await library('editor.resource.inspect',{kind:'node',id:'node'})).canDelete,false);
 await assert.rejects(mutate({action:'asset.purge',kind:'node',id:'node',confirm:'node'}),/官方节点/);
 await assert.rejects(mutate({action:'asset.purge',kind:'node',id:saved.id,confirm:'wrong'}),/确认/);
 // 删除书签后，磁盘节点预设仍保护它携带的模块和工具实现。
 await mutate({action:'bookmark.patch',changes:[{id:book.id,expected:book,value:null}]});
 for(const [kind,id] of [['module','example.local'],['tool','harness:Read']])assert.equal((await library('editor.resource.inspect',{kind,id})).canDelete,false);
 const value=await mutate({action:'asset.purge',kind:'node',id:saved.id,confirm:saved.id});assert.equal(value.nodeTemplates.length,0);assert.deepEqual(value.history[0].snapshot,saved.snapshot);assert.equal(purged(),0);
 await assert.rejects(fs.stat(saved.file),{code:'ENOENT'});await assert.rejects(fs.stat(saved.metadataFile),{code:'ENOENT'});assert.equal((await library('editor.resource.inspect',{kind:'module',id:'example.local'})).canDelete,true);
 assert.equal(pasteSubnet({network:{nodes:[]},files:{}},value.history[0],{x:0,y:0}).document.network.nodes[0].modules['example.local'].state.count,12);
});
test('node files accept exactly one node; a full network containing only root remains a network preset',async()=>{
 const {directory,library,mutate}=await setup(),store=storedNodes(directory),document={network:{version:8,nodes:[]},files:{}};
 await assert.rejects(store.save({storageKind:'node',document,editor:{}}),/无效/);document.network.nodes=editorNodes().slice(0,2).map(n=>n.snapshot.nodes[0]);await assert.rejects(store.save({storageKind:'node',document,editor:{}}),/无效/);
 document.network.nodes=[editorNode('node','root')];const result=await mutate({action:'network.save',name:'只有根的完整网络',document});assert.equal(result.presets.length,1);assert.equal(result.nodeTemplates.length,0);assert.equal(result.presets[0].storageKind,'network');
 const book=await saveBook(mutate,'single',{nodes:document.network.nodes,files:{},positions:{}});await assert.rejects(mutate({action:'node.save',bookId:book.id,folder:'gone'}),/不存在/);
 assert.deepEqual((await library('editor.library')).nodeErrors,[]);
});
