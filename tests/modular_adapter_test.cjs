const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const native=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
const {Context}=native('cordis');
const context=vm.createContext({process,console,Buffer,URL,AbortController,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});
async function load(file){
 const mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href});
 await mod.link(async spec=>{
  if(spec.startsWith('.'))return load(path.resolve(path.dirname(file),spec));
  const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):spec==='zod'?require(path.join(nativeRoot,'zod')):require(spec);
  const keys=[...new Set([...Object.keys(ns),'default'])];return new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context});
 });return mod;
}
(async()=>{
 const host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 host.provide('loader',{entries:()=>[{id:'agent-loop',disabled:true,config:{maxParallelToolCalls:3,agents:[{id:'configured',sessionId:'configured-retained',cwd:testRoot,provider:'mock',model:'mock'}]}}]});
 const entry=await load(productRoot+'/adapters/harness/runtime/agent-loop/entry.js');await entry.evaluate();
 await host.plugin(entry.namespace.default);
 assert.equal(host.agentLoop.config.maxParallelToolCalls.get(),3);
 assert.equal(host.agentLoop.config.agents.length,1);
 assert.ok(host.agents.list().some(a=>a.id==='configured-retained'));
 await host.fiber.dispose();
 console.log('PASS native Cordis adapter: original configured Agent and parallel-tool limit retained by replacement loop');
})().catch(error=>{console.error(error);process.exit(1)});
