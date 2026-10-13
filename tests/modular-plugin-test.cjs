const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
const llm=native('dsh-llm'),{Context}=native('cordis'),{Session}=native('dsh-session');
const base=productRoot;
function agentContext(){const ctx=new Context(),tools=new Map();ctx.provide('tools',{register:def=>{tools.set(def.name,def);return ()=>tools.delete(def.name)},guard:()=>()=>{}});ctx.provide('systemPrompt',{section:()=>()=>{}});ctx.toolsMap=tools;return ctx;}
(async()=>{
 const cache=new Map(),context=vm.createContext({process,console,Buffer,URL,AbortController,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
 const synthetic=(ns,id)=>{const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context,identifier:id})};
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null;
  const key=file??spec;if(cache.has(key))return cache.get(key);
  if(file?.replaceAll('\\','/').endsWith('framework/capabilities.js')){const mod=synthetic({applyCapabilities:async()=>({officialPreset:'standard'}),updateCapabilityTools:()=>({})},key);cache.set(key,mod);return mod;}
  if(!file){const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):await import(spec);const mod=synthetic(ns,key);cache.set(key,mod);return mod;}
  const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href,importModuleDynamically:async(spec,ref)=>{const m=await get(spec,ref.identifier);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m;}});cache.set(key,mod);return mod;
 }
 const link=(spec,ref)=>get(spec,ref.identifier);const entry=await get(pathToFileURL(base+'/index.js').href);await entry.link(link);await entry.evaluate();
 async function boot(components={}){
  const temp=await fs.mkdtemp(path.join(testRoot,'modular-plugin-')),host=new Context();host.provide('sessions',{flush:async()=>{}});host.provide('sessionTitle',{rename(){}});
  const runtime=await entry.namespace.apply(host,{workspace:temp,storage:path.join(temp,'.datanet'),...(process.env.DATANET_TEST_PYTHON?{backend:process.env.DATANET_TEST_PYTHON,backendArgs:[base+'/adapters/harness/backend/server.py']}:{}),rootNetwork:'project_root',rootToolboxes:['network_access','node_creation','agent_management','interface_management','discussion','self_repair','network_management_skill'],maxSignalStrength:100,components});
  const root={ctx:agentContext(),id:'modular-root',options:{},status:'idle',session:Session.create('modular-root',[],{...Session.create('modular-root').header,cwd:temp}),inbox:{nextTurn:[],nextStep:[]},steer(){}};
  await host.parallel('agent/created',{agent:root});
  return {host,runtime,root,temp,async close(){await runtime.components.dispose();await runtime.bridge.close();await host.fiber.dispose();}};
 }
 const app=await boot();
 try{
  const call=async(name,args={})=>{const tool=app.root.ctx.toolsMap.get(name);assert.ok(tool,name+' registered');return tool.execute(args,{agent:app.root,callId:'modular-'+name});};
  assert.equal([...app.root.ctx.toolsMap.keys()].filter(x=>x.startsWith('query_text_')).length,3);
  const skills=await call('datanet_skill',{action:'list'});assert.ok(skills.skills.some(s=>s.id==='network_management'));
  await call('datanet_create_node_channel');const node=await call('datanet_create_node',{child_id:'ref',node_spec:{preset:'query_text',name:'测试资料'}});assert.equal(node.status,'ok');
  await call('node_write',{target:'root/ref',key:'content',value:'共享正文'});
  await call('datanet_create_network_channel',{preset:'discussion_group'});
  const group=await call('datanet_create_network',{preset:'discussion_group',instance_id:'modular',project_nodes:['root/project','root/ref'],with_agents:false,rounds:1});assert.equal(group.status,'ok');
  assert.deepEqual(JSON.parse(JSON.stringify(group.entry_points.projects)),['root/project','root/ref']);
  assert.ok(!app.root.ctx.toolsMap.has('datanet_resolve_feedback_channel'));
  assert.ok(!app.root.ctx.toolsMap.has('datanet_reports_channel'));
  await app.runtime.delegateReport(app.root.ctx,'root/ref','最小委托',agentContext());
  assert.ok(app.root.ctx.toolsMap.has('datanet_reports_channel'));
  const reportOpened=await call('datanet_reports_channel');assert.equal(reportOpened.instructions_added,true);
  assert.equal((await call('datanet_reports_channel')).instructions_added,false);
  assert.ok(await call('datanet_report_read',{root_request_id:reportOpened.root_request_id,path:'node-index.json'}));
  await app.runtime.remember('root/ref',{kind:'generic',session_id:'fixture-child',creator_node_id:'root'});
  const feedback=await app.runtime.bridge.call('report_feedback',{actor:'root/ref',category:'missing_tool'});
  await app.host.serial('datanet/feedback-received',{report:feedback});
  assert.ok(app.root.ctx.toolsMap.has('datanet_resolve_feedback'));
  const member={ctx:agentContext(),id:'member-fixture',options:{},status:'idle',session:Session.create('member-fixture'),inbox:{nextTurn:[],nextStep:[]},received:[],steer(message){this.received.push(message)}};
  const grant=app.runtime.resolveAgentToolboxes([],undefined,{role:'discussion'});
  app.runtime.scopes.set(member.ctx,{grant,actor:'root/ref',maxStrength:2});
  await app.runtime.prepareAgent(member.ctx,'root/ref','member');app.runtime.bindAgentContext(member.ctx,member,'root/ref','member');
  await app.host.serial('datanet/agent-ready',{ac:member.ctx,agent:member,actor:'root/ref'});
  assert.ok(!member.ctx.toolsMap.has('datanet_send_message'));
  const receipt=await call('datanet_send_message',{target:'root/ref',content:'请回复'});
  assert.equal(member.received.length,1);
  const reply=member.ctx.toolsMap.get(app.runtime.messaging.entries[receipt.message_id].reply_tool);
  assert.equal(reply.description,'仅用来回复此条消息，调用一次后失效');
  await reply.execute({content:'已收到'},{agent:member});
  assert.throws(()=>reply.execute({content:'再次回复'},{agent:member}),/停用|disabled/);
  await assert.rejects(()=>app.runtime.messaging.send('root/ref','root','主动发送'),/停用|disabled/);
  const sections=app.runtime.components.disposers.get('toolboxes/problem_handling').length;
  await app.runtime.prepareAgent(app.root.ctx,'root');
  assert.equal(app.runtime.components.disposers.get('toolboxes/problem_handling').length,sections);
  const disabled=app.runtime.components.disable('toolboxes/experience');assert.ok(disabled.includes('toolboxes/problem_handling'));
  await assert.rejects(()=>call('datanet_resolve_feedback',{target:'root/ref',action:'inspect'}),/停用|disabled/);
  app.runtime.components.disable('nodes/text');
  const tail=await app.root.ctx.waterfall('agent/request-tail',{},()=>[]);assert.equal(tail.length,0);
  await call('node_write',{target:'root/ref',key:'content',value:'关闭经验后可写'});
  console.log('PASS native Cordis events + compiled backend: feedback gate, delegation reports, received-message reply only, single-use reply, idempotent hooks, revocation, tail cleanup, retained node operations');
 }finally{await app.close();}
 const app2=await boot({'toolboxes/experience':false,'toolboxes/agent_messaging':false,'tools/reports':false});
 try{assert.ok(app2.root.ctx.toolsMap.has('node_read'));assert.ok(!app2.root.ctx.toolsMap.has('handle_problem'));assert.ok(!app2.root.ctx.toolsMap.has('datanet_send_message'));await assert.rejects(()=>fs.stat(path.join(app2.temp,'.datanet','experiences')),e=>e.code==='ENOENT');await app2.runtime.diagnostics.start(app2.root.ctx);await app2.runtime.diagnostics.completed(app2.root.ctx,'本地完成');console.log('PASS startup without experience, problem, reports and messaging; no experience library created');}finally{await app2.close();}
 const app3=await boot({'nodes/text':false});
 try{assert.ok(app3.root.ctx.toolsMap.has('node_read'));assert.equal((await app3.runtime.bridge.call('ping')).nodes,1);assert.equal([...app3.root.ctx.toolsMap.keys()].filter(x=>x.startsWith('query_text_')).length,0);console.log('PASS fresh startup with the configured root preset disabled by its text dependency');}finally{await app3.close();}
})().catch(error=>{console.error(error);process.exit(1);});
