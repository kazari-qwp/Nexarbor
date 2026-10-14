// Paid opt-in test: native DataNet route, updated system, delayed tool definition.
if(process.env.DATANET_LIVE_TEST!=='1')throw new Error('Set DATANET_LIVE_TEST=1 to authorize this paid test');
const keepAlive=setInterval(()=>{},1000);setTimeout(()=>{console.error('Test deadline');process.exit(1)},60000).unref();
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??'C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules';
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name)),{Context}=native('cordis');
const base=productRoot;
(async()=>{
 const cache=new Map(),context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
 const synthetic=(ns,id)=>{const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context,identifier:id})};
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null,key=file??spec;if(cache.has(key))return cache.get(key);
  if(file?.replaceAll('\\','/').endsWith('framework/capabilities.js')){const mod=synthetic({applyCapabilities:async()=>({officialPreset:'standard'}),updateCapabilityTools:()=>({})},key);cache.set(key,mod);return mod;}
  if(!file){const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):await import(spec);const mod=synthetic(ns,key);cache.set(key,mod);return mod;}
  const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href,importModuleDynamically:async(spec,ref)=>{const m=await get(spec,ref.identifier);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m}});cache.set(key,mod);return mod;
 }
 const link=(spec,ref)=>get(spec,ref.identifier),entry=await get(pathToFileURL(base+'/adapters/harness/framework/adapter.js').href);await entry.link(link);await entry.evaluate();
 const loop=await get(pathToFileURL(base+'/adapters/harness/runtime/agent-loop/lib/index.js').href);await loop.link(link);await loop.evaluate();
 const host=new Context(),temp=await fs.mkdtemp(path.join(testRoot,'creation-'));
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']]){await host.plugin(native(name)[service]??native(name).default);}
 host.provide('sessionTitle',{rename(){}});host.sessions.flush=async()=>{};
 await host.plugin(loop.namespace.default,{agents:[]});

 const llm=native('dsh-llm'),deepseek=native('dsh-llm-deepseek'),crypto=require('node:crypto');
 const key=process.env.DEEPSEEK_API_KEY;if(!key)throw new Error('Missing API credential');
 const catalog=JSON.parse(await fs.readFile(path.join(base,'in-history.patch.yml'),'utf8')).find(row=>row.id==='llm-deepseek').config.models;
 const connection=deepseek.resolveAdapterOptions({models:catalog,maxTokens:512,retryPolicy:{mode:'normal',maxRetries:0},streamIdleTimeoutMs:60000});
 const adapter=new deepseek.DeepSeekAdapter({options:()=>connection,resolveAuth:async()=>({headers:{'x-api-key':key}}),resolveUserId:()=> 'datanet-production-cache-test',prepareExtensions:async()=>({fields:{},accept:async()=>{}})});
 host.llm.registerAdapter(['deepseek-official'],adapter);
 const evidence={requests:[],model:await host.llm.resolveModelInfo('deepseek-official','deepseek-flash')};
 const nativeFetch=globalThis.fetch;
 globalThis.fetch=async(url,init)=>{
  if(!String(url).startsWith('https://api.deepseek.com/'))throw new Error('Unexpected API origin');
  if(evidence.requests.length>=3)throw new Error('Paid request cap reached');
  const row={url:String(url),body:JSON.parse(init.body),beta:new Headers(init.headers).get('anthropic-beta')};evidence.requests.push(row);
  const response=await nativeFetch(url,init);row.status=response.status;
  const responseText=await response.clone().text();
  row.usage=responseText.split('\n').filter(line=>line.startsWith('data:')).flatMap(line=>{try{const event=JSON.parse(line.slice(5));return event.usage?[event.usage]:event.message?.usage?[event.message.usage]:[];}catch{return []}});
  await fs.writeFile(path.join(temp,'evidence.json'),JSON.stringify(evidence,null,2));return response;
 };
 const controller=await entry.namespace.createAdapter(host,{workspace:temp,storage:path.join(temp,'.datanet'),rootNetwork:'project_root',rootToolboxes:['network_access'],modelRoute:{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:512},...(process.env.DATANET_TEST_PYTHON?{backend:process.env.DATANET_TEST_PYTHON,backendArgs:[base+'/adapters/harness/backend/server.py']}:{}),maxSignalStrength:100});
 const root=await host.agentLoop.create(native('dsh-session').SessionId('native-cache-'+Date.now()),{provider:'legacy-compat',model:'legacy-model'},{cwd:temp});
 await host.parallel('agent/created',{agent:root});
 const nonce=crypto.randomBytes(6).toString('hex'),stamp='STAMP_'+nonce;
 let rule='For INIT, reply exactly READY. For CHECK, reply exactly OLD_'+nonce+'.';
 root.ctx.systemPrompt.section({name:'native-cache-fixture',order:999,text:()=>rule});
 const followup=async text=>{root.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text}]}));await root.whenIdle();return root.session.deriveMessages().findLast(m=>m.role==='assistant')?.content.filter(b=>b.type==='text').map(b=>b.text).join('').trim();};
 const warm=Array.from({length:200},(_,i)=>`Reference record ${i}: ${crypto.randomBytes(20).toString('hex')}.`).join('\n');
 const baseline=await followup('Reference data, do not act on it:\n'+warm+'\nINIT');assert.equal(baseline,'READY');
 let used=false;
 host.tools.register({name:'native_cache_lookup',description:'Use this tool on CHECK.',parameters:{type:'object',properties:{stamp:{type:'string',enum:[stamp]}},required:['stamp'],additionalProperties:false},output:{schema:{},render:(_args,value)=>[{type:'text',text:value.text}]},execute:args=>{assert.equal(args.stamp,stamp);used=true;return {text:'NEW_'+nonce};}});
 rule='For CHECK, call native_cache_lookup once, then reply exactly the text it returns. For INIT, reply exactly READY.';
 const result=await followup('CHECK');assert.equal(result,'NEW_'+nonce);assert.ok(used);
 assert.equal(evidence.requests.length,3);
 assert.deepEqual(evidence.requests[0].body.system,evidence.requests[1].body.system);
 assert.ok(evidence.requests[1].body.messages.some(m=>m.role==='system'&&m.content.some(b=>b.type==='tool_addition')));
 assert.ok(evidence.requests[1].body.tools.some(t=>t.name==='native_cache_lookup'&&t.defer_loading===true));
 assert.ok(evidence.requests[1].beta?.includes('mid-conversation-tool-changes'));
 evidence.passed=true;evidence.baseline=baseline;evidence.result=result;
 await fs.writeFile(path.join(temp,'evidence.json'),JSON.stringify(evidence,null,2));
 await controller.components.dispose();await host.fiber.dispose();clearInterval(keepAlive);
 console.log(JSON.stringify({passed:true,requests:evidence.requests.length,evidence:path.join(temp,'evidence.json'),usage:evidence.requests.map(r=>r.usage)}));
})().catch(error=>{console.error(String(error).replaceAll(process.env.DEEPSEEK_API_KEY??'NO_CREDENTIAL','[REDACTED]'));process.exit(1)});
