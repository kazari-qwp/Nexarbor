// Read actual persisted DSH usage without invoking models or reconstructing responses.
import fs from 'node:fs/promises';import path from 'node:path';import zlib from 'node:zlib';
async function files(directory){try{return (await Promise.all((await fs.readdir(directory,{withFileTypes:true})).map(e=>e.isDirectory()?files(path.join(directory,e.name)):[path.join(directory,e.name)]))).flat();}catch(error){if(error.code==='ENOENT')return [];throw error;}}
export async function nativeUsage(directory){
 const result={responses:0,usage:{inputTokens:0,outputTokens:0,cacheReadTokens:0,cacheWriteTokens:0,totalTokens:0},sessions:[],pending_files:[]};
 for(const kind of ['native-logs','maker-logs'])for(const file of (await files(path.join(directory,kind))).filter(f=>f.endsWith('.jsonl.zstd'))){
  let events;try{const compressed=await fs.readFile(file),chunks=[];let offset=0;while(offset<compressed.length){const frame=zlib.zstdDecompressSync(compressed.subarray(offset),{info:true});if(!frame.engine.bytesWritten)throw Error('Empty frame');chunks.push(frame.buffer);offset+=frame.engine.bytesWritten;}events=Buffer.concat(chunks).toString('utf8').split('\n').filter(Boolean).map(line=>JSON.parse(line));}catch(error){result.pending_files.push({file,error:error.code??error.message});continue;}
  const rows=events.filter(e=>e.type==='assistant/message'&&e.data?.usage),usage=Object.fromEntries(Object.keys(result.usage).map(k=>[k,rows.reduce((n,e)=>n+(e.data.usage[k]??0),0)]));
  result.sessions.push({kind,session:path.basename(path.dirname(file)),responses:rows.length,usage});result.responses+=rows.length;for(const key in usage)result.usage[key]+=usage[key];
 }
 return result;
}
