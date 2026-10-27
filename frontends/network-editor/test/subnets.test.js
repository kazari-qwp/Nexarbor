import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {copySubnet,pasteSubnet,selectionStep,historyBookmark} from '../src/subnets.js';
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
test('key bindings distinguish modifiers',()=>{
 assert.equal(keyMatches({key:'z',ctrlKey:true},'Ctrl+Z'),true);assert.equal(keyMatches({key:'z',ctrlKey:true,shiftKey:true},'Ctrl+Z'),false);
 assert.equal(pointerMatches({button:2,altKey:true},{button:2,modifier:'Alt'}),true);
});
test('history drag preserves bookmark mode and drops an edge source while keeping its target',()=>{
 const entry={kind:'edge',id:'a|0',label:'a → b',source:'a',target:'b',metadata:edge('b').metadata};
 const book=historyBookmark(entry);assert.deepEqual(book.snapshot.edges,[{metadata:entry.metadata,target:'b'}]);
 assert.equal(Object.hasOwn(book.snapshot.edges[0],'source'),false);
 const internal=copySubnet(document,['a','b'],'internal');
 const saved=historyBookmark({kind:'bookmark',id:'removed',label:'旧书签',mode:'internal',snapshot:internal});
 assert.equal(saved.mode,'internal');assert.equal(saved.snapshot.nodes.length,2);
 const live=historyBookmark({kind:'node',id:'a',label:'a',snapshot:copySubnet(document,['a'],'internal')},[],document);
 assert.equal(live.snapshot.nodes[0].connections.interfaces.length,0);
 assert.throws(()=>historyBookmark({kind:'node',id:'missing',label:'不存在'}),/没有可复用/);
});
test('every A/B placement allocates collision-free IDs and remaps all internal links while B retains original external targets',()=>{
 const schema={reference:{schema:{type:'object',properties:{target:{type:'string',format:'node-id'}}},state_schema:{type:'object',properties:{location:{type:'string',format:'node-id'},visitors:{type:'array',items:{type:'string',format:'node-id'}},external:{type:'string',format:'node-id'}}}}};
 const source=structuredClone(document);source.network.nodes[0].modules.reference={config:{target:'b'},state:{location:'b',visitors:['a','b'],external:'c'}};
 for(const mode of ['internal','external']){
  const snapshot=copySubnet(source,['a','b'],mode);let current=source;
  for(let i=0;i<4;i++){
   const result=pasteSubnet(current,{mode,snapshot},{x:i*100,y:100},schema),[first,second]=result.document.network.nodes.slice(-2);
   assert.equal(first.name,'a');assert.equal(second.name,'b');
   assert.equal(first.connections.interfaces[0].target_node_id,second.node_id);assert.equal(second.connections.interfaces[0].target_node_id,first.node_id);
   assert.equal(first.modules.reference.config.target,second.node_id);
   assert.deepEqual(first.modules.reference.state,{location:second.node_id,visitors:[first.node_id,second.node_id],external:'c'});
   assert.deepEqual(first.connections.interfaces.slice(1).map(l=>l.target_node_id),mode==='external'?['c']:[]);
   assert.equal(new Set(result.document.network.nodes.map(n=>n.node_id)).size,result.document.network.nodes.length);current=result.document;
  }
 }
 const missing=structuredClone(source);missing.network.nodes=missing.network.nodes.filter(n=>n.node_id!=='c');
 const result=pasteSubnet(missing,{snapshot:copySubnet(source,['a','b'],'external')},{x:0,y:0});assert.equal(result.document.network.nodes.at(-2).connections.interfaces.length,1);
});
test('history owns its node, links and document cache after the source and bookmark are removed',()=>{
 const entry={kind:'network',id:'cached',label:'缓存',mode:'external',snapshot:copySubnet(document,['a','b'],'external')};
 const book=historyBookmark(entry,[{id:'cached',snapshot:{nodes:[]}}],{network:{nodes:[]},files:{}});const result=pasteSubnet(document,book,{x:0,y:0});
 assert.equal(result.document.files[result.document.network.nodes.at(-2).parameters.file_path],'a记忆');
 assert.equal(result.document.network.nodes.at(-2).connections.interfaces[0].target_node_id,result.document.network.nodes.at(-1).node_id);
 book.snapshot.nodes[0].name='修改';assert.equal(entry.snapshot.nodes[0].name,'a');
});
test('even a repeated UUID cannot overwrite an existing node or its associated document',t=>{
 t.mock.method(crypto,'randomUUID',()=> 'fixed-uuid');
 const book={snapshot:copySubnet(document,['a','b'],'external')},first=pasteSubnet(document,book,{x:0,y:0}),second=pasteSubnet(first.document,book,{x:0,y:0});
 const [a2,b2]=second.document.network.nodes.slice(-2);assert.notEqual(a2.node_id,first.nodes[0]);assert.notEqual(b2.node_id,first.nodes[1]);
 assert.equal(a2.connections.interfaces[0].target_node_id,b2.node_id);assert.equal(b2.connections.interfaces[0].target_node_id,a2.node_id);
 assert.notEqual(a2.parameters.file_path,first.document.network.nodes.at(-2).parameters.file_path);assert.equal(second.document.files[a2.parameters.file_path],'a记忆');
 const long=structuredClone(book);long.snapshot.nodes[0].node_id='a'.repeat(180);assert.ok(pasteSubnet(document,long,{x:0,y:0}).nodes.every(id=>id.length<=180));
});

test('real record-store node references in configuration, state and receipts follow copied internal nodes',()=>{
 const spec=JSON.parse(readFileSync(new URL('../../../extensions/composable/capabilities/records_store/module.json',import.meta.url),'utf8'));
 const source=structuredClone(document),references=[{key:'home',node_id:'b'},{key:'outside',node_id:'c'}];
 source.network.nodes[0].modules['records.store']={config:{initial:{label:'b'},references},state:{values:{label:'b'},references,receipts:[{key:'old-request',fingerprint:'not-authority',values:{label:'b'},references}]},access:{strength:0,channels:['records']}};
 for(const mode of ['internal','external']){
  const result=pasteSubnet(source,{mode,snapshot:copySubnet(source,['a','b'],mode)},{x:0,y:0},{'records.store':{schema:spec.config_schema,state_schema:spec.state_schema}});
  const [first,second]=result.document.network.nodes.slice(-2),record=first.modules['records.store'];
  for(const refs of [record.config.references,record.state.references,record.state.receipts[0].references])assert.deepEqual(refs,[{key:'home',node_id:second.node_id},{key:'outside',node_id:'c'}]);
  assert.equal(record.config.initial.label,'b');assert.equal(record.state.values.label,'b');
 }
});

test('text, binary and directory data are independent, including empty directory templates',()=>{
 const data=structuredClone(document);data.network.nodes[0].type='sqlite';data.network.nodes[0].parameters={db_path:'data/store.sqlite3'};data.files['data/store.sqlite3']={encoding:'base64',data:'AAECAw=='};
 const saved=copySubnet(data,['a'],'internal'),placed=pasteSubnet(data,{snapshot:saved},{x:0,y:0}),n=placed.document.network.nodes.at(-1);
 assert.notEqual(n.parameters.db_path,'data/store.sqlite3');placed.document.files[n.parameters.db_path].data='changed';assert.equal(saved.files['data/store.sqlite3'].data,'AAECAw==');assert.equal(data.files['data/store.sqlite3'].data,'AAECAw==');
 const empty=structuredClone(saved);empty.nodes[0].parameters={directory:'data/empty'};empty.files={};const one=pasteSubnet(data,{snapshot:empty},{x:0,y:0}),two=pasteSubnet(one.document,{snapshot:empty},{x:0,y:0});assert.notEqual(one.document.network.nodes.at(-1).parameters.directory,two.document.network.nodes.at(-1).parameters.directory);
});

test('JSON node values preserve ordinary node_id and file_path fields without copying another nodes document',()=>{
 const value={file_path:'a.md',node_id:'a',directory:'some/path'},source=structuredClone(document);source.network.nodes[0].type='value';source.network.nodes[0].parameters={value};
 const saved=copySubnet(source,['a'],'internal');assert.deepEqual(saved.files,{});const result=pasteSubnet(source,{snapshot:saved},{x:0,y:0});assert.deepEqual(result.document.network.nodes.at(-1).parameters.value,value);
});

test('missing backing data and external resource paths fail instead of creating lookalike empty copies',()=>{
 const source=structuredClone(document);delete source.files['a.md'];assert.throws(()=>copySubnet(source,['a'],'internal'),/数据资源缺失/);assert.throws(()=>pasteSubnet(document,{snapshot:{nodes:[a],files:{}}},{x:0,y:0}),/数据资源缺失/);
 source.network.nodes[0].parameters.file_path='../external.md';assert.throws(()=>copySubnet(source,['a'],'internal'),/导入网络目录/);
});

test('one selected incoming edge becomes an anonymous entry; every A/B paste binds it to a fresh internal target independent of selection order',()=>{
 const source=structuredClone(document);source.network.nodes.find(n=>n.node_id==='c').connections.interfaces=[edge('b')];const before=structuredClone(source);
 for(const mode of ['internal','external'])for(const order of [['a','b'],['b','a']]){
  const snapshot=copySubnet(source,order,mode,{},['c|0','a|0']);assert.equal(snapshot.edges.length,1);assert.equal(snapshot.edges[0].target,'b');assert.equal(Object.hasOwn(snapshot.edges[0],'source'),false);
  // A 保存内部接入口，但仍去掉节点自身指向外部的出边。
  assert.equal(snapshot.nodes.find(n=>n.node_id==='a').connections.interfaces.some(e=>e.target_node_id==='c'),mode==='external');
  const result=pasteSubnet(source,{snapshot},{x:10,y:20},{},{},{source:'c'}),copied=result.document.network.nodes.slice(source.network.nodes.length),target=copied.find(n=>n.name==='b');
  assert.equal(result.attachedEntry,true);assert.equal(result.document.network.nodes.find(n=>n.node_id==='c').connections.interfaces.at(-1).target_node_id,target.node_id);assert.notEqual(target.node_id,'b');assert.deepEqual(result.document.network.nodes.find(n=>n.node_id==='c').connections.interfaces.at(-1).metadata,edge('b').metadata);
  assert.equal(copied.find(n=>n.name==='a').connections.interfaces[0].target_node_id,target.node_id);
 }
 assert.deepEqual(source,before);
});

test('entry placement depends only on the saved structure: imported/reordered snapshots work, multiple anonymous entries are ignored',()=>{
 const snapshot={nodes:[structuredClone(b),structuredClone(a)],files:{'a.md':'a','b.md':'b'},positions:{},edges:[{metadata:edge('a').metadata,target:'a'}]};
 let pasted=pasteSubnet(document,{snapshot},{x:0,y:0},{},{},{source:'c'});assert.equal(pasted.attachedEntry,true);assert.equal(pasted.document.network.nodes.find(n=>n.node_id==='c').connections.interfaces[0].target_node_id,pasted.document.network.nodes.find(n=>n.name==='a'&&n.node_id!=='a').node_id);
 for(const entries of [[],[...snapshot.edges,...snapshot.edges],[{metadata:edge('x').metadata,target:'missing'}]]){
  const result=pasteSubnet(document,{snapshot:{...snapshot,edges:entries}},{x:0,y:0},{},{},{source:'c'});assert.equal(result.nodes.length,2);assert.equal(result.attachedEntry,false);assert.equal(result.document.network.nodes.find(n=>n.node_id==='c').connections.interfaces.length,0);
 }
 assert.equal(pasteSubnet(document,{snapshot},{x:0,y:0}).attachedEntry,false);
});
