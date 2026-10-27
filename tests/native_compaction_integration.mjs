// Production NativeRunner + installed DSH compaction + durable JSONL. HTTP replies are local fixtures.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import zlib from 'node:zlib';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import readAgentDefaults from '../adapt/harness/framework/agent-defaults.cjs';

const directory=path.resolve(process.argv[2]);await fs.mkdir(path.join(directory,'temp'),{recursive:true});
const limits=readAgentDefaults(),bindings={},calls=[];let latest=null,native,overflowInjected=false,cancelArmed=false,cancelReady;
const cancellationSummary=new Promise(resolve=>{cancelReady=resolve;});
const content=m=>typeof m?.content==='string'?m.content:(m?.content??[]).map(b=>b.text??'').join('\n');
const server=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const part of req)raw+=part;const body=JSON.parse(raw),last=content(body.messages.at(-1));
  const summary=last.includes('checkpoint')&&last.includes('Rules:');
  const cancelOverflow=!summary&&last==='CANCEL_OVERFLOW_CHECK'&&!cancelArmed;
  const overflow=cancelOverflow||!summary&&last==='OVERFLOW_CHECK'&&!overflowInjected;
  const entry={summary,overflow,max_tokens:body.max_tokens,input_chars:JSON.stringify(body.messages).length,reasoning_effort:body.reasoning_effort};calls.push(entry);
  assert.ok(calls.length<20,'No unbounded recovery');
  if(summary&&cancelArmed){cancelReady();return;}
  if(overflow){if(cancelOverflow)cancelArmed=true;else overflowInjected=true;res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'maximum context length exceeded',type:'invalid_request_error',code:'context_length_exceeded'}}));return;}
  const text=summary?'DSH_FIXTURE_CHECKPOINT: preserve durable session identity and continue the current task.':'NATIVE_COMPACTION_OK';
  const prompt=summary?100:last.startsWith('PRESSURE_SEED_1')?300000:last.startsWith('PRESSURE_SEED_2')?500000:100;
  const base={id:'compaction-'+calls.length,object:'chat.completion.chunk',created:1,model:'deepseek-flash'};
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{role:'assistant',content:text},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({...base,choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:prompt,completion_tokens:12,total_tokens:prompt+12}})+'\n\n');res.end('data: [DONE]\n\n');
 }catch(error){res.writeHead(500);res.end(String(error));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+server.address().port+'/v1',api_key:'local-fixture',signature:'native-compaction-fixture',model:{model:'deepseek-flash',reasoningEfforts:{off:'none',low:'low',high:'high',max:'max'},compat:{thinkingFormat:'deepseek',supportsReasoningEffort:true,requiresReasoningContentOnAssistantMessages:true,maxTokensField:'max_tokens'},maxTokens:limits.max_tokens,contextWindow:limits.context_window,reasoningEffort:'low'}};
async function callback(method,p){
 if(method==='executor_prepare')return {tools:[],context:[],inputs:[],tail:[],retained_tools:[]};
 if(method==='executor_prune')return [];
 if(method==='executor_bind'){bindings[p.actor]={...p,name:p.actor};return {ok:true};}
 if(method==='persistence_info')return {commit_id:0,bindings:Object.fromEntries(Object.entries(bindings).map(([a,b])=>[a,b.session_id])),pending:[]};
 if(method==='persistence_latest_point')return latest;
 if(method==='persistence_checkpoint')return latest={...p,id:'fixture-point'};
 throw Error('Unexpected production callback '+method);
}
function start(){native=new NativeRunner(directory,callback,{noCredentials:true,modelResolver:async()=>profile});}
async function run(actor,message){const result=await native.request('agent-run',{...bindings[actor],actor,name:actor,message});assert.equal(result.status,'completed',result.error);return result;}
async function events(actor){
 const cursors=await native.request('agent-context-capture',{bindings:{[actor]:bindings[actor].session_id},requireIdle:true});
 const cursor=cursors[actor],raw=await fs.readFile(cursor.log.path),chunks=[];let offset=0;
 while(offset<raw.length){const part=zlib.zstdDecompressSync(raw.subarray(offset),{info:true});assert.ok(part.engine.bytesWritten);chunks.push(part.buffer);offset+=part.engine.bytesWritten;}
 const rows=Buffer.concat(chunks).toString('utf8').trim().split('\n').map(s=>JSON.parse(s));
 return {cursor,rows:rows.filter(r=>Number.isInteger(r.seq))};
}
try{
 start();
 await run('pressure','PRESSURE_SEED_1 '+('history-one '.repeat(50000)));
 await run('pressure','PRESSURE_SEED_2 '+('history-two '.repeat(50000)));
 const before=await events('pressure');
 const completed=await run('pressure','PRESSURE_CHECK');assert.equal(completed.output,'NATIVE_COMPACTION_OK');
 const compacted=await events('pressure'),summaries=compacted.rows.filter(e=>e.type==='compaction/summary');
 assert.ok(summaries.length,'Native pressure compaction must run');
 assert.ok(compacted.rows.some(e=>e.type==='compaction/end'&&!e.data.error));
 assert.equal(compacted.rows.findLast(e=>e.type==='request/context').data.contextWindow,limits.context_window);
 assert.ok(compacted.rows.length>before.rows.length,'Raw history is retained');
 const read=await native.request('agent-read',{...bindings.pressure,actor:'pressure'});
 assert.ok(JSON.stringify(read.messages).includes('DSH_FIXTURE_CHECKPOINT'));
 assert.ok(JSON.stringify(read.messages).length<1200000,'Derived messages use the replacement surface');
 const pressureSession=bindings.pressure.session_id;
 await native.close();start();
 const reopened=await native.request('agent-read',{...bindings.pressure,actor:'pressure'});
 assert.equal(reopened.session_id,pressureSession);assert.deepEqual(reopened.messages,read.messages);
 assert.equal((await run('pressure','CONTINUE_AFTER_REOPEN')).session_id,pressureSession);
 await run('overflow','OVERFLOW_SEED '+('balanced-history '.repeat(12000)));
 const recovered=await run('overflow','OVERFLOW_CHECK');assert.equal(recovered.output,'NATIVE_COMPACTION_OK');
 const overflow=await events('overflow');assert.ok(overflowInjected);
 assert.ok(overflow.rows.some(e=>e.type==='compaction/summary'),'Native overflow handler must compact before retry');
 assert.equal(overflow.rows.filter(e=>e.type==='turn/end'&&e.data.reason.kind==='completed').length,2);
 assert.equal(calls.filter(c=>c.overflow).length,1);
 for(const call of calls.filter(c=>!c.summary)){assert.equal(call.max_tokens,limits.max_tokens);assert.equal(call.reasoning_effort,'low');}
 await run('cancel','CANCEL_SEED '+('cancel-history '.repeat(12000)));
 const pending=native.request('agent-run',{...bindings.cancel,actor:'cancel',message:'CANCEL_OVERFLOW_CHECK'});
 await cancellationSummary;await native.request('agent-cancel',{actor:'cancel'});
 const cancelled=await pending;assert.equal(cancelled.status,'failed');
 const cancelledLog=await events('cancel');
 assert.ok(cancelledLog.rows.some(e=>e.type==='compaction/end'&&e.data.error),'Cancellation closes the native compaction bracket');
 const attempts=calls.length;cancelArmed=false;await run('cancel','CONTINUE_AFTER_CANCEL');assert.equal(calls.length,attempts+1);
 const evidence={passed:true,cancelled_compaction_closed:true,paid_api_calls:0,actual_harness_sdk:true,limits,pressure_summaries:summaries.length,overflow_recovered:true,same_session_reopened:true,raw_log_retained:true,calls};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{await native?.close();await new Promise(resolve=>server.close(resolve));}
