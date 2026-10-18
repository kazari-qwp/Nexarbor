// 一套制作试验共用宿主；改变输入时可从同前缀的种子位置分叉。
import fs from 'node:fs/promises';import path from 'node:path';
import {startStudio} from '../adapters/harness/studio/host.mjs';
const spec=JSON.parse(await fs.readFile(process.argv[2],'utf8')),directory=path.resolve(spec.directory),host=await startStudio({directory,initialNetwork:spec.initialNetwork,components:spec.components??[]});
const evidence={started:Date.now(),spec,results:[]},output=path.join(directory,'suite-'+Date.now()+'.json');
const checkpoint=()=>fs.writeFile(output,JSON.stringify(evidence,null,2));
try{
 await host.rpc('studio_agent_connect',{runtime:{max_requests:spec.max_requests??400,max_seconds:spec.max_seconds??3600}});
 for(let i=0;i<spec.tasks.length;i+=spec.parallel??1){
  const batch=spec.tasks.slice(i,i+(spec.parallel??1));
  await Promise.all(batch.map(async task=>{
   const work=task.workspace?await host.rpc('studio_read',{id:task.workspace}):task.fork_module?await host.rpc('studio_fork',{module:task.fork_module}):await host.rpc('studio_create',{sample:'blank',kind:task.kind??'module',name:task.name,dependencies:task.dependencies??[]});
   const source=task.fork_from?evidence.results.find(r=>r.name===task.fork_from):null;
   const job=await host.rpc('studio_agent_start',{...task,id:work.id,timeout:task.timeout??1000,max_steps:task.max_steps??90,max_repairs:task.max_repairs??3,auto_publish:task.auto_publish!==false,...(source?{fork_session:source.session_id,seed_only:task.seed_only!==false}:{})});
   let result;console.log(JSON.stringify({name:task.name,workspace:work.id,task:job.id,session_id:job.session_id}));
   for(;;){result=await host.rpc('studio_agent_read',{task:job.id});console.log(JSON.stringify({name:task.name,status:result.status,steps:result.steps,tools:result.tool_events.length,last:result.tool_events.at(-1)?.tool}));if(result.status!=='running')break;await new Promise(r=>setTimeout(r,15000));}
   evidence.results.push({name:task.name,...result});await checkpoint();
  }));
 }
 evidence.finished=Date.now();await checkpoint();console.log(JSON.stringify({evidence:output,results:evidence.results.map(r=>({name:r.name,status:r.status,error:r.error,release:r.release?.id,steps:r.steps}))}));process.exitCode=evidence.results.every(r=>r.status==='completed')?0:1;
}finally{await host.close();}
