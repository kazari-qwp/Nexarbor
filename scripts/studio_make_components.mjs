import {startStudio} from '../adapters/harness/studio/host.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
const [workspace,requestFile,output]=process.argv.slice(2);if(!output)throw Error('Usage: studio_make_components workspace requests.json output');
await fs.mkdir(output,{recursive:true});let h;
if(workspace.endsWith('.json')){
 const connection=JSON.parse(await fs.readFile(workspace,'utf8')),url=new URL(connection.url),token=new URLSearchParams(url.hash.slice(1)).get('token');
 h={close:async()=>{},rpc:async(method,params={})=>{const response=await fetch(url.origin+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation:'studio.'+method.slice(7).replaceAll('_','.'),params})});const result=await response.json();if(result.error)throw Error(result.error);return result.value;}};
}else h=await startStudio({directory:path.resolve(workspace)});
try{
 await h.rpc('studio_agent_connect',{});
 const queue=JSON.parse(await fs.readFile(requestFile,'utf8'));let index=0;
 async function worker(){
  while(index<queue.length){
   const request=queue[index++];
   const w=request.workspace?await h.rpc('studio_read',{id:request.workspace}):await h.rpc('studio_create',{sample:'empty',dependencies:request.dependencies??[]});
   if(request.workspace&&request.dependencies?.length)await h.rpc('studio_dependencies',{id:w.id,modules:request.dependencies});
   let validation;
   if(request.verify_existing&&JSON.parse(w.files['module.json']).id!=='example.module'){
    let check=await h.rpc('studio_validate',{id:w.id});while(check.status==='running'){await new Promise(r=>setTimeout(r,1000));check=await h.rpc('studio_job',{job:check.id});}
    validation=check.id;
    if(check.status==='passed'){
     const release=await h.rpc('studio_publish',{id:w.id});await fs.writeFile(path.join(output,request.name+'-release.json'),JSON.stringify(release,null,2));await fs.writeFile(path.join(output,request.name+'-result.json'),JSON.stringify({workspace:w.id,status:'completed',phase:'verified_existing',validation:check.id,log:check.log,new_model_calls:0,session_id:request.resume_session},null,2));console.log('VERIFIED EXISTING',request.name,release.id);continue;
    }
   }
   const task=await h.rpc('studio_agent_start',{id:w.id,requirement:request.prompt,timeout:request.timeout??540,validation,model:{provider:'deepseek-account',model:'deepseek-flash',reasoningEffort:request.effort??'low'},...(request.fork_session?{fork_session:request.fork_session}:request.resume_session?{resume_session:request.resume_session}:{})});
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
}finally{
 if(!workspace.endsWith('.json')){
  // Another client may have queued work while this batch was running.
  for(;;){const state=await h.rpc('studio_agent_status');if(!state.jobs.some(j=>j.status==='running'))break;await new Promise(r=>setTimeout(r,15000));}
 }
 await h.close();
}
