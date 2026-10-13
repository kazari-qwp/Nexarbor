import {isPermissionDenied} from '../../../adapters/harness/framework/tool-permissions.js';
import {randomUUID} from 'node:crypto';
import {briefError} from '../../tools/execution_records/store.js';
export const TEMPORARY_PROBLEM_TOOLS=new Set(['experience_query','experience_submit','incident_query','incident_resolve','datanet_feedback','problem_attempt','problem_resolved','problem_defer']);
const channelTools=new Set(['handle_problem',...TEMPORARY_PROBLEM_TOOLS]);
const communication=name=>name==='datanet_send_message'||name?.startsWith('datanet_reply_');
const inspection=new Set(['read','glob','grep','node_read','node_list','node_tools','network_structure','datanet_recovery_status','experience_review','datanet_agent_capabilities','datanet_presets']);
const now=()=>new Date().toISOString();
const nonempty=(value,name,max=1000)=>{if(typeof value!=='string'||!value.trim()||value.length>max)throw new Error(`Invalid ${name}`);return value.trim()};
function successful(result){const value=result?.value;if(result?.isError)return false;if(value?.status&&!['ok','success','completed'].includes(value.status))return false;for(const k of ['exitCode','exit_code'])if(typeof value?.[k]==='number'&&value[k]!==0)return false;return true}
function recordUses(db, snapshot, resolved){
 db.experience_uses??=[];
 for(const a of new Map(snapshot.attempts.filter(a=>a.experience_id).map(a=>[a.experience_id,a])).values()){
  if(db.experience_uses.some(u=>u.problem_id===snapshot.id&&u.experience_id===a.experience_id))continue;
  const outcome=resolved&&a===snapshot.attempts.at(-1)?'success':'failure';
  db.experience_uses.push({problem_id:snapshot.id,experience_id:a.experience_id,node_id:snapshot.node_id,source:snapshot.source,session_id:snapshot.session_id,outcome,evidence:outcome==='success'?snapshot.evidence:'方案未解决此问题',verification:a.successes,time:now()});
  const entry=db.entries.find(e=>e.id===a.experience_id);if(entry){const uses=db.experience_uses.filter(u=>u.experience_id===entry.id);entry.success_count=uses.filter(u=>u.outcome==='success').length;entry.failure_count=uses.filter(u=>u.outcome==='failure').length;entry.promotion_candidate=entry.status==='verified'&&!entry.core&&entry.success_count>=5;}
 }
}
export class ProblemChannel {
 constructor(store,source,guide){this.store=store;this.source=source;this.guide=guide;this.states=new WeakMap();this.deferred=new Map()}
 bind(ac,metadata,allowSelfRepair){if(!this.states.has(ac))this.states.set(ac,{metadata,allowSelfRepair,problem:null});else this.states.get(ac).allowSelfRepair=allowSelfRepair}
 state(ac){const s=this.states.get(ac);return s?.problem?.status==='active'?s:null}
 async save(s){const copy=structuredClone(s.problem);await this.store.mutate(db=>{db.problems??=[];const i=db.problems.findIndex(x=>x.id===copy.id);if(i<0)db.problems.push(copy);else db.problems[i]=copy})}
 async recover(){await this.store.mutate(db=>{for(const problem of db.problems??[])if(problem.source===this.source){if(problem.status==='active'){problem.status='interrupted';problem.finished_at=now()}if(problem.status==='deferred')this.deferred.set(problem.id,structuredClone(problem))}})}
 async enter(ac,summary,{origin='self',origin_node_id,problem_id,max_attempts=3}={}){
  const s=this.states.get(ac);if(!s)throw new Error('Problem channel is not mounted');
  if(!Number.isInteger(max_attempts)||max_attempts<1||max_attempts>3)throw new Error('max_attempts must be an integer from 1 to 3');
  if(this.state(ac)){const lowered=Math.min(s.problem.max_attempts??3,max_attempts);if(lowered!==(s.problem.max_attempts??3)){s.problem.max_attempts=lowered;await this.save(s)}if(problem_id&&problem_id!==s.problem.id)throw new Error('Finish the current problem before opening another');return this.info(ac)}
  summary=nonempty(summary,'problem',240);
  if(!['self','subordinate','dependency'].includes(origin))throw new Error('Invalid problem origin');
  const metadata=s.metadata();
  if(origin==='self'){if(origin_node_id&&origin_node_id!==metadata.node_id)throw new Error('Self problem must belong to the current node');origin_node_id=metadata.node_id}
  else if(origin==='subordinate')origin_node_id=nonempty(origin_node_id,'origin_node_id',240);
  else origin_node_id=origin_node_id===undefined?null:nonempty(origin_node_id,'origin_node_id',240);
  const records=(await this.store.read()).problems??[];
  const existing=problem_id?records.find(x=>x.id===problem_id):records.findLast(x=>x.source===this.source&&x.node_id===metadata.node_id&&['deferred','interrupted','reported'].includes(x.status)&&x.summary===summary&&x.origin===origin&&x.origin_node_id===origin_node_id);
  if(problem_id&&(!existing||existing.source!==this.source||existing.node_id!==metadata.node_id||!['deferred','interrupted','reported'].includes(existing.status)))throw new Error('Only this node can reopen its unresolved problem');
  const previous=s.problem;
  s.problem=existing?{...structuredClone(existing),max_attempts:Math.min(existing.max_attempts??3,max_attempts),status:'active',stage:'lookup',queried:false,reopened_at:now(),finished_at:null}:{id:randomUUID(),source:this.source,...metadata,summary,origin,origin_node_id,max_attempts,status:'active',stage:'lookup',created_at:now(),queried:false,experience_ids:[],attempts:[],candidate_ids:[]};
  try{await this.save(s)}catch(error){s.problem=previous;throw error}
  this.deferred.delete(s.problem.id);return this.info(ac)
 }
 info(ac){const s=this.state(ac);if(!s)return {active:false};return {problem_id:s.problem.id,origin:s.problem.origin??'self',origin_node_id:s.problem.origin_node_id??(s.problem.origin==='dependency'?null:s.problem.node_id),stage:s.problem.stage,attempt_count:s.problem.attempts.length,max_attempts:s.problem.max_attempts??3,remaining_attempts:Math.max(0,(s.problem.max_attempts??3)-s.problem.attempts.length),allow_self_repair:s.allowSelfRepair}}
 async defer(ac,{reason,impact,continuation}){
  const s=this.state(ac);if(!s)throw new Error('Enter handle_problem first');
  const disposition={reason:nonempty(reason,'reason'),impact:nonempty(impact,'impact'),continuation:nonempty(continuation,'continuation'),time:now()};
  const snapshot=structuredClone(s.problem),last=snapshot.attempts.at(-1);
  if(last&&!last.finished_at){last.outcome='unresolved';last.finished_at=disposition.time}
  snapshot.status='deferred';snapshot.finished_at=disposition.time;snapshot.dispositions??=[];snapshot.dispositions.push(disposition);
  await this.store.mutate(db=>{const i=(db.problems??[]).findIndex(x=>x.id===snapshot.id);if(i<0||db.problems[i].status!=='active')throw new Error('Problem has already finished');db.problems[i]=snapshot});
  s.problem=snapshot;this.deferred.set(snapshot.id,snapshot);
  return {problem_id:snapshot.id,status:'deferred',resolved:false,attempt_count:snapshot.attempts.length,...disposition,next:'继续当前委托，正常汇报必须保留未解决问题和影响；继续排障时复用 problem_id，不得重置尝试记录。'}
 }
 async queried(ac,entries){const s=this.state(ac);if(!s)throw new Error('Enter handle_problem first');s.problem.queried=true;s.problem.experience_ids=[...new Set([...s.problem.experience_ids,...entries.map(x=>x.id)])];await this.save(s)}
 guard(ac,exec){const own=this.states.get(ac);if(exec.agent&&exec.agent.id!==own?.metadata().session_id)return;const s=this.state(ac);if(TEMPORARY_PROBLEM_TOOLS.has(exec.name)&&!s)return 'Enter handle_problem first';if(!s)return;
  if(communication(exec.name)||channelTools.has(exec.name)||inspection.has(exec.name)||exec.name?.endsWith('_channel'))return;
  if(exec.name==='datanet_skill'&&['list','read'].includes(exec.arguments?.action))return;
  if(s.problem.stage==='lookup'||s.problem.stage==='attempt_failed')return 'Query experience, then call problem_attempt before attempting a repair; or defer the unresolved problem if the task can continue, or report a task blocker';
 }
 assert(ac,exec){const reason=this.guard(ac,exec);if(reason)throw new Error(reason)}
 async attempt(ac,experienceId){const s=this.state(ac);if(!s?.problem.queried)throw new Error('Query experience before attempting repair');
  if(s.problem.attempts.length>=(s.problem.max_attempts??3))throw new Error('RECOVERY_LIMIT_REACHED: no further attempts; defer with task impact or report an actual task blocker');
  if(experienceId&&!s.problem.experience_ids.includes(experienceId))throw new Error('Experience must have been returned by experience_query for this problem');
  if(!experienceId&&!s.allowSelfRepair)throw new Error('Self repair is not authorized; try an applicable experience or report the blocker');
  if(experienceId){const entries=await this.store.query({ids:[experienceId],status:'all'});if(!entries.length)throw new Error('Experience is no longer available')}
  const previous=s.problem.attempts.at(-1);if(previous&&!previous.finished_at){previous.outcome='abandoned';previous.finished_at=now()}
  const attempt={id:randomUUID(),mode:experienceId?'experience':'self',experience_id:experienceId??null,started_at:now(),successes:[],failures:[]};s.problem.attempts.push(attempt);s.problem.stage='trying';await this.save(s);
  return {problem_id:s.problem.id,attempt_id:attempt.id,attempt_count:s.problem.attempts.length,max_attempts:s.problem.max_attempts??3,mode:attempt.mode,next:'按现有工具权限验证方案。成功后记录依据；自行修复成功须先提交候选经验，失败可报告阻塞。'}
 }
 // Share a persistent recovery budget for one reporting target across creators,
 // generic delegation, configuration changes, session restarts and feedback IDs.
 async reserveRecovery(ac,target,feedbackId,action){
  if(!feedbackId)return null;
  const limit=this.state(ac)?.problem.max_attempts??3;
  return this.store.mutate(db=>{
   db.recovery_budgets??=[];
   let budget=db.recovery_budgets.findLast(x=>x.source===this.source&&x.target===target&&x.status==='unresolved');
   if(!budget){
    if(db.recovery_budgets.some(x=>x.source===this.source&&x.target===target&&x.status==='resolved'&&x.feedback_ids.includes(feedbackId)))return null;
    budget={id:randomUUID(),source:this.source,target,status:'unresolved',max_attempts:limit,feedback_ids:[],attempts:[],created_at:now()};db.recovery_budgets.push(budget);
   }
   budget.max_attempts=Math.min(budget.max_attempts??3,limit);
   if(!budget.feedback_ids.includes(feedbackId))budget.feedback_ids.push(feedbackId);
   let attempt=budget.attempts.at(-1);
   // A cycle can contain one toolbox update, one prompt update and one restart,
   // then one execution. Repeating any configuration step starts another cycle.
   if(!attempt||attempt.finished_at||attempt.actions.some(x=>x.action===action)){
    if(budget.attempts.length>=budget.max_attempts)throw new Error('RECOVERY_LIMIT_REACHED: target '+target+' has exhausted '+budget.max_attempts+' recovery attempts; return existing failure evidence instead of changing configuration or retrying');
    if(attempt&&!attempt.finished_at){attempt.finished_at=now();attempt.outcome='superseded'}
    attempt={id:randomUUID(),started_at:now(),actions:[]};budget.attempts.push(attempt);
   }
   attempt.actions.push({action,actor:this.states.get(ac)?.metadata().node_id??null,time:now()});
   if(action==='execute'){attempt.finished_at=now();attempt.outcome='execution_requested'}
   return {recovery_id:budget.id,attempt_id:attempt.id,attempt_count:budget.attempts.length,max_attempts:budget.max_attempts};
  });
 }
 async recoveryResolved(target,feedbackId){
  await this.store.mutate(db=>{for(const b of db.recovery_budgets??[])if(b.source===this.source&&b.target===target&&b.status==='unresolved'&&b.feedback_ids.at(-1)===feedbackId){b.status='resolved';b.finished_at=now()}})
 }
 async recoveryStatus(){return ((await this.store.read()).recovery_budgets??[]).filter(x=>x.source===this.source).map(x=>({target:x.target,status:x.status,attempt_count:x.attempts.length,max_attempts:x.max_attempts??3,remaining_attempts:Math.max(0,(x.max_attempts??3)-x.attempts.length)}))}
 async outcome(ac,exec,result){if(isPermissionDenied(result))return;const s=this.state(ac);if(exec.agent&&exec.agent.id!==s?.metadata().session_id)return;if(!s||s.problem.stage!=='trying'||(communication(exec.name)||channelTools.has(exec.name)||exec.name?.endsWith('_channel')))return;
  const attempt=s.problem.attempts.at(-1);if(!attempt)return;
  if(exec.callId&&[...attempt.successes,...attempt.failures].some(e=>e.call_id===exec.callId))return;
  const evidence={tool:exec.name,call_id:exec.callId??randomUUID(),time:now()};
  if(successful(result)){attempt.successes.push(evidence);attempt.successes=attempt.successes.slice(-8)}else{attempt.failures.push({...evidence,error:briefError(result?.isError?result.content?.filter(x=>x.type==='text').map(x=>x.text).join('\n'):JSON.stringify(result?.value))});attempt.outcome='failed';attempt.finished_at=now();s.problem.stage='attempt_failed'}
  await this.save(s)
 }
 canSubmit(ac){const s=this.state(ac),attempt=s?.problem.attempts.at(-1);if(!s||!attempt||attempt.mode!=='self'||!s.allowSelfRepair||s.problem.stage!=='trying'||!attempt.successes.length)throw new Error('Candidate submission requires authorized self repair and an observed successful verification')}
 async submitted(ac,id){const s=this.state(ac);s.problem.candidate_ids.push(id);s.problem.attempts.at(-1).candidate_ids??=[];s.problem.attempts.at(-1).candidate_ids.push(id);await this.save(s)}
 canReport(ac,taskBlocker){nonempty(taskBlocker,'task_blocker');const s=this.state(ac);if(!s?.problem.queried)throw new Error('Query experience before reporting a blocker');if(s.allowSelfRepair&&s.problem.attempts.length<(s.problem.max_attempts??3)&&!s.problem.attempts.some(a=>a.mode==='self'))throw new Error('Attempt authorized self repair before reporting; use problem_attempt without experience_id')}
 async report(ac,feedbackId,taskBlocker){const s=this.state(ac);if(!s)return;s.problem.task_blocker=nonempty(taskBlocker,'task_blocker');s.problem.status='reported';s.problem.feedback_id=feedbackId;s.problem.finished_at=now();const snapshot=structuredClone(s.problem);await this.store.mutate(db=>{const i=db.problems.findIndex(p=>p.id===snapshot.id);db.problems[i]=snapshot;recordUses(db,snapshot,false)})}
 async resolve(ac,evidence){evidence=nonempty(evidence,'evidence');const s=this.state(ac),attempt=s?.problem.attempts.at(-1);
  if(!s||!attempt||s.problem.stage!=='trying'||!attempt.successes.length)throw new Error('A successful observed verification after problem_attempt is required');
  if(attempt.mode==='self'&&!attempt.candidate_ids?.length)throw new Error('Submit the verified solution as candidate experience before finishing self repair');
  const snapshot=structuredClone(s.problem);const last=snapshot.attempts.at(-1);last.outcome='resolved';last.finished_at=now();snapshot.status='resolved';snapshot.evidence=evidence;snapshot.finished_at=now();
  const result=await this.store.mutate(db=>{
   db.problems??=[];const i=db.problems.findIndex(p=>p.id===snapshot.id);if(i<0||db.problems[i].status!=='active')throw new Error('Problem has already finished');db.problems[i]=snapshot;
   recordUses(db,snapshot,true);
   return {problem_id:snapshot.id,status:'resolved',experience_id:attempt.experience_id,candidate_ids:snapshot.candidate_ids,promotion_requires_review:true};
  });s.problem=snapshot;return result
 }
 async abandon(ac,reason){const s=this.state(ac);if(s){s.problem.status='interrupted';s.problem.finished_at=now();s.problem.interruption=briefError(reason);await this.save(s)}}
 render(ac){const own=this.states.get(ac),s=this.state(ac);const pending=[...this.deferred.values()].filter(x=>x.node_id===own?.metadata().node_id).map(x=>({problem_id:x.id,problem:x.summary,origin:x.origin??'self',origin_node_id:x.origin_node_id??null,attempt_count:x.attempts.length,...x.dispositions.at(-1)}));
  return (s?`当前问题：${s.problem.summary}\n归属：${s.problem.origin??'self'}；来源节点：${s.problem.origin_node_id??'未指定'}；problem_id：${s.problem.id}；累计尝试：${s.problem.attempts.length}/${s.problem.max_attempts??3}。达到上限后不得再次修复或执行，选择未解决退出或自身任务阻塞上报。\n阶段：${s.problem.stage}；自主排障授权：${s.allowSelfRepair?'允许（仅原有工具权限内）':'不允许'}。`:'')+(pending.length?'\n未解决但已结束排障的问题（不是成功；正常汇报须保留与当前任务有关的失败及影响，重新排障须复用 problem_id）：\n'+JSON.stringify(pending):'')
 }
}
