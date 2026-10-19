import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {editorLibrary} from '../../../adapters/harness/framework/editor-library.js';
import {editorNodes} from '../../../adapters/harness/framework/editor-nodes.js';
const root=fileURLToPath(new URL('../../../build/stored-network-tests/',import.meta.url));
test('real network files share the product format; the current virtual folder chooses fragment or complete-network storage',async()=>{
 await fs.mkdir(root,{recursive:true});const directory=await fs.mkdtemp(path.join(root,'run-')),library=editorLibrary(directory),mutate=p=>library('editor.library.update',p);
 const snapshot=structuredClone(editorNodes()[0].snapshot),other=structuredClone(snapshot.nodes[0]);other.node_id='other';snapshot.nodes.push(other);
 snapshot.nodes[0].connections.interfaces=[{target_node_id:'other',metadata:{channels:['data']}},{target_node_id:'outside',metadata:{channels:['data']}}];
 const book={id:'book',name:'网络书签',mode:'external',snapshot,category:'default',createdAt:1};await mutate({action:'bookmark.patch',changes:[{id:book.id,value:book}]});
 await mutate({action:'asset.folder.create',kind:'preset',id:'parts',name:'地点'});await mutate({action:'asset.folder.create',kind:'preset',id:'finished-child',name:'子目录',parent:'stored-networks'});
 for(const [folder,storageKind] of [['parts','fragment'],['stored-networks','network'],['finished-child','network']]){
  const result=await mutate({action:'preset.save',bookId:book.id,folder}),preset=result.presets.find(p=>result.assets.preset.items[p.id].folder===folder);
  assert.equal(preset.storageKind,storageKind);assert.equal(path.dirname(preset.file),path.join(directory,'network_presets',storageKind==='fragment'?'fragments':'networks'));
  const raw=JSON.parse(await fs.readFile(preset.file,'utf8'));assert.equal(raw.network.version,8);assert.deepEqual(raw.network.nodes,snapshot.nodes);assert.deepEqual(raw.files,snapshot.files);assert.equal(raw.snapshot,undefined);assert.equal(raw.mode,undefined);
  assert.deepEqual(preset.snapshot,snapshot);assert.equal(preset.mode,'external');const savedEditor=JSON.parse(await fs.readFile(preset.metadataFile,'utf8'));assert.equal(savedEditor.display_folder,folder);
 }
 const document={network:{version:8,nodes:snapshot.nodes.map((n,i)=>({...n,node_id:i?'other':'root'})),signals:{},delegations:[]},files:{'notes.md':'成品文档'}};
 const result=await mutate({action:'network.save',name:'完整网络',document,layout:{root:{x:20,y:30}}}),full=result.presets.find(p=>p.name==='完整网络');
 assert.deepEqual(JSON.parse(await fs.readFile(full.file,'utf8')),document);assert.equal(result.assets.preset.items[full.id].folder,'stored-networks');
 const metadata=JSON.parse(await fs.readFile(path.join(directory,'editor-library.json'),'utf8'));assert.equal(metadata.presets,undefined);
 // 删除编辑器目录资料后，磁盘文件仍能重新扫描；完整文件默认进入已存储网络。
 await fs.unlink(path.join(directory,'editor-library.json'));const rescanned=await editorLibrary(directory)('editor.library');assert.equal(rescanned.presets.length,4);assert.equal(rescanned.assets.preset.items[full.id].folder,'stored-networks');assert.deepEqual(rescanned.presets.find(p=>p.id===full.id).snapshot.files,document.files);
});
test('preset archive keeps real files, confirmed deletion removes only the selected pair and leaves independent history',async()=>{
 const directory=await fs.mkdtemp(path.join(root,'delete-')),library=editorLibrary(directory),mutate=p=>library('editor.library.update',p),nodes=editorNodes().slice(0,2).map(p=>p.snapshot.nodes[0]),snapshot={nodes,files:{},positions:{}};
 const book={id:'source',name:'原件',mode:'internal',snapshot,category:'default',createdAt:1};await mutate({action:'bookmark.patch',changes:[{id:book.id,value:book}]});
 let value=await mutate({action:'preset.save',bookId:book.id,folder:null}),preset=value.presets[0];await mutate({action:'history.push',entries:[{kind:'network',id:preset.id,label:preset.name,mode:preset.mode,snapshot:preset.snapshot}]});
 await mutate({action:'asset.archive',kind:'preset',entries:[{id:preset.id}]});assert.ok(await fs.stat(preset.file));
 await assert.rejects(mutate({action:'asset.purge',kind:'preset',id:preset.id,confirm:'wrong'}),/确认/);
 const info=await library('editor.resource.inspect',{kind:'preset',id:preset.id});assert.deepEqual(info.files,[preset.file,preset.metadataFile]);
 value=await mutate({action:'asset.purge',kind:'preset',id:preset.id,confirm:preset.id});assert.equal(value.presets.length,0);assert.equal(value.bookmarks.length,1);assert.deepEqual(value.history[0].snapshot,snapshot);
 await assert.rejects(fs.stat(preset.file),{code:'ENOENT'});await assert.rejects(fs.stat(preset.metadataFile),{code:'ENOENT'});
});

test('entry connectors persist through bookmark, network preset, node preset and history without storing their old source',async()=>{
 await fs.mkdir(root,{recursive:true});const directory=await fs.mkdtemp(path.join(root,'entry-')),library=editorLibrary(directory),mutate=p=>library('editor.library.update',p),snapshot=structuredClone(editorNodes()[0].snapshot),target=snapshot.nodes[0].node_id;const extra=structuredClone(snapshot.nodes[0]);extra.node_id='second';snapshot.nodes.push(extra);
 snapshot.edges=[{target,metadata:{channels:['tick'],threshold:2,multiplier:3,attributes:{label:'接入口'}}}];const book={id:'entry',name:'可连接节点',mode:'internal',snapshot,category:'default',createdAt:1};await mutate({action:'bookmark.patch',changes:[{id:book.id,value:book}]});
 let value=await mutate({action:'preset.save',bookId:book.id}),saved=value.presets[0];assert.deepEqual(saved.snapshot.edges,snapshot.edges);assert.equal(JSON.parse(await fs.readFile(saved.file,'utf8')).network.version,8);assert.equal(JSON.parse(await fs.readFile(saved.file,'utf8')).edges,undefined);
 const single={...book,id:'single-entry',snapshot:{...snapshot,nodes:snapshot.nodes.slice(0,1)}};await mutate({action:'bookmark.patch',changes:[{id:single.id,value:single}]});value=await mutate({action:'node.save',bookId:single.id});assert.deepEqual(value.nodeTemplates[0].snapshot.edges,snapshot.edges);
 await mutate({action:'history.push',entries:[{kind:'node',id:'entry-use',label:book.name,snapshot}]});const kept=await editorLibrary(directory)('editor.library');assert.deepEqual(kept.history[0].snapshot.edges,snapshot.edges);assert.deepEqual(kept.presets[0].snapshot.edges,snapshot.edges);assert.deepEqual(kept.nodeTemplates[0].snapshot.edges,snapshot.edges);
});
