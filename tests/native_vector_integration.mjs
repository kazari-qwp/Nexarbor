// Actual managed backend and local HuggingFace model; no model API calls.
import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {startStudio} from '../adapt/harness/studio/host.mjs';
const root=process.cwd(),folder=await fs.mkdtemp(path.join(root,'build/native-vector-integration-')),project=path.join(folder,'project'),runtime=path.join(project,'.nexarbor/runs/main');
await fs.cp(path.join(root,'项目演示/应用2-资料库-初始'),project,{recursive:true,filter:f=>!['.git','.nexarbor','__pycache__'].includes(path.basename(f))});
const file=path.join(project,'networks/main.json'),manifest=JSON.parse(await fs.readFile(file,'utf8'));
for(const ref of manifest.nodes){const file=path.join(project,ref.file),node=JSON.parse(await fs.readFile(file,'utf8'));for(const module of node.tables.modules)if(module.module_id==='knowledge.catalog')module.config.embedding={model_path:path.join(root,'build/models/bge-small-zh-v1.5'),device:'cpu',max_length:512,batch_size:32};await fs.writeFile(file,JSON.stringify(node,null,2));}
let host;const started=Date.now();
try{
 host=await startStudio({directory:runtime,projectDirectory:project});
 const call=(operation,args={})=>host.request('module.call',{node:'root',module:'knowledge.tools',operation,arguments:args});
 const initial=await host.request('startup.status');assert.equal(initial.vector.torch_imported,false);assert.equal(initial.vector.state,'idle');
 await call('kb_task',{content:'向量启动专项',mode:'agent'});
 const wiki=await call('kb_create_node',{name:'原文',storage:'wiki'});
 const record=await call('kb_store',{collection:wiki.id,content:'# SQLite\n## Shared database files\nDo not share SQLite database files between two computers using network filesystems. Use a client-server database when multiple computers need the same database.',key:'doc'});assert.equal(record.index.status,'ready',JSON.stringify(record.index));
 const result=await call('kb_search',{query:'多台计算机共享数据库文件',semantic:true});assert.ok(result.items.length);const hit=result.items[0];assert.equal(hit.entry.storage,'wiki');assert.equal(hit.matches[0].location_verified,true);assert.equal((await call('kb_fetch',hit.read)).version,1);
 const status=await host.request('startup.status');assert.equal(status.vector.torch_imported,false);assert.equal(status.vector.worker.loaded_on_main_thread,true);assert.equal(status.vector.worker.torch_imported,true);
 const report={passed:true,real_local_embedding:true,paid_api_calls:0,elapsed_seconds:(Date.now()-started)/1000,vector:status.vector,wiki_read:hit.read};await fs.writeFile(path.join(folder,'verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({directory:folder,...report}));
}catch(error){await fs.writeFile(path.join(folder,'failure.json'),JSON.stringify({error:error.stack},null,2));console.log('FAILED '+folder);throw error;}finally{await host?.close();}
