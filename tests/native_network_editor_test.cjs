// Bounded native host for workbench acceptance. Real SDK/JSONL, deterministic model.
const fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const product=path.resolve(__dirname,'..'),run=path.resolve(process.env.DATANET_TEST_OUTPUT??path.join(product,'build/network-editor-native'));
const keepAlive=setInterval(()=>{},1000);
setTimeout(()=>{console.error('Editor test host deadline (60 minutes)');process.exit(1);},3600000).unref();
(async()=>{
 await fs.mkdir(run,{recursive:true});
 const nativeRoot=path.join(process.env.LOCALAPPDATA,'Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules');
 const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
 const context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});const cache=new Map();
 const synthetic=(ns,id)=>{const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const k of keys)this.setExport(k,k==='default'?(ns.default??ns):ns[k]);},{context,identifier:id});};
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null,key=file??spec;if(cache.has(key))return cache.get(key);
  if(file?.replaceAll('\\','/').endsWith('framework/capabilities.js')){const mod=synthetic({applyCapabilities:async()=>({officialPreset:'standard'}),updateCapabilityTools:()=>({})},key);cache.set(key,mod);return mod;}
  if(!file){const mod=synthetic(spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):await import(spec),key);cache.set(key,mod);return mod;}
  const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href,importModuleDynamically:async(spec,ref)=>{const m=await get(spec,ref.identifier);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m;}});cache.set(key,mod);return mod;
 }
 const link=(spec,ref)=>get(spec,ref.identifier),load=async file=>{const m=await get(pathToFileURL(file).href);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m.namespace;};
 const {Context}=native('cordis'),host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(native('dsh-session-title').SessionTitleService,{fallbackMaxWords:12,fallbackMaxBytes:120,maxTitleBytes:256});
 await host.plugin(native('dsh-session-persistence-jsonl').default,{root:path.join(run,'native-logs')});
 const loop=await load(path.join(product,'adapters/harness/runtime/agent-loop/lib/index.js'));await host.plugin(loop.default,{agents:[]});
 const entry=await load(path.join(product,'extensions/editor/capabilities/network_editor/entry.js'));
 const controller=await entry.apply(host,{workspace:run,storage:path.join(run,'.datanet'),backend:path.join(product,'.venv/Scripts/python.exe'),backendArgs:[path.join(product,'adapters/harness/backend/server.py')],agentMaxTokens:4096,editor:{mode:'Native Mock'}});
 const llm=native('dsh-llm');
 class Model extends llm.LlmAdapter{
  steps={};calls=[];active=0;peak=0;
  async resolveModel(provider,id){return {provider,id,name:id,toolUpdate:'addition-only',systemPromptUpdate:'in-history'};}
  async *stream(options){
   this.active++;this.peak=Math.max(this.peak,this.active);await new Promise(r=>setTimeout(r,80));
   const text=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
   const actor=text.includes('[Editor A]')?'alice':text.includes('[Editor B]')?'bob':'root';
   const step=this.steps[actor]??0;this.steps[actor]=step+1;
   let tool=null,args={};
   if(actor==='alice'&&step<3){
    const prefix=['near_talk_','near_chop_','near_move_here_'][step];
    tool=options.tools.find(t=>(t.function?.name??t.name).startsWith(prefix)&&(step!==2||(t.function?.description??t.description).startsWith('商店：')));
    if(step===0)args={content:'你好，我去砍点木材，然后去商店。'};
   }else if(actor==='bob'&&step===0){tool=options.tools.find(t=>(t.function?.name??t.name).startsWith('near_talk_'));args={content:'你好，路上小心。'};}
   const block=tool?{type:'tool-call',id:actor+'-'+step,name:tool.function?.name??tool.name,arguments:JSON.stringify(args)}:{type:'text',text:'已完成本次活动。'};
   this.calls.push({actor,step,tool:block.name??null});
   yield {type:'block-start',index:0,blockType:block.type};if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};
   yield {type:'block-end',index:0,block};yield {type:'usage',usage:{inputTokens:10,outputTokens:2}};yield {type:'finish',reason:{kind:'stop'}};
   this.active--;
  }
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const root=await host.agentLoop.create(native('dsh-session').SessionId('network-editor-'+Date.now()),{provider:'mock',model:'mock'},{cwd:run});
 await host.parallel('agent/created',{agent:root});const runtime=controller.runtimes.get(root.id);
 root.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'网络工作台最小测试就绪。'}]}));await root.whenIdle();
 const connection={url:runtime.editor.url,authority:runtime.editor.authority,directory:runtime.directory,workspace:run,mode:'native-mock',model_api_calls:0};
 await fs.writeFile(path.join(run,'editor.json'),JSON.stringify(connection,null,2));
 async function manifest(){
  const live=await runtime.bridge.call('application/component',{component:'capabilities/network_editor',operation:'state',params:{}},0);
  const rows=[];
  for(const [rootId,network] of controller.runtimes){
    rows.push({actor:'root',agent:network.rootAgent,rootId});
    for(const [actor,entry] of network.sessions)rows.push({actor,agent:entry.handle.agent,rootId});
  }
  const sessions=[];
  for(const row of rows){const node=live.live.document.network.nodes.find(n=>n.node_id===row.actor),title='网络编辑器测试（Mock） · '+(node?.name??row.actor)+(row.rootId===root.id?'':'（恢复）');if(host.sessionTitle.get(row.agent.session).title!==title)host.sessionTitle.rename(row.agent.session,title);await host.sessions.flush(row.agent.session);sessions.push({actor:row.actor,network_root:row.rootId,session_id:row.agent.id,name:node?.name??row.actor,events:row.agent.session.seq,title});}
  await fs.writeFile(path.join(run,'sessions-manifest.json'),JSON.stringify({kind:'native-mock',workspace:run,native_logs:path.join(run,'native-logs'),root_session:root.id,sessions},null,2));
  await fs.writeFile(path.join(run,'acceptance-state.json'),JSON.stringify({job:live.job,document:live.live.document,requests:model.calls,peak_parallel_streams:model.peak,model_api_calls:0},null,2));
 }
 await manifest();setInterval(()=>manifest().catch(e=>console.error(e.message)),2500);
 console.log('READY native network editor; connection saved in '+path.join(run,'editor.json'));
})().catch(e=>{console.error(e);process.exit(1);});
