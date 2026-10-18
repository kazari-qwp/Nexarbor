// 独立制作验收；只通过正式工作副本接口与制作 Agent 交互。
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const spec=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const directory=path.resolve(spec.directory??path.join(root,'build/maker-paid-'+Date.now()));
const host=await startStudio({directory});
try{
 await host.rpc('studio_agent_connect',{runtime:{max_requests:spec.max_requests??100,max_seconds:spec.timeout??900}});
 const work=spec.workspace?await host.rpc('studio_read',{id:spec.workspace}):await host.rpc('studio_create',{sample:'blank',kind:spec.kind??'tool',name:spec.name??'制作验收',dependencies:spec.dependencies??[]});
 const job=await host.rpc('studio_agent_start',{id:work.id,name:spec.name,requirement:spec.requirement,timeout:spec.timeout??600,max_repairs:spec.max_repairs??3,max_steps:spec.max_steps??70,hidden_modules:spec.hidden_modules??[],fork_session:spec.fork_session,resume_session:spec.resume_session,seed_only:spec.seed_only,auto_publish:spec.auto_publish!==false,allow_component_creation:spec.allow_component_creation===true});
 console.log(JSON.stringify({directory,workspace:work.id,task:job.id,session_id:job.session_id}));
 let result;
 for(;;){result=await host.rpc('studio_agent_read',{task:job.id});console.log(JSON.stringify({status:result.status,phase:result.phase,steps:result.steps,requests:result.requests,tools:result.tool_events?.length,repairs:result.repairs,last:result.tool_events?.at(-1)?.tool}));if(result.status!=='running')break;await new Promise(r=>setTimeout(r,15000));}
 await fs.writeFile(path.join(directory,'trial-result.json'),JSON.stringify({spec,result},null,2));
 console.log(JSON.stringify({status:result.status,error:result.error,validation_log:result.validation_log,release:result.release?.id}));process.exitCode=result.status==='completed'?0:1;
}finally{await host.close();}
