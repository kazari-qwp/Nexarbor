import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {copySubnet,pasteSubnet,selectionStep,historyBookmark} from '../src/subnets.js';
import {linkRecord,edgeMetadata} from '../../shared/graph/links.js';
import {moduleTable,setModule} from '../../shared/graph/node-records.js';
import {keyMatches,pointerMatches} from '../src/shortcuts.js';
const edge=target=>linkRecord(target,{channels:['tools'],threshold:1,multiplier:1,attributes:{label:'边参数'}});
const node=id=>({node_id:id,name:id,type:'agent',data:{path:id+'.md',directory:false,save_data:true},execution:{executor:'harness'},links:[],tables:{modules:[]}});
const a=node('a'),b=node('b'),c=node('c');a.links=[edge('b'),edge('c')];b.links=[edge('a')];
const document={network:{nodes:[a,b,c]},files:{'a.md':'a记忆','b.md':'b记忆','c.md':'c记忆','unused.md':'不复制'}};
test('A trims external links; B keeps them; neither changes source or copies unrelated documents',async()=>{
 const internal=copySubnet(document,['a','b'],'internal'),external=copySubnet(document,['a','b'],'external');
 assert.deepEqual(internal.nodes[0].links.map(e=>e.target_id),['b']);assert.equal(external.nodes[0].links.length,2);
 assert.deepEqual(Object.keys(external.files),['a.md','b.md']);assert.equal(Object.hasOwn(internal,'agents'),false);
 const paste=await pasteSubnet(document,{snapshot:external},{x:300,y:400});const copied=paste.document.network.nodes.slice(3);
 assert.notEqual(copied[0].node_id,'a');assert.equal(copied[0].links[0].target_id,copied[1].node_id);assert.equal(copied[0].links[1].target_id,'c');
 assert.notEqual(copied[0].data.path,'a.md');assert.equal(paste.document.files[copied[0].data.path],'a记忆');assert.equal(Object.hasOwn(copied[0],'context_cursor'),false);
});
test('pure edge A has no endpoints, B only retains destination',async()=>{
 const x=copySubnet(document,[],'internal',{},['a|0']),y=copySubnet(document,[],'external',{},['a|0']);
 assert.deepEqual(Object.keys(x.edges[0]),['metadata']);assert.deepEqual(Object.keys(y.edges[0]),['metadata','target']);assert.equal(y.edges[0].target,'b');
 assert.equal(x.edges[0].metadata.attributes.label,'边参数');assert.deepEqual((await pasteSubnet(document,{snapshot:x},{x:0,y:0})).edges,x.edges);
});
test('selection wheel advances one incidence layer at a time',async()=>{
 const nodes=['a','b','c'].map(id=>({id})),edges=[{id:'ab',source:'a',target:'b'},{id:'bc',source:'b',target:'c'}];
 let selected=selectionStep(nodes,edges,{nodes:['a'],edges:[]});assert.deepEqual(selected,{nodes:['a'],edges:['ab']});
 selected=selectionStep(nodes,edges,selected);assert.deepEqual(selected,{nodes:['a','b'],edges:['ab']});
 selected=selectionStep(nodes,edges,selected);assert.deepEqual(selected.edges,['ab','bc']);
 assert.deepEqual(selectionStep(nodes,edges,{nodes:['a'],edges:[]},false),{nodes:[],edges:[]});
});
test('key bindings distinguish modifiers',async()=>{
 assert.equal(keyMatches({key:'z',ctrlKey:true},'Ctrl+Z'),true);assert.equal(keyMatches({key:'z',ctrlKey:true,shiftKey:true},'Ctrl+Z'),false);
 assert.equal(pointerMatches({button:2,altKey:true},{button:2,modifier:'Alt'}),true);
});
test('history drag preserves bookmark mode and drops an edge source while keeping its target',async()=>{
 const entry={kind:'edge',id:'a|0',label:'a → b',source:'a',target:'b',metadata:edgeMetadata(edge('b'))};
 const book=historyBookmark(entry);assert.deepEqual(book.snapshot.edges,[{metadata:entry.metadata,target:'b'}]);
 assert.equal(Object.hasOwn(book.snapshot.edges[0],'source'),false);
 const internal=copySubnet(document,['a','b'],'internal');
 const saved=historyBookmark({kind:'bookmark',id:'removed',label:'旧书签',mode:'internal',snapshot:internal});
 assert.equal(saved.mode,'internal');assert.equal(saved.snapshot.nodes.length,2);
 const live=historyBookmark({kind:'node',id:'a',label:'a',snapshot:copySubnet(document,['a'],'internal')},[],document);
 assert.equal(live.snapshot.nodes[0].links.length,0);
 assert.throws(()=>historyBookmark({kind:'node',id:'missing',label:'不存在'}),/没有可复用/);
});
test('every A/B placement allocates collision-free IDs and remaps all internal links while B retains original external targets',async()=>{
 const schema={reference:{config_schema:{type:'object',properties:{target:{type:'string',format:'node-id'}}},state_schema:{type:'object',properties:{location:{type:'string',format:'node-id'},visitors:{type:'array',items:{type:'string',format:'node-id'}},external:{type:'string',format:'node-id'}}}}};
 const source=structuredClone(document);setModule(source.network.nodes[0],'reference',{config:{target:'b'},state:{location:'b',visitors:['a','b'],external:'c'}});
 for(const mode of ['internal','external']){
  const snapshot=copySubnet(source,['a','b'],mode);let current=source;
  for(let i=0;i<4;i++){
   const result=await pasteSubnet(current,{mode,snapshot},{x:i*100,y:100},schema),[first,second]=result.document.network.nodes.slice(-2);
   assert.equal(first.name,'a');assert.equal(second.name,'b');
   assert.equal(first.links[0].target_id,second.node_id);assert.equal(second.links[0].target_id,first.node_id);
   assert.equal(moduleTable(first).reference.config.target,second.node_id);
   assert.deepEqual(moduleTable(first).reference.state,{location:second.node_id,visitors:[first.node_id,second.node_id],external:'c'});
   assert.deepEqual(first.links.slice(1).map(l=>l.target_id),mode==='external'?['c']:[]);
   assert.equal(new Set(result.document.network.nodes.map(n=>n.node_id)).size,result.document.network.nodes.length);current=result.document;
  }
 }
 const missing=structuredClone(source);missing.network.nodes=missing.network.nodes.filter(n=>n.node_id!=='c');
 const result=await pasteSubnet(missing,{snapshot:copySubnet(source,['a','b'],'external')},{x:0,y:0});assert.equal(result.document.network.nodes.at(-2).links.length,1);
});
test('history owns its node, links and document cache after the source and bookmark are removed',async()=>{
 const entry={kind:'network',id:'cached',label:'缓存',mode:'external',snapshot:copySubnet(document,['a','b'],'external')};
 const book=historyBookmark(entry,[{id:'cached',snapshot:{nodes:[]}}],{network:{nodes:[]},files:{}});const result=await pasteSubnet(document,book,{x:0,y:0});
 assert.equal(result.document.files[result.document.network.nodes.at(-2).data.path],'a记忆');
 assert.equal(result.document.network.nodes.at(-2).links[0].target_id,result.document.network.nodes.at(-1).node_id);
 book.snapshot.nodes[0].name='修改';assert.equal(entry.snapshot.nodes[0].name,'a');
});
test('even a repeated UUID cannot overwrite an existing node or its associated document',async t=>{
 t.mock.method(crypto,'randomUUID',()=> 'fixed-uuid');
 const book={snapshot:copySubnet(document,['a','b'],'external')},first=await pasteSubnet(document,book,{x:0,y:0}),second=await pasteSubnet(first.document,book,{x:0,y:0});
 const [a2,b2]=second.document.network.nodes.slice(-2);assert.notEqual(a2.node_id,first.nodes[0]);assert.notEqual(b2.node_id,first.nodes[1]);
 assert.equal(a2.links[0].target_id,b2.node_id);assert.equal(b2.links[0].target_id,a2.node_id);
 assert.notEqual(a2.data.path,first.document.network.nodes.at(-2).data.path);assert.equal(second.document.files[a2.data.path],'a记忆');
 const long=structuredClone(book);long.snapshot.nodes[0].node_id='a'.repeat(180);assert.ok((await pasteSubnet(document,long,{x:0,y:0})).nodes.every(id=>id.length<=180));
});

test('real record-store node references in configuration, state and receipts follow copied internal nodes',async()=>{
 const spec=JSON.parse(readFileSync(new URL('../../../projects/npc_town/modules/records_store/module.json',import.meta.url),'utf8'));
 const source=structuredClone(document),references=[{key:'home',node_id:'b'},{key:'outside',node_id:'c'}];
 setModule(source.network.nodes[0],'records.store',{config:{initial:{label:'b'},references},state:{values:{label:'b'},references,receipts:[{key:'old-request',fingerprint:'not-authority',values:{label:'b'},references}]},strength:0,channels:['records']});
 for(const mode of ['internal','external']){
  const result=await pasteSubnet(source,{mode,snapshot:copySubnet(source,['a','b'],mode)},{x:0,y:0},{'records.store':{config_schema:spec.config_schema,state_schema:spec.state_schema}});
  const [first,second]=result.document.network.nodes.slice(-2),record=moduleTable(first)['records.store'];
  for(const refs of [record.config.references,record.state.references,record.state.receipts[0].references])assert.deepEqual(refs,[{key:'home',node_id:second.node_id},{key:'outside',node_id:'c'}]);
  assert.equal(record.config.initial.label,'b');assert.equal(record.state.values.label,'b');
 }
});

test('text, binary and directory data are independent, including empty directory templates',async()=>{
 const data=structuredClone(document);data.network.nodes[0].type='sqlite';data.network.nodes[0].data={path:'data/store.sqlite3',directory:false,save_data:true};data.files['data/store.sqlite3']={encoding:'base64',data:'AAECAw=='};
 const saved=copySubnet(data,['a'],'internal'),placed=await pasteSubnet(data,{snapshot:saved},{x:0,y:0}),n=placed.document.network.nodes.at(-1);
 assert.notEqual(n.data.path,'data/store.sqlite3');placed.document.files[n.data.path].data='changed';assert.equal(saved.files['data/store.sqlite3'].data,'AAECAw==');assert.equal(data.files['data/store.sqlite3'].data,'AAECAw==');
 const empty=structuredClone(saved);empty.nodes[0].data={path:'data/empty',directory:true,save_data:true};empty.files={};const one=await pasteSubnet(data,{snapshot:empty},{x:0,y:0}),two=await pasteSubnet(one.document,{snapshot:empty},{x:0,y:0});assert.notEqual(one.document.network.nodes.at(-1).data.path,two.document.network.nodes.at(-1).data.path);
});

test('JSON node values preserve ordinary node_id and file_path fields without copying another nodes document',async()=>{
 const value={file_path:'a.md',node_id:'a',directory:'some/path'},source=structuredClone(document);source.network.nodes[0].type='value';source.network.nodes[0].data={path:'data/value.json',directory:false,save_data:true};source.files['data/value.json']=JSON.stringify(value);
 const saved=copySubnet(source,['a'],'internal');assert.deepEqual(saved.files,{'data/value.json':JSON.stringify(value)});const result=await pasteSubnet(source,{snapshot:saved},{x:0,y:0});assert.deepEqual(JSON.parse(result.document.files[result.document.network.nodes.at(-1).data.path]),value);
});

test('missing backing data and external resource paths fail instead of creating lookalike empty copies',async()=>{
 const source=structuredClone(document);delete source.files['a.md'];assert.throws(()=>copySubnet(source,['a'],'internal'),/数据资源缺失/);await assert.rejects(pasteSubnet(document,{snapshot:{nodes:[a],files:{}}},{x:0,y:0}),/数据资源缺失/);
 source.network.nodes[0].data.path='../external.md';assert.throws(()=>copySubnet(source,['a'],'internal'),/导入网络目录/);
});

test('one selected incoming edge becomes an anonymous entry; every A/B paste binds it to a fresh internal target independent of selection order',async()=>{
 const source=structuredClone(document);source.network.nodes.find(n=>n.node_id==='c').links=[edge('b')];const before=structuredClone(source);
 for(const mode of ['internal','external'])for(const order of [['a','b'],['b','a']]){
  const snapshot=copySubnet(source,order,mode,{},['c|0','a|0']);assert.equal(snapshot.edges.length,1);assert.equal(snapshot.edges[0].target,'b');assert.equal(Object.hasOwn(snapshot.edges[0],'source'),false);
  // A 保存内部接入口，但仍去掉节点自身指向外部的出边。
  assert.equal(snapshot.nodes.find(n=>n.node_id==='a').links.some(e=>e.target_id==='c'),mode==='external');
  const result=await pasteSubnet(source,{snapshot},{x:10,y:20},{},{},{source:'c'}),copied=result.document.network.nodes.slice(source.network.nodes.length),target=copied.find(n=>n.name==='b');
  assert.equal(result.attachedEntry,true);assert.equal(result.document.network.nodes.find(n=>n.node_id==='c').links.at(-1).target_id,target.node_id);assert.notEqual(target.node_id,'b');assert.deepEqual(edgeMetadata(result.document.network.nodes.find(n=>n.node_id==='c').links.at(-1)),edgeMetadata(edge('b')));
  assert.equal(copied.find(n=>n.name==='a').links[0].target_id,target.node_id);
 }
 assert.deepEqual(source,before);
});

test('entry placement depends only on the saved structure: imported/reordered snapshots work, multiple anonymous entries are ignored',async()=>{
 const snapshot={nodes:[structuredClone(b),structuredClone(a)],files:{'a.md':'a','b.md':'b'},positions:{},edges:[{metadata:edgeMetadata(edge('a')),target:'a'}]};
 let pasted=await pasteSubnet(document,{snapshot},{x:0,y:0},{},{},{source:'c'});assert.equal(pasted.attachedEntry,true);assert.equal(pasted.document.network.nodes.find(n=>n.node_id==='c').links[0].target_id,pasted.document.network.nodes.find(n=>n.name==='a'&&n.node_id!=='a').node_id);
 for(const entries of [[],[...snapshot.edges,...snapshot.edges],[{metadata:edgeMetadata(edge('x')),target:'missing'}]]){
  const result=await pasteSubnet(document,{snapshot:{...snapshot,edges:entries}},{x:0,y:0},{},{},{source:'c'});assert.equal(result.nodes.length,2);assert.equal(result.attachedEntry,false);assert.equal(result.document.network.nodes.find(n=>n.node_id==='c').links.length,0);
 }
 assert.equal((await pasteSubnet(document,{snapshot},{x:0,y:0})).attachedEntry,false);
});
