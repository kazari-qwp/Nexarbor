import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import zlib from 'node:zlib';
import {nativeUsage} from '../scripts/native_usage.mjs';
test('native usage counts each billed message once when restored journals copy the earlier prefix',async()=>{
 const root=await fs.mkdtemp(path.join(process.cwd(),'build/native-usage-'));try{
  const row=id=>({type:'assistant/message',data:{message:{id},usage:{inputTokens:2,outputTokens:3,cacheReadTokens:5,totalTokens:10}}});
  for(const [name,ids] of [['original',['a','b']],['resumed',['a','b','c']]]){
   const directory=path.join(root,'native-logs',name);await fs.mkdir(directory,{recursive:true});
   await fs.writeFile(path.join(directory,'events.jsonl.zstd'),zlib.zstdCompressSync(Buffer.from(ids.map(id=>JSON.stringify(row(id))).join('\n')+'\n')));
  }
  const result=await nativeUsage(root);assert.equal(result.responses,3);assert.equal(result.duplicate_records,2);assert.equal(result.usage.totalTokens,30);assert.equal(result.usage.cacheReadTokens,15);
 }finally{assert.equal(path.dirname(path.resolve(root)),path.resolve('build'));await fs.rm(root,{recursive:true,force:true});}
});


test('native summary inference is billed once across restored journals',async()=>{
 const root=await fs.mkdtemp(path.join(process.cwd(),'build/native-usage-summary-'));try{
 const event={type:'compaction/summary',data:{compactionId:'same-summary',usage:{inputTokens:7,outputTokens:3,cacheReadTokens:10,totalTokens:20}}};
 for(const name of ['source','fork']){const folder=path.join(root,'native-logs',name);await fs.mkdir(folder,{recursive:true});await fs.writeFile(path.join(folder,'events.jsonl.zstd'),zlib.zstdCompressSync(Buffer.from(JSON.stringify(event)+'\n')));}
 const result=await nativeUsage(root);assert.equal(result.responses,1);assert.equal(result.assistant_responses,0);assert.equal(result.compaction_responses,1);assert.equal(result.duplicate_records,1);assert.equal(result.usage.totalTokens,20);
 }finally{assert.equal(path.dirname(path.resolve(root)),path.resolve('build'));await fs.rm(root,{recursive:true,force:true});}
});
