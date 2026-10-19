// 实际托管 RPC：首次向量调用在主线程导入，目录/工具/检索均按需，模型只用 E 盘本地文件。
import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {startStudioProfile} from '../../../adapters/harness/studio/host.mjs';
const root=process.cwd(),directory=path.join(root,'build/startup-on-demand-'+Date.now());await fs.mkdir(directory,{recursive:true});
const host=await startStudioProfile(path.join(root,'configs/knowledge_v3/profile.json'),{directory});
const api=async(operation,params={})=>{const r=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URLSearchParams(new URL(host.url).hash.slice(1)).get('token')},body:JSON.stringify({operation,params})}),v=await r.json();if(v.error)throw Error(v.error);return v.value;};
const evidence={};
try{
 evidence.before=await api('startup.status');assert.equal(evidence.before.vector.state,'idle');assert.equal(evidence.before.vector.torch_imported,false);assert.equal(evidence.before.officialState,'idle');
 const catalog=await api('catalog');assert.equal(catalog.toolsReady,false);assert.ok(!catalog.tools.some(t=>t.ref.startsWith('harness:')));
 const list=await api('editor.library.index');assert.equal(list.presets.length,3);assert.ok(list.presets.every(p=>p.lazySnapshot&&!p.snapshot));evidence.indexBytes=Buffer.byteLength(JSON.stringify(list));
 const loaded=await api('catalog',{official:true});assert.ok(loaded.toolsReady);assert.ok(loaded.tools.some(t=>t.ref.startsWith('harness:')));evidence.officialTools=loaded.tools.filter(t=>t.ref.startsWith('harness:')).length;
 const state=await api('state'),node=structuredClone(state.live.document.network.nodes.find(n=>n.node_id==='knowledge/rag'));
 node.parameters.embedding={model_path:path.join(root,'build/models/bge-small-zh-v1.5'),device:'cpu',max_length:512,batch_size:8};
 let files=Object.fromEntries(Object.entries(state.live.document.files).filter(([name])=>!name.startsWith(node.parameters.directory+'/')));node.parameters.collection_id=null;
 // 先保存普通资料；第一次语义查询才配置模型，明确测量真正的首次计算。
 const embedding=node.parameters.embedding;node.parameters.embedding=null;
 for(const [key,value] of [['solar','太阳能电池板把阳光转换为电能，可用于家庭清洁能源供电。'],['bread','制作面包需要面粉、水、酵母和烤箱。']]){const r=await api('data.preview',{node,files,operation:'put',arguments:{key,value}});assert.equal(r.result.status,'ok');files={...files,...r.files};}
 node.parameters.embedding=embedding;
 const start=performance.now();let complete=false;
 const search=api('data.preview',{node,files,operation:'index',arguments:{}}).finally(()=>complete=true);
 // 第一次导入科学库时，其他 RPC 工作者仍能返回网络与目录，不能被一个全局事务堵住。
 await new Promise(resolve=>setTimeout(resolve,100));const ping=performance.now();await api('state');evidence.concurrentStateMs=Math.round(performance.now()-ping);evidence.stateReturnedBeforeSearch=!complete;
 const answer=await search;assert.equal(answer.result.status,'ok');assert.equal(answer.result.items[0].status,'ready',JSON.stringify(answer.result));assert.ok(evidence.stateReturnedBeforeSearch);evidence.firstIndexMs=Math.round(performance.now()-start);
 evidence.after=await api('startup.status');assert.equal(evidence.after.vector.state,'ready');assert.equal(evidence.after.vector.worker.loaded_on_main_thread,true);assert.equal(evidence.after.vector.torch_imported,false);assert.equal(evidence.after.vector.worker.torch_imported,true);
 const solar=await api('data.preview',{node,files:{...files,...answer.files},operation:'query',arguments:{request:{method:'semantic',query:'如何利用日照发电',top_k:1}}});assert.ok(solar.result.items.some(i=>i.key==='solar'),JSON.stringify(solar.result));
 const again=await api('data.preview',{node,files:{...files,...answer.files},operation:'query',arguments:{request:{method:'semantic',query:'面包的原料',top_k:1}}});assert.ok(again.result.items.some(i=>i.key==='bread'),JSON.stringify(again.result));
 assert.deepEqual((await api('state')).live.document,state.live.document);evidence.realSemanticSearch=true;evidence.originalDataUnchanged=true;evidence.paidCalls=0;
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log('PASS 按需加载与真实向量 RPC '+directory);console.log(JSON.stringify(evidence));
}finally{await host.close();if(evidence.after?.vector.worker.pid){assert.throws(()=>process.kill(evidence.after.vector.worker.pid,0));evidence.workerClosed=true;await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));}}
