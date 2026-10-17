import fs from 'node:fs/promises';import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startEditorServer} from '../../../adapters/harness/framework/editor-server.js';
const root=path.resolve('../..');
export async function visualFixture(run){
 await fs.mkdir(run,{recursive:true});
 const ids=['world/time','world/npc/alice','world/npc/bob','world/pulse','world/savepoint'];
 const names=['时间','阿青','阿白','世界脉冲','五轮存档点'];
 const pairs=[[3,0],[0,1],[0,2],[1,4],[2,4],[4,3]];
 const layout=Object.fromEntries(ids.map((id,i)=>[id,[{x:100,y:500},{x:490,y:670},{x:550,y:460},{x:900,y:80},{x:1000,y:215}][i]]));
 const nodes=ids.map((node_id,i)=>({node_id,name:names[i],type:i===1||i===2?'agent':i===3?'pulse':i===0?'text_file':'node',modules:{},parameters:{},description:'布线展示样例，无模型执行',divergence:-1,toolboxes:[],expose:[],management_parent_id:null,connections:{interfaces:pairs.filter(([source])=>source===i).map(([,to])=>({target_node_id:ids[to],metadata:{channels:['world.tick'],threshold:0,multiplier:1,attributes:{}}}))}}));
 const document={network:{version:7,nodes,delegations:[],signals:{}},files:{}};
 const state={mode:'布线样例 · 不运行Agent',live:{document,commit:1,sessions:{}},draft:{document,layout,version:1,applied:true},job:{status:'idle',completed:0,requested:0}};
 const server=await startEditorServer({web:path.join(root,'extensions/editor/capabilities/network_editor/web'),directory:run,
  request:async(operation)=>{if(operation==='state')return state;if(operation==='catalog')return {modules:{},presets:[]};throw Error('展示样例不执行运行或保存操作');},
  chat:async()=>{throw Error('展示样例没有模型会话');},recover:async()=>{throw Error('展示样例没有恢复点');}});
 return {...server,state};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const server=await visualFixture(path.join(root,'build/routing-v7/preview'));console.log('Visual fixture ready.');setTimeout(()=>server.close(),3600000).unref();
}
