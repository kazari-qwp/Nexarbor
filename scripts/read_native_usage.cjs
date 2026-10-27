const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
function files(root){return fs.readdirSync(root,{withFileTypes:true}).flatMap(item=>item.isDirectory()?files(path.join(root,item.name)):[path.join(root,item.name)]);}
for(const directory of process.argv.slice(2)){
 const records=[];
 for(const file of files(path.join(directory,'native-logs')).filter(file=>file.endsWith('.jsonl.zstd'))){
  const compressed=fs.readFileSync(file),chunks=[];let offset=0;
  while(offset<compressed.length){const result=zlib.zstdDecompressSync(compressed.subarray(offset),{info:true});if(!result.engine.bytesWritten)throw Error('No Zstd frame progress');chunks.push(result.buffer);offset+=result.engine.bytesWritten;}
  const data=Buffer.concat(chunks).toString('utf8');
  const events=data.split('\n').filter(Boolean).map(line=>JSON.parse(line));
  const usage=[];function scan(value,trail=[]){if(!value||typeof value!=='object')return;for(const [key,item]of Object.entries(value)){if(key==='usage')usage.push({path:[...trail,key],usage:item});else scan(item,[...trail,key]);}}
  for(const event of events)if(event.type==='assistant/message'&&event.data?.usage)usage.push({type:event.type,seq:event.seq,time:event.time,usage:event.data.usage});

  records.push({session:path.basename(path.dirname(file)),events:events.length,usage_count:usage.length,usage_sample:usage.slice(0,1),usage});
 }
 const destination=path.join(process.cwd(),'build','native-usage-'+require('node:crypto').createHash('sha256').update(directory).digest('hex').slice(0,12)+'.json');
 fs.writeFileSync(destination,JSON.stringify({directory,records},null,2));
 console.log(JSON.stringify({directory,sessions:records.length,usage_count:records.reduce((sum,item)=>sum+item.usage_count,0),sample:records[0]?.usage_sample}));
}
