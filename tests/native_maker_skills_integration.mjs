// Real DSH sessions and lazy maker Skills; model replies are a local HTTP fixture.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import {makerTools} from '../adapt/harness/studio/makers/tools.mjs';
import {ProjectObservations} from '../adapt/harness/studio/makers/project-observer.mjs';
import skill from '../adapt/harness/studio/makers/network-skill.cjs';
const directory=path.resolve(process.argv[2]);await fs.mkdir(path.join(directory,'temp'),{recursive:true});
const calls=[],counts=new Map(),receipts=[],sessions={};let native;
const project=path.resolve('resources/examples/npc-town');
const observations=new ProjectObservations({render(){throw Error('text fixture')}});
const text=message=>typeof message?.content==='string'?message.content:(message?.content??[]).map(block=>block.text??'').join('');
const server=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);
  const marker=text(body.messages.findLast(message=>message.role==='user'&&/MAKER_(network|module|resume)/.test(text(message)))).match(/MAKER_(network|module|resume)/)?.[1];
  assert.ok(marker);const count=counts.get(marker)??0;counts.set(marker,count+1);assert.ok(count<12);
  const names=body.tools.map(tool=>tool.function.name);calls.push({role:marker,step:count,tools:names});
  let operation;
  if(marker==='resume'){
   assert.ok(names.includes('view_network'));assert.ok(names.includes('list_files'));
   operation=count===0?['view_network',{project,image:false,types:['agent']}]:null;
  }else{
   const sequence=[['skill',{name:'nexarbor-basics'}],['read_skill_reference',{skill:'nexarbor-basics',file:'references/lessons/01-local.md',line_count:35}],['skill',{name:'inspect-network'}],['view_network',{project,image:false,types:['agent']}],['inspect_nodes',{nodes:['小砾'],section:'modules'}],['read_network_text',{nodes:['小砾']}],['skill',{name:marker==='network'?'make-network':'make-components'}]];
   if(count===0){assert.ok(names.includes('skill'));assert.ok(!names.includes('view_network'));assert.ok(!names.includes('list_files'));}
   if(count>=3)assert.ok(names.includes('view_network'));
   if(count===7)assert.ok(names.includes('list_files'));
   operation=sequence[count];
  }
  const delta=operation?{role:'assistant',tool_calls:[{index:0,id:'maker-'+calls.length,type:'function',function:{name:operation[0],arguments:JSON.stringify(operation[1])}}]}:{role:'assistant',content:'MAKER_SKILLS_OK'};
  const base={id:'maker-'+calls.length,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta,finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:operation?'tool_calls':'stop'}],usage:{prompt_tokens:12,completion_tokens:12,total_tokens:24}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end(error.stack);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture',signature:'maker-skills-local',model:{model:'deepseek-flash',reasoningEfforts:{off:'none',low:'low',high:'high',max:'max'},maxTokens:16000,contextWindow:600000,compat:{supportsDeveloperRole:false,maxTokensField:'max_tokens'}}};
const callback=async(method,args)=>{assert.equal(method,'maker-tool');const result=await observations.observe(args.task,args.tool,args.arguments);receipts.push({tool:args.tool,result});return result;};
const start=()=>native=new NativeRunner(directory,callback,{noCredentials:true,modelResolver:async()=>profile,script:fileURLToPath(new URL('../adapt/harness/studio/makers/worker.cjs',import.meta.url))});
try{
 start();
 for(const kind of ['network','module']){
  const created=await native.request('create',{task:kind,directory,name:kind,kind,instructions:skill.instructions(kind),tools:makerTools(kind,false,true)});sessions[kind]=created;
  const result=await native.request('run',{session_id:created.session_id,prompt:'MAKER_'+kind,timeout:86400});assert.equal(result.status,'completed',JSON.stringify(result.reason));
  assert.ok(JSON.stringify(result.messages).includes('MAKER_SKILLS_OK'));
 }
 assert.equal(receipts.filter(item=>item.tool==='view_network').length,2);
 for(const receipt of receipts.filter(item=>item.tool==='inspect_nodes'))assert.ok(receipt.result.nodes[0].modules.some(module=>module.id==='tool_discovery'));
 await native.close();start();
 const restored=await native.request('create',{task:'resumed',directory,name:'continued',kind:'network',instructions:skill.instructions('network'),tools:makerTools('network',false,true),resume_session:sessions.network.session_id,model_signature:sessions.network.model_signature});
 assert.equal(restored.session_id,sessions.network.session_id);
 const result=await native.request('run',{session_id:restored.session_id,prompt:'MAKER_resume',timeout:86400});assert.equal(result.status,'completed',JSON.stringify(result.reason));
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({status:'passed',paid_requests:0,requests:calls.length,sessions,calls,tools:receipts.map(item=>item.tool)},null,2));
 console.log(JSON.stringify({status:'passed',requests:calls.length,paid_requests:0,roles:['network','module'],cold_resume:true}));
}finally{await native?.close();server.close();}
