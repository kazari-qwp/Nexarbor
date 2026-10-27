const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const crypto=require('node:crypto');
function files(root){return fs.readdirSync(root,{withFileTypes:true}).flatMap(item=>item.isDirectory()?files(path.join(root,item.name)):[path.join(root,item.name)]);}
function events(file){const input=fs.readFileSync(file),parts=[];let offset=0;while(offset<input.length){const out=zlib.zstdDecompressSync(input.subarray(offset),{info:true});parts.push(out.buffer);if(!out.engine.bytesWritten)throw Error('Zstd decoder made no progress');offset+=out.engine.bytesWritten;}return Buffer.concat(parts).toString('utf8').split('\n').filter(Boolean).map(line=>JSON.parse(line));}
function summarize(list){return {responses:list.length,output_tokens:list.reduce((s,x)=>s+x.output_tokens,0),text_chars:list.reduce((s,x)=>s+x.text_chars,0),thinking_chars:list.reduce((s,x)=>s+x.thinking_chars,0),tool_argument_chars:list.reduce((s,x)=>s+x.tool_argument_chars,0),tool_calls:list.reduce((s,x)=>s+x.tools.length,0),tool_responses:list.filter(x=>x.tools.length).length,plain_responses:list.filter(x=>!x.tools.length).length,errors:list.reduce((s,x)=>s+x.tool_results.filter(r=>r.error).length,0)};}
for(const directory of process.argv.slice(2)){
 const verification=JSON.parse(fs.readFileSync(path.join(directory,'verification.json'),'utf8'));
 const waves=(verification.cycles??verification.turns).flatMap(x=>x.report?.reports??[]);
 const responses=[],actors=[],toolResults=[],shapes=[],eventTypes={},safeSettings=[],toolDefinitions={},turns=[],userSources={};
 for(const file of files(path.join(directory,'native-logs')).filter(x=>x.endsWith('.jsonl.zstd'))){
  const all=events(file),header=all[0];
  const titles=all.filter(e=>e.type==='session/title');
  const actor=titles.at(-1)?.data?.title??path.basename(path.dirname(file));
  actors.push({actor,session:header.id,header_keys:Object.keys(header)});
  for(const event of all){
   eventTypes[event.type]=(eventTypes[event.type]??0)+1;
   function settings(value,trail=[]){if(!value||typeof value!=='object')return;for(const [key,item] of Object.entries(value)){if(/effort|thinking|reasoning/i.test(key)&&((typeof item==='string'&&item.length<40)||typeof item==='boolean'||typeof item==='number'))safeSettings.push({actor,event:event.type,path:[...trail,key],value:item});else if(typeof item==='object'&&!['message','content','replayState','stream'].includes(key))settings(item,[...trail,key]);}}
   if(event.type!=='assistant/message')settings(event.data);
   const cycle=waves.findIndex(w=>event.time>=w.started_at*1000&&event.time<=w.finished_at*1000)+1;
   if(event.type==='request/header'){
    const header=event.data.header??{};
    for(const tool of Array.isArray(header.tools)?header.tools:[]){const spec=tool.function??tool;if(spec.name)toolDefinitions[spec.name]={name:spec.name,description:spec.description??''};}
   }
   if(!cycle)continue;
   if(event.type==='turn/start')turns.push({actor,cycle,seq:event.seq,time:event.time,keys:Object.keys(event.data??{})});
   if(event.type==='user/message'){const source=event.data.message?.source??{};const id=cycle+':'+(source.kind??'unknown');userSources[id]=(userSources[id]??0)+1;}
   if(event.type==='tool/result'){
    const message=event.data?.message??{};
    const result={actor,cycle,time:event.time,call_id:message.toolCallId,error:!!message.isError,blocks:(message.content??[]).map(block=>({type:block.type,chars:typeof block.text==='string'?block.text.length:0,...(message.isError&&block.type==='text'?{error_preview:block.text.slice(0,240)}:{})}))};
    toolResults.push(result);continue;
   }
   if(event.type!=='assistant/message'||!event.data?.usage)continue;
   const message=event.data.message;
   const blocks=message.content??[];
   const tools=blocks.filter(b=>b.type==='tool-call').map(b=>({name:b.name,id:b.id,argument_keys:Object.keys(b.arguments??b.input??{}),args:b.arguments??b.input??null}));
   const text=blocks.filter(b=>b.type==='text').map(b=>b.text??'').join('\n');
   const thoughts=blocks.filter(b=>['thinking','reasoning'].includes(b.type));
   const entry={actor,session:header.id,cycle,time:event.time,seq:event.seq,turn:event.data.turn,step:event.data.step,output_tokens:event.data.usage.outputTokens??0,usage:event.data.usage,
    message_source_keys:Object.keys(message.source??{}),block_shapes:blocks.map(b=>({type:b.type,keys:Object.keys(b),chars:typeof b.text==='string'?b.text.length:0})),
    text_chars:text.length,thinking_chars:thoughts.reduce((s,b)=>s+(b.text??b.thinking??'').length,0),tool_argument_chars:tools.reduce((s,t)=>s+JSON.stringify(t.args).length,0),tools,text_preview:text.slice(0,220),tool_results:[]};
   responses.push(entry);
   if(shapes.length<3)shapes.push({type:event.type,data_keys:Object.keys(event.data),block_shapes:entry.block_shapes,source_keys:entry.message_source_keys,usage:entry.usage});
  }
 }
 const byCall=new Map(responses.flatMap(response=>response.tools.map(tool=>[tool.id,response])));
 for(const result of toolResults){const response=byCall.get(result.call_id);if(response)response.tool_results.push(result);}
 const grouped=key=>Object.fromEntries([...new Set(responses.map(x=>x[key]))].map(value=>[value,summarize(responses.filter(x=>x[key]===value))]));
 const report={directory,actors,tool_definitions:toolDefinitions,turns,user_sources:userSources,event_types:eventTypes,safe_settings:safeSettings,summary:summarize(responses),by_actor:grouped('actor'),by_cycle:grouped('cycle'),shapes,responses,tool_results:toolResults};
 const name='town-output-'+crypto.createHash('sha256').update(directory).digest('hex').slice(0,12)+'.json';
 fs.writeFileSync(path.join(process.cwd(),'build',name),JSON.stringify(report,null,2));
 console.log(JSON.stringify({directory,output:name,summary:report.summary,actors,by_actor:report.by_actor,by_cycle:report.by_cycle,event_types:eventTypes,safe_settings:safeSettings.slice(0,12),shapes,tool_definition_samples:Object.values(toolDefinitions).slice(0,3),turns:turns.length,user_sources:userSources}));
}
