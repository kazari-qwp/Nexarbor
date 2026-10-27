// Read only the seven active native branches, not parent/abandoned copies.
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const directory=path.resolve(process.argv[2]),state=JSON.parse(fs.readFileSync(path.join(directory,'final-state.json'),'utf8')),rows=[];
for(const [actor,binding]of Object.entries(state.agents)){
 const raw=fs.readFileSync(binding.context_cursor.log.path),chunks=[];let offset=0;
 while(offset<raw.length){const part=zlib.zstdDecompressSync(raw.subarray(offset),{info:true});assert.ok(part.engine.bytesWritten);chunks.push(part.buffer);offset+=part.engine.bytesWritten;}
 const events=Buffer.concat(chunks).toString('utf8').trim().split('\n').map(JSON.parse).filter(e=>Number.isInteger(e.seq));
 const usage={input:0,output:0,total:0,cached:0},formal=new Set();let assistants=0,completed=0;
 for(const e of events){
  if(e.type==='turn/end'){assert.equal(e.data.reason.kind,'completed');completed++;}
  if(e.type==='user/message'&&e.data.source?.kind==='nexarbor-input'){
   const id=e.data.source.source+'\0'+e.data.source.event;assert.ok(!formal.has(id),'Repeated formal input '+actor);formal.add(id);
  }
  if(e.type==='assistant/message'&&e.data.usage){const u=e.data.usage;assistants++;usage.input+=(u.inputTokens??0)+(u.cacheReadTokens??0)+(u.cacheWriteTokens??0);usage.cached+=u.cacheReadTokens??0;usage.output+=u.outputTokens??0;usage.total+=u.totalTokens??0;}
 }
 rows.push({actor,session_id:binding.session_id,completed_turns:completed,assistant_responses:assistants,formal_inputs:formal.size,usage});
}
const usage=rows.reduce((sum,row)=>{for(const k in sum)sum[k]+=row.usage[k];return sum;},{input:0,output:0,total:0,cached:0});assert.equal(usage.input+usage.output,usage.total);
const report={passed:true,paid_api_calls:0,active_native_branches:rows.length,unique_formal_inputs:true,usage,rows};fs.writeFileSync(path.join(directory,'native-session-audit.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
