// 使用已安装 Harness SDK。用户已明确授权本任务复用 E 盘账户调用官方 API。
const fs=require('node:fs/promises'),path=require('node:path');
module.exports=async function(p){
 const loader=await require('../runtime/loader.cjs')(),native=loader.native,{Context}=native('cordis'),host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(native('dsh-session-title').SessionTitleService,{fallbackMaxWords:12,fallbackMaxBytes:120,maxTitleBytes:256});
 const persistence=native('dsh-session-persistence-jsonl');await host.plugin(persistence.default??persistence,{root:path.join(p.directory,'maker-logs')});
 await host.plugin((await loader.load(p.root+'/adapters/harness/runtime/agent-loop/lib/index.js')).default,{agents:[]});
 const grant=require(path.join(loader.root,'yaml')).parse(await fs.readFile(p.credentials,'utf8')).records['deepseek-account-platform/default'];
 if(grant?.kind!=='grant'||new URL(grant.payload.issuer).origin!=='https://platform.deepseek.com')throw Error('未找到受支持的 Harness DeepSeek 账户授权');
 const deepseek=native('dsh-llm-deepseek'),models=JSON.parse(await fs.readFile(p.root+'/in-history.patch.yml','utf8')).find(r=>r.id==='llm-deepseek-account').config.models;
 const model={provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:'low',maxTokens:24000,contextWindow:500000,...p.options?.model};
 const connection=deepseek.resolveAdapterOptions({models,maxTokens:model.maxTokens,retryPolicy:{mode:'normal',maxRetries:0},streamIdleTimeoutMs:60000});
 host.llm.registerAdapter(['deepseek-account'],new deepseek.DeepSeekAdapter({options:()=>connection,resolveAuth:async c=>{if(new URL(c.baseURL).origin!=='https://api.deepseek.com')throw Error('非预期模型端点');return {headers:{'x-dsh-auth-token':grant.payload.token}};},resolveUserId:()=> 'nexarbor-makers',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
 let requests=0;const started=Date.now(),fetch=globalThis.fetch,limit=p.options?.max_requests??1200;
 globalThis.fetch=async(url,args)=>{if(new URL(url).origin!=='https://api.deepseek.com')throw Error('非预期请求端点');if(++requests>limit||Date.now()-started>(p.options?.max_seconds??21600)*1000)throw Error('制作测试已达到请求数或时间上限');return fetch(url,args);};
 return {host,native,loader,model,requests:()=>requests,createUserMessage:native('dsh-llm').createUserMessage};
};
