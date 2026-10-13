import {isPermissionDenied} from '../../../adapters/harness/framework/tool-permissions.js';
import {randomUUID} from 'node:crypto';
import {uuidv7,redactText} from '../../../adapters/harness/framework/record-utils.js';
const failureStatuses=new Set(['error','forbidden']);
const stamp=()=>new Date().toISOString();
export function briefError(value){
 return redactText(value??'执行异常');
}
function evidenceText(value){if(typeof value!=='string'||!value.trim()||value.length>1000)throw new Error('Resolution evidence requires 1-1000 characters');return value.trim()}
export class IncidentStore {
 constructor(store,source,version,experienceFor){this.store=store;this.source=source;this.version=version;this.experienceFor=experienceFor}
 async record(input){return this.store.mutate(db=>{
  db.incidents??=[];const existing=input.feedback_id&&db.incidents.find(e=>e.feedback_id===input.feedback_id);if(existing)return existing;
  const incident={id:randomUUID(),type:input.type??'blocked',status:'unresolved',...input,source:this.source,version:this.version,created_at:stamp()};db.incidents.push(incident);return incident;
 })}
 async query({status='all',node_id,query='',offset=0,limit=6}={}){
  if(!['all','unresolved','resolved'].includes(status)||!Number.isInteger(offset)||offset<0||!Number.isInteger(limit)||limit<1||limit>10)throw new Error('Invalid incident query');
  const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return ((await this.store.read()).incidents??[]).filter(e=>(status==='all'||e.status===status)&&(!node_id||e.node_id===node_id)&&words.every(w=>JSON.stringify(e).toLowerCase().includes(w))).slice(offset,offset+limit);
 }
 async start(meta){return this.store.mutate(db=>{db.runs??=[];const run={id:uuidv7(),...meta,source:this.source,status:'running',started_at:stamp()};db.runs.push(run);return run})}
 async finish(id,status,summary){if(!id)return;return this.store.mutate(db=>{const run=(db.runs??[]).find(e=>e.id===id);if(!run)return;if(run.status==='running'){run.status=status;run.finished_at=stamp();run.summary=redactText(summary)}return run})}
 async resolve({id,retry_run_id,evidence,experience_id},actor,maintainer=false,managerFor){
  evidence=evidenceText(evidence);
  if(experience_id&&!(await this.experienceFor?.(experience_id))?.some(e=>['pending','verified'].includes(e.status)))throw new Error('Linked experience must be pending or verified');
  return this.store.mutate(db=>{const incident=(db.incidents??[]).find(e=>e.id===id);if(!incident)throw new Error('Incident not found');
   if(!maintainer&&actor!==incident.node_id&&actor!==(managerFor?managerFor(incident.node_id):incident.manager_id??incident.creator_node_id))throw new Error('Only reporter, manager or authorized maintainer may resolve');
   if(incident.status!=='unresolved')throw new Error('Incident is already resolved');
   const run=(db.runs??[]).find(e=>e.id===retry_run_id);if(!run||run.source!==incident.source||run.node_id!==incident.node_id||run.status!=='completed'||run.started_at<incident.created_at)throw new Error('A completed retry after this incident is required');
   Object.assign(incident,{status:'resolved',resolved_by:actor,resolved_at:stamp(),retry_run_id,evidence,...(experience_id?{experience_id}:{})});return {id,status:'resolved',retry_run_id};
  });
 }
 async recover(){return this.store.mutate(db=>{
  db.incidents??=[];for(const run of db.runs??[])if(run.source===this.source&&run.status==='running'){
   run.status='interrupted';run.finished_at=stamp();
   if(db.incidents.some(e=>e.run_id===run.id))continue;
   db.incidents.push({id:randomUUID(),type:'execution_exception',category:'interrupted',status:'unresolved',node_id:run.node_id,manager_id:run.manager_id,creator_node_id:run.creator_node_id,role:run.role,toolboxes:run.toolboxes,session_id:run.session_id,run_id:run.id,source:this.source,version:this.version,message:'上次执行中断，结果未确认',created_at:stamp()});
  }
 })}
}
export class RuntimeDiagnostics {
 constructor(store,reports,on=(ac,event,fn)=>ac.on(event,fn)){this.on=on;this.store=store;this.reports=reports;this.states=new WeakMap()}
 attach(ac,agent,meta){
  const state={agent,meta,run:null,last_failure:null,failed:false,startIndex:0};this.states.set(ac,state);
  this.on(ac,'tools/result',async(exec,result)=>{if(exec.agent&&exec.agent!==agent)return;if(!isPermissionDenied(result)&&(result.isError||failureStatuses.has(result.value?.status)||(typeof result.value?.exitCode==='number'&&result.value.exitCode!==0)||(typeof result.value?.exit_code==='number'&&result.value.exit_code!==0)))state.last_failure={tool:exec.name,call_id:exec.callId??null,error:briefError(result.isError?result.content?.filter(x=>x.type==='text').map(x=>x.text).join('\n'):JSON.stringify(result.value)),time:stamp()};await this.reports?.tool(ac,exec,result)});
  this.on(ac,'agent/pre-step',async(_p,next)=>{if(!_p.agent||_p.agent===agent)await this.start(ac);return next()});
  this.on(ac,'agent/error',async payload=>{if(payload.agent&&payload.agent!==agent)return;state.failed=true;await this.exception(ac,payload.error??'agent error','agent_error')});
 }
 metadata(ac){const s=this.states.get(ac);return s?{...(typeof s.meta==='function'?s.meta():s.meta),session_id:s.agent.id}:null}
 async start(ac){const s=this.states.get(ac);if(!s||s.run)return;s.failed=false;s.last_failure=null;s.last_completed=null;const messages=s.agent.session.deriveMessages();s.startIndex=messages.length;s.run=await this.store.start(this.metadata(ac));await this.reports?.startRun(ac,this.metadata(ac),s.run.id,messages.filter(m=>m.role==='user').at(-1)?.content?.filter(c=>c.type==='text').map(c=>c.text).join('\n'));return s.run}
 messages(ac){const s=this.states.get(ac);return s?s.agent.session.deriveMessages().slice(s.startIndex):[]}
 report(ac){return this.messages(ac).filter(m=>m.role==='assistant').at(-1)?.content?.filter(c=>c.type==='text').map(c=>c.text).join('\n')??''}
 failure(ac,tool,error){const s=this.states.get(ac);if(s)s.last_failure={tool,error:briefError(error),time:stamp()}}
 async blocked(ac,report){const s=this.states.get(ac);const run=s?.run;if(s){s.failed=true;s.run=null}try{return await this.store.record({...this.metadata(ac),type:'blocked',feedback_id:report.id,manager_id:report.manager_id,creator_node_id:report.creator_node_id,category:report.category,message:report.message,run_id:run?.id??null,last_failure:s?.last_failure??null})}finally{await this.store.finish(run?.id,'blocked',report.message);await this.reports?.finish(ac,'blocked',null,report.message,this.messages(ac))}}
 async exception(ac,error,category='execution_error'){const s=this.states.get(ac);if(!s)return;const run=s.run;s.failed=true;s.run=null;if(run){try{await this.store.record({...this.metadata(ac),type:'execution_exception',category,message:briefError(error),run_id:run.id,last_failure:s.last_failure})}finally{await this.store.finish(run.id,'failed',error);await this.reports?.finish(ac,'failed',null,error,this.messages(ac))}}}
 lastCompleted(ac){return this.states.get(ac)?.last_completed}
 async completed(ac,summary){const s=this.states.get(ac);if(!s||s.failed)return;const run=s.run;s.run=null;const report=this.report(ac);await this.store.finish(run?.id,'completed',report||summary||'委托正常结束，无新增阻塞');await this.reports?.finish(ac,'completed',report,null,this.messages(ac));s.last_completed=run?.id??s.last_completed;return s.last_completed}
}
