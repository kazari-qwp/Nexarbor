import {startStudio} from '../adapters/harness/studio/host.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
const [workspace,requestFile,output]=process.argv.slice(2);if(!output)throw Error('Usage: studio_make_components workspace requests.json output');
await fs.mkdir(output,{recursive:true});const h=await startStudio({directory:path.resolve(workspace)});
try{
 await h.rpc('studio_agent_connect',{});
 const queue=JSON.parse(await fs.readFile(requestFile,'utf8'));let index=0;
 async function worker(){
  while(index<queue.length){
   const request=queue[index++];
   const w=request.workspace?await h.rpc('studio_read',{id:request.workspace}):await h.rpc('studio_create',{sample:'empty',dependencies:request.dependencies??[]});
   const task=await h.rpc('studio_agent_start',{id:w.id,requirement:request.prompt,timeout:request.timeout??540,model:{provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:request.effort??'low'},...(request.fork_session?{fork_session:request.fork_session}:{})});
   await fs.writeFile(path.join(output,request.name+'-task.json'),JSON.stringify({workspace:w.id,...task,prompt:request.prompt},null,2));console.log('MAKING',request.name,task.session_id);
   while(true){
    await new Promise(r=>setTimeout(r,15000));const result=await h.rpc('studio_agent_read',{task:task.id});if(result.status==='running')continue;
    await fs.writeFile(path.join(output,request.name+'-result.json'),JSON.stringify(result,null,2));console.log('RESULT',request.name,result.status,result.phase);
    if(result.status==='completed'){
     const release=await h.rpc('studio_publish',{id:w.id});await fs.writeFile(path.join(output,request.name+'-release.json'),JSON.stringify(release,null,2));console.log('PUBLISHED',request.name,release.id);
    }break;
   }
  }
 }
 await Promise.all([worker(),worker()]);
}finally{await h.close();}
