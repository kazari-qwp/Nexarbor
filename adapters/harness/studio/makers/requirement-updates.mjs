// Bounded, durable supplements to an already supervised maker task.
import {createHash} from 'node:crypto';
export const requirementReference='reference/追加要求.json';
const reference=requirementReference;
export class RequirementUpdates{
 constructor(manager){this.manager=manager;this.states=new Map();}
 state(job){let state=this.states.get(job.id);if(!state){state={tail:Promise.resolve(),queued:new Map()};this.states.set(job.id,state);}return state;}
 async enqueue(job,{requirement,source}){
  if(typeof requirement!=='string'||!requirement.trim()||requirement.length>16000)throw Error('追加要求为1至16000字符');
  if(job.status!=='running'||job.requirements_closed||Date.now()>=job.deadline)return {task:job.id,status:job.status,delivery:'not_delivered',reason:'task_finalizing',hint:'要求尚未投递；当前任务结束后用 task 继续或修订。'};
  const id=createHash('sha256').update(requirement).digest('hex'),history=job.requirement_updates??=[];
  const old=history.find(update=>update.id===id&&update.status!=='failed');
  if(old)return {task:job.id,status:job.status,delivery:'duplicate',update:id,previous_delivery:old.status,reference};
  if(history.length>=32)throw Error('每个制作任务最多接收32条追加要求');
  const entry={id,source,received:Date.now(),status:'saving'},state=this.state(job);history.push(entry);state.queued.set(id,{entry,text:requirement});job.self_review_done=false;
  const pending=state.tail.then(async()=>{
   try{
    await this.manager.rpc('studio_append_requirement',{id:job.workspace,update:{id,source,text:requirement,received:entry.received}});
    let receipt={delivered:false};
    if(job.status==='running'&&!job.requirements_closed&&Date.now()<job.deadline){
     try{receipt=await this.manager.runner.request('message',{session_id:job.session_id,update_id:id,prompt:'委托方补充要求，原需求仍有效；在当前工作副本与原预算内处理：\n'+requirement+'\n追加原文已保存于 '+reference});}catch(error){entry.delivery_error=String(error.message).slice(0,200);}
    }
    entry.status=receipt.delivered?'delivered':'queued';if(receipt.delivered)state.queued.delete(id);
    return {task:job.id,status:job.status,delivery:entry.status,update:id,reference};
   }catch(error){entry.status='failed';state.queued.delete(id);throw error;}
  });
  state.tail=pending.catch(()=>{});return pending;
 }
 async drain(job){
  const state=this.states.get(job.id);if(!state)return '';
  for(;;){const pending=state.tail;await pending;if(pending===state.tail)break;}
  const entries=[...state.queued.values()].filter(({entry})=>entry.status==='queued');
  for(const {entry}of entries){entry.status='included';state.queued.delete(entry.id);}
  return entries.length?'继续处理委托方在本次任务内追加的要求（原需求仍有效，原文保存在 '+reference+'）：\n'+entries.map(({text},index)=>String(index+1)+'. '+text).join('\n'):'';
 }
 busy(job){return (job.requirement_updates??[]).some(entry=>entry.status==='saving'||entry.status==='queued');}
 clear(job){this.states.delete(job.id);}
}
