// 付费应用验收：只有组件、配置与通用宿主运行；不启动日常 Harness GUI。
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';
import {startStudioProfile} from '../adapters/harness/studio/host.mjs';
const root=path.resolve(import.meta.dirname,'..'),mode=process.argv[2]??'town',resumeOnly=!!process.argv[3],directory=resumeOnly?path.resolve(process.argv[3]):path.join(root,'build','native-'+mode+'-'+Date.now());
const profile=path.join(root,'configs',mode==='town'?'npc_town_v3':mode==='groups'?'fixed_groups_v3':'knowledge_v3','profile.json');
await fs.mkdir(path.join(directory,'studio'),{recursive:true});await fs.mkdir(path.join(directory,'temp'),{recursive:true});
await fs.writeFile(path.join(directory,'studio/harness-connection.json'),JSON.stringify({home:'E:/dsh/state',authority:'native-sdk'}));
await fs.writeFile(path.join(directory,'native-model.json'),JSON.stringify({max_requests:360,max_seconds:2400,model:{reasoningEffort:'low',maxTokens:10000}}));
let host;const evidence=resumeOnly?JSON.parse(await fs.readFile(path.join(directory,'run-evidence.json'),'utf8')):{mode,directory,started:Date.now(),turns:[],reopened:false};
const snapshot=async()=>{const state=await host.rpc('studio_state');await fs.writeFile(path.join(directory,'state-latest.json'),JSON.stringify(state,null,2));return state;};
const local=async(node,module,operation,args={})=>{const r=await host.rpc('module_access',{node,module,operation,arguments:args});assert.equal(r.status,'ok',JSON.stringify(r));return r.data;};
const run=async(actor,text)=>{const result=await host.rpc('executor_run',{actor,text});evidence.turns.push({actor,...result});await fs.writeFile(path.join(directory,'run-evidence.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({actor,status:result.status,steps:result.steps,requests:result.requests,output:result.output?.slice(0,160)}));return result;};
try{
 host=await startStudioProfile(profile,{directory});const initial=await snapshot();const valid=await host.rpc('studio_graph_validate',{document:initial.live.document});assert.equal(valid.valid,true,JSON.stringify(valid));
 if(!resumeOnly){if(mode==='town'){
  for(let cycle=1;cycle<=5;cycle++){
   const result=await host.rpc('studio_pulse',{pulse:'world/pulse',cycles:1,timeout_seconds:540});evidence.turns.push({cycle,report:result.report});await fs.writeFile(path.join(directory,'run-evidence.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({cycle,status:result.report.status,deliveries:result.report.reports?.[0]?.deliveries.map(d=>({node:d.node_id,status:d.status,error:d.error}))}));assert.equal(result.report.status,'completed',JSON.stringify(result.report));
  }
  const state=await snapshot();assert.equal(state.live.document.network.nodes.find(n=>n.node_id==='world/time').modules['clock.counter'].state.tick,5);
  await local('npc/sen','agents.context','remember',{text:'验收记忆：今天的木材交易经过真实工具完成，以账户记录为准。',key:'native-acceptance'});
 }else if(mode==='groups'){
  for(const actor of ['discuss_eng','discuss_pm','discuss_qa'])await run(actor,'请先阅读公共讨论板，针对“小团队应先做可验证原型还是完整规划”提出一条与你职责一致的建议，发到讨论板，再记住自己的关键观点，然后结束。不需要全网管理。');
  const board=await local('board_discuss','messages.box','read');assert.ok(board.messages.length>=3,JSON.stringify(board));
  await Promise.all(['collab_eng','collab_qa'].map(actor=>run(actor,'请查看任务板，挑一个尚未被认领的任务，先get再使用expected_revision提交认领，认领后把你计划的验收步骤发到公告箱；如果发现已被别人认领就选别的任务。只完成本轮认领和公告，然后结束。')));
  assert.ok((await local('board_notice','messages.box','read')).messages.length>=2);
 }else{
  await run('root','请归档一篇文档：id=acceptance，标题“组件笔记”，正文“节点锁让多个节点的内部修改一起提交”，标签[架构,锁]。然后用私人记忆记住“我正在维护组件资料库”，结束。');
  assert.ok((await local('knowledge','knowledge.collection','get',{id:'acceptance'})).document.text.includes('节点锁'));
 }}
 const before=await snapshot();await host.rpc('save',{full:true});await host.close();host=null;host=await startStudioProfile(profile,{directory});evidence.reopened=true;
 const after=await snapshot();for(const [id,s] of Object.entries(before.live.sessions))assert.equal(after.live.sessions[id]?.session_id,s.session_id);
 if(mode==='town'){
  assert.ok((await local('npc/sen','agents.context','recall',{query:'验收记忆'})).count===1);
  await run('npc/sen','请回忆我保存的“验收记忆”，并结合当前现场，用一句话说明你现在的位置和记忆内容；本轮不要移动或交易。');
 }else if(mode==='groups'){
  await run('discuss_eng','请回顾自己的私人记忆和公共讨论板，用两句话归纳刚才讨论的分歧，本轮只总结。');
 }else{
  await run('root','请先回忆你自己的资料库笔记，再检索标签为“锁”的文档，并读取acceptance，引用正文回答这篇笔记说了什么；本轮不改动资料。');
 }
 for(const id of Object.keys((await snapshot()).live.sessions)){
  const chat=await host.rpc('executor_read',{actor:id});await fs.writeFile(path.join(directory,'transcript-'+id.replaceAll('/','-')+'.json'),JSON.stringify(chat,null,2));
 }
 evidence.passed=true;evidence.finished=Date.now();await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({passed:true,mode,directory,reopened:true}));
}catch(error){evidence.passed=false;evidence.error=error.stack;await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.error(error);process.exitCode=1;}finally{if(host)await host.close();}
