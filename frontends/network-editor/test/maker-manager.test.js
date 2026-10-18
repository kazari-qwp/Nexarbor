import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';import {makerTools} from '../../../adapters/harness/studio/makers/tools.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),checksum=text=>createHash('sha256').update(text).digest('hex');
async function fixture(t,factory){const directory=await fs.mkdtemp(path.join(root,'build/makers-offline-')),host=await startStudio({directory,makerRunnerFactory:factory});t.after(()=>host.close());return {host,directory,api:async(operation,params={})=>{const r=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})});const v=await r.json();if(v.error)throw Error(v.error);return v.value;}};}
const finished=async(api,id)=>{for(let n=0;n<200;n++){const v=await api('studio.job',{job:id});if(v.status!=='running')return v;await new Promise(r=>setTimeout(r,25));}throw Error('validation timeout');};
test('maker files are scoped; tutorials are readonly and tool releases keep the tool entry folder',async t=>{
 const {api}=await fixture(t);await api('editor.library.update',{action:'asset.folder.create',kind:'tool',id:'mine',name:'我的工具'});
 const w=await api('studio.create',{kind:'tool',sample:'blank',display_folder:'mine'});assert.equal(w.kind,'tool');assert.ok(w.references['lessons/03-locks.md']);assert.ok(!w.files['lessons/03-locks.md']);
 for(const file of ['../outside.py','lessons/03-locks.md','MODULE_GUIDE.md'])await assert.rejects(api('studio.maker_tool',{id:w.id,tool:'write_file',arguments:{path:file,content:'修改'}}));
 await assert.rejects(api('studio.maker_tool',{id:w.id,tool:'read_file',arguments:{path:'../../../../README.md'}}));
 const check=await api('studio.validate',{id:w.id});assert.equal((await finished(api,check.id)).status,'passed');const release=await api('studio.publish',{id:w.id});assert.equal(release.origin_kind,'tool');
 const library=await api('editor.library');assert.equal(library.assets.tool.items['module:example.counter/increment'].folder,'mine');assert.equal(library.assets.module?.items['example.counter']?.folder??null,null);
});
test('network work copies publish real files into the entry directory and validate dependencies',async t=>{
 const {api,directory}=await fixture(t);await api('editor.library.update',{action:'asset.folder.create',kind:'preset',id:'maps',name:'地图',parent:'stored-networks'});
 const work=await api('studio.create',{kind:'network',sample:'blank',display_folder:'maps'});assert.deepEqual(Object.keys(work.files).sort(),['README.md','network.json']);
 let check=await api('studio.validate',{id:work.id});assert.equal((await finished(api,check.id)).status,'passed');const release=await api('studio.publish',{id:work.id,name:'入口预设'});assert.equal(release.storageKind,'network');assert.equal(release.display_folder,'maps');assert.ok(release.file.startsWith(path.join(directory,'network_presets','networks')));assert.equal(JSON.parse(await fs.readFile(release.file,'utf8')).network.version,8);
 const doc=JSON.parse(work.files['network.json']);assert.equal((await api('validate',{document:doc})).valid,true);doc.network.nodes[0].modules.missing={config:{},state:{},access:{strength:0,channels:[]}};assert.equal((await api('validate',{document:doc})).valid,false);await api('studio.save',{id:work.id,file:'network.json',content:JSON.stringify(doc),expected:checksum(work.files['network.json'])});check=await api('studio.validate',{id:work.id});assert.equal((await finished(api,check.id)).status,'failed');await assert.rejects(api('studio.publish',{id:work.id}));
});
test('delegation switch is enforced by host capabilities; same-prefix history can fork',async t=>{
 let callback,serial=0;const created=[],waiting=new Map();const runner={start:async()=>({ready:true}),close:async()=>{},request:async(method,p)=>{if(method==='create'){created.push(p);return {session_id:'offline-'+(++serial),seed_cursor:{seed:true}};}if(method==='run')return new Promise(resolve=>waiting.set(p.session_id,resolve));if(method==='read')return {messages:[]};if(method==='cancel'){waiting.get(p.session_id)?.({status:'cancelled',messages:[],events:[]});return {};}}};
 const {api}=await fixture(t,async(_p,cb)=>{callback=cb;return runner;});await api('studio.agent.connect');
 const work=await api('studio.create',{kind:'network',dependencies:[]}),off=await api('studio.agent.start',{id:work.id,requirement:'做固定网络',auto_publish:false});assert.ok(!created[0].tools.some(t=>t.name==='request_component'));await assert.rejects(callback('maker-tool',{task:off.id,tool:'request_component',arguments:{}}),/未获准/);await api('studio.agent.cancel',{task:off.id});
 const second=await api('studio.create',{kind:'network',dependencies:[]}),fork=await api('studio.agent.start',{id:second.id,requirement:'换成三个成员',fork_session:off.session_id,seed_only:true,auto_publish:false});assert.deepEqual(created[1].fork_cursor,{seed:true});await api('studio.agent.cancel',{task:fork.id});
 const on=await api('studio.agent.start',{id:second.id,requirement:'允许补组件',allow_component_creation:true,auto_publish:false});assert.ok(created.at(-1).tools.some(t=>t.name==='request_component'));await assert.rejects(callback('maker-tool',{task:on.id,tool:'component_status',arguments:{task:'other'}}),/当前预设/);await api('studio.agent.cancel',{task:on.id});
 assert.ok(!makerTools('module',true).some(t=>t.name==='request_component'));
});

test('current-network test copies own state and files, isolate edits and reject stale candidate code',async t=>{
 const {api}=await fixture(t);const w=await api('studio.create',{sample:'blank',dependencies:[]});
 const manifest=JSON.parse(w.files['module.json']);manifest.node_types=['node','agent','text_file'];await api('studio.save',{id:w.id,file:'module.json',content:JSON.stringify(manifest),expected:checksum(w.files['module.json'])});
 const original=(await api('state')).live.document;
 const copy=await api('studio.environment',{id:w.id,action:'reset'});assert.equal(copy.ok,true,JSON.stringify(copy));assert.equal(copy.nodes[0].id,'root');assert.deepEqual(copy.disabled,['模型执行','外部工具','节点工具箱']);
 const mounted=await api('studio.environment',{id:w.id,action:'mount',node:'root',config:{},state:{count:10},access:{strength:0,channels:['demo']}});assert.equal(mounted.ok,true,JSON.stringify(mounted));
 const changed=await api('studio.environment',{id:w.id,action:'call',actor:'root',node:'root',operation:'increment',arguments:{amount:3},strength:0,channels:['demo']});assert.equal(changed.result.data,13,JSON.stringify(changed));
 const forbidden=await api('studio.environment',{id:w.id,action:'call',actor:'root',node:'root',operation:'increment',arguments:{amount:100},channels:['wrong']});assert.equal(forbidden.ok,false);assert.equal(forbidden.error_type,'PermissionError');
 const inspected=await api('studio.environment',{id:w.id,action:'inspect',node:'root'});assert.equal(inspected.nodes[0].modules['example.counter'].state.count,13);assert.deepEqual((await api('state')).live.document,original);
 await api('studio.save',{id:w.id,file:'module.py',content:w.files['module.py']+'\n# 新版本\n',expected:checksum(w.files['module.py'])});await assert.rejects(api('studio.environment',{id:w.id,action:'inspect'}),/源码已修改/);
 const next=await api('studio.environment',{id:w.id,action:'reset'});assert.notEqual(next.directory,copy.directory);assert.ok(await fs.stat(copy.directory));
 const network=await api('studio.create',{kind:'network',dependencies:[]});await api('studio.copy_current',{id:network.id});const draft=await api('studio.read',{id:network.id});assert.equal(JSON.parse(draft.files['network.json']).network.nodes[0].context_cursor,null);assert.deepEqual((await api('state')).live.document,original);
});

test('a configuration wish can reuse an existing component and publish bookmarks without generating implementation',async t=>{
 const {api}=await fixture(t);const before=(await api('studio.catalog')).library['metadata.fields'];const work=await api('studio.create',{sample:'blank',dependencies:[]});
 const presets={format:'nexarbor-component-presets/v1',presets:[{module:'metadata.fields',name:'商店资料',description:'现有字段组件的配置方案',config:{fields:{类型:'商店'}}}]};
 await api('studio.save',{id:work.id,file:'presets.json',content:JSON.stringify(presets),expected:checksum('')});let check=await api('studio.validate',{id:work.id});assert.equal((await finished(api,check.id)).status,'passed');
 const published=await api('studio.publish',{id:work.id});assert.equal(published.kind,'component-presets');assert.equal(published.bookmarks.length,1);
 let library=await api('editor.library');const book=library.bookmarks.find(b=>b.id===published.bookmarks[0]);assert.deepEqual(book.asset,{kind:'module',id:'metadata.fields',config:{fields:{类型:'商店'}}});assert.deepEqual(library.history,[]);
 await api('studio.publish',{id:work.id});library=await api('editor.library');assert.equal(library.bookmarks.length,1);assert.deepEqual((await api('studio.catalog')).library['metadata.fields'],before);
 const old=JSON.stringify(presets);presets.presets[0].module='missing';await api('studio.save',{id:work.id,file:'presets.json',content:JSON.stringify(presets),expected:checksum(old)});check=await api('studio.validate',{id:work.id});assert.equal((await finished(api,check.id)).status,'failed');await assert.rejects(api('studio.publish',{id:work.id}));
});

test('network maker rejects unsupported execution shapes and merges only workcopy nodes',async t=>{
 const {api}=await fixture(t);const work=await api('studio.create',{kind:'network',dependencies:[]});const document=JSON.parse(work.files['network.json']);const rootNode=document.network.nodes[0];
 for(const binding of [{executor:'harness',prepare:true},{executor:'harness',prepare:{module:'agents.context',operation:'prepare'}},{executor:'harness',tool_provider:{}},{executor:'harness',channels:['tools','tools']}]){
  const invalid=structuredClone(document);invalid.network.nodes[0].execution=binding;assert.equal((await api('validate',{document:invalid})).valid,false);
 }
 const a=await api('studio.maker_tool',{id:work.id,tool:'network_patch',arguments:{nodes:[{...rootNode,name:'修改后的入口'}],files:{'data/note.md':'资料'}}});assert.equal(a.nodes,1);
 const edited=JSON.parse((await api('studio.read',{id:work.id})).files['network.json']);assert.equal(edited.network.nodes[0].name,'修改后的入口');assert.equal(edited.files['data/note.md'],'资料');assert.notEqual((await api('state')).live.document.network.nodes[0].name,'修改后的入口');
 const component=await api('studio.create',{dependencies:[]});await assert.rejects(api('studio.maker_tool',{id:component.id,tool:'network_patch',arguments:{nodes:[]}}),/只有网络/);
});
