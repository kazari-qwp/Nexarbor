// 使用已安装 Harness SDK；模型与凭据按每个制作职责的选择解析。
const fs=require('node:fs/promises'),path=require('node:path');
module.exports=async function(p){
 const loader=await require('../runtime/loader.cjs')(),native=loader.native,{Context}=native('cordis'),host=new Context();
 for(const [name,service] of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(native('dsh-skill').SkillRegistry);
 // Newer Harness skill loaders resolve the session's committed working directory.
 if(native('dsh-tool-skill').inject.includes('workingDirectory')){
  await host.plugin(native('dsh-fs-local').LocalFileSystem,{cwd:p.directory});
  await host.plugin(native('dsh-working-directory').WorkingDirectoryService,{defaultDirectory:path.resolve(p.directory)});
 }
 await host.plugin(native('dsh-session-title').SessionTitleService,{fallbackMaxWords:12,fallbackMaxBytes:120,maxTitleBytes:256});
 await host.plugin(native('dsh-attachment-local').LocalAttachmentStore,{dshHome:p.directory});
 const persistence=native('dsh-session-persistence-jsonl');await host.plugin(persistence.default??persistence,{root:path.join(p.directory,'maker-logs')});
 await host.plugin((await loader.load(p.root+'/adapters/harness/runtime/agent-loop/lib/index.js')).default,{agents:[]});
 const model={provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:'low',maxTokens:24000,contextWindow:500000,...p.options?.model};
 const models=await require('../runtime/model-adapters.cjs')({host,native,root:p.root,credentials:p.credentials,defaults:model});
 let requests=0;const started=Date.now(),fetch=globalThis.fetch,limit=p.options?.max_requests??1200;
 globalThis.fetch=async(url,args)=>{if(++requests>limit||Date.now()-started>(p.options?.max_seconds??21600)*1000)throw Error('制作测试已达到请求数或时间上限');return fetch(url,args);};
 return {host,native,loader,model,resolveModel:profile=>models.resolve(profile),redact:models.redact,requests:()=>requests,createUserMessage:native('dsh-llm').createUserMessage};
};
