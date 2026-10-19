import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {editorLibrary} from '../../../adapters/harness/framework/editor-library.js';
import {normalizeHistory} from '../../../adapters/harness/framework/editor-history.js';
import {editorNodes} from '../../../adapters/harness/framework/editor-nodes.js';
import {copySubnet,pasteSubnet} from '../src/subnets.js';
const root=new URL('../../../build/editor-library-tests/',import.meta.url);
const entry=snapshot=>({kind:'bookmark',id:crypto.randomUUID(),label:'配置',mode:'external',snapshot});
test('configuration key ignores allocated IDs, placement, cursor, runtime state and copied document namespace',()=>{
 const snapshot=editorNodes().find(n=>n.id==='agent').snapshot,document={network:{nodes:structuredClone(snapshot.nodes)},files:snapshot.files};
 document.network.nodes[0].modules.x={config:{amount:2},state:{count:30},access:{strength:2,channels:['data']}};
 const original=entry(copySubnet(document,[document.network.nodes[0].node_id],'external'));
 const result=pasteSubnet(document,original,{x:500,y:900}),copied=entry(copySubnet(result.document,result.nodes,'external',result.layout));
 copied.snapshot.nodes[0].context_cursor={offset:80};copied.snapshot.nodes[0].modules.x.state.count=400;
 assert.equal(normalizeHistory(original).id,normalizeHistory(copied).id);
 copied.snapshot.nodes[0].modules.x.config.amount=3;assert.notEqual(normalizeHistory(original).id,normalizeHistory(copied).id);
});
test('network history uses relative internal references while preserving the identity of B external destinations',()=>{
 const snapshot=structuredClone(editorNodes()[0].snapshot),second=structuredClone(snapshot.nodes[0]);second.node_id='second';snapshot.nodes.push(second);
 snapshot.nodes[0].connections.interfaces=[{target_node_id:'second',metadata:{channels:['data']}},{target_node_id:'outside',metadata:{channels:['data']}}];
 const original=entry(snapshot),document={network:{nodes:structuredClone(snapshot.nodes)},files:{}};document.network.nodes.push({...structuredClone(second),node_id:'outside'});
 const placed=pasteSubnet(document,original,{x:0,y:0}),copied=entry(copySubnet(placed.document,placed.nodes,'external'));
 assert.equal(normalizeHistory(original).id,normalizeHistory(copied).id);copied.snapshot.nodes[0].connections.interfaces[1].target_node_id='another-outside';assert.notEqual(normalizeHistory(original).id,normalizeHistory(copied).id);
});
test('history merges configuration and uses MRU order: 1, 2, 1 becomes 1, 2 and survives deletion and restart',async()=>{
 await fs.mkdir(root,{recursive:true});const folder=await fs.mkdtemp(path.join(fileURLToPath(root),'mru-'));
 const library=editorLibrary(folder),one=entry(editorNodes()[0].snapshot),two=structuredClone(one);two.id='second';two.snapshot.nodes[0].name='另一配置';
 const push=entries=>library('editor.library.update',{action:'history.push',entries});
 await push([one]);await push([two]);const reused=structuredClone(one);reused.id='new-instance';reused.snapshot.nodes[0].node_id='different-instance';await push([reused]);
 const saved=await library('editor.library');assert.equal(saved.history.length,2);assert.equal(saved.history[0].snapshot.nodes[0].name,'普通节点');
 assert.equal(saved.history[1].snapshot.nodes[0].name,'另一配置');assert.deepEqual((await editorLibrary(folder)('editor.library')).history,saved.history);
});
test('network preset stores raw A/B snapshot and remains independent of bookmark removal; origin folder is applied once',async()=>{
 await fs.mkdir(root,{recursive:true});const folder=await fs.mkdtemp(path.join(fileURLToPath(root),'presets-'));
 const catalog={nodes:editorNodes(),modules:{},tools:[]},library=editorLibrary(folder,{catalog:async()=>catalog}),mutate=p=>library('editor.library.update',p);
 await mutate({action:'asset.folder.create',kind:'preset',id:'dest',name:'常用'});await mutate({action:'asset.folder.create',kind:'module',id:'maker',name:'新模块'});
 const snapshot=structuredClone(editorNodes()[0].snapshot),second=structuredClone(snapshot.nodes[0]);second.node_id='second';snapshot.nodes.push(second);snapshot.nodes[0].connections.interfaces=[{target_node_id:'second',metadata:{channels:['a']}},{target_node_id:'outside',metadata:{channels:['b']}}];
 const book={id:'book',name:'网络',mode:'external',snapshot,createdAt:1,category:'default'};await mutate({action:'bookmark.patch',changes:[{id:'book',value:book}]});
 await mutate({action:'preset.save',bookId:'book',folder:'dest'});await mutate({action:'bookmark.patch',changes:[{id:'book',expected:book,value:null}]});let saved=await library('editor.library');
 assert.deepEqual(saved.presets[0].snapshot,snapshot);assert.equal(saved.presets[0].mode,'external');assert.equal(saved.assets.preset.items[saved.presets[0].id].folder,'dest');assert.deepEqual(saved.history,[]);
 catalog.modules.new={label:'新模块',display_folder:'maker'};saved=await library('editor.library');assert.equal(saved.assets.module.items.new.folder,'maker');
 await mutate({action:'asset.move',kind:'module',entries:[{type:'item',id:'new'}],target:null});assert.equal((await library('editor.library')).assets.module.items.new.folder,null);
 catalog.modules.fallback={label:'目录被删',display_folder:'missing'};assert.equal((await library('editor.library')).assets.module.items.fallback.folder,null);
});

test('binary databases and knowledge directories deduplicate by payload rather than copied storage paths',()=>{
 const node=structuredClone(editorNodes()[0].snapshot.nodes[0]);node.type='knowledge_collection';node.parameters={directory:'data/wiki'};
 const source={network:{nodes:[node]},files:{'data/wiki/catalog.sqlite3':{encoding:'base64',data:'AAECAw=='},'data/wiki/pages/one.md':'知识正文'}};
 const original=entry(copySubnet(source,[node.node_id],'internal')),placed=pasteSubnet(source,original,{x:0,y:0}),copied=entry(copySubnet(placed.document,placed.nodes,'internal'));
 assert.notEqual(copied.snapshot.nodes[0].parameters.directory,node.parameters.directory);assert.equal(normalizeHistory(original).id,normalizeHistory(copied).id);
 const binary=Object.values(copied.snapshot.files).find(v=>typeof v==='object');binary.data='BAUG';assert.notEqual(normalizeHistory(original).id,normalizeHistory(copied).id);assert.equal(source.files['data/wiki/catalog.sqlite3'].data,'AAECAw==');
});
