// Real installed Harness tools; no model calls or credentials.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startStudio} from '../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const directory=path.join(root,'build/tool-collector-'+Date.now());
await fs.mkdir(directory,{recursive:true});const host=await startStudio({directory});
try{
 const initial=await host.rpc('studio_state'),document=structuredClone(initial.live.document);
 for(let number=1;number<=6;number++){
  document.network.nodes.push({type:number===1?'agent':'node',node_id:String(number),name:String(number),description:'',management_parent_id:'root',divergence:-1,data_kind:null,
   parameters:number===1?{file_path:'one-memory.md'}:{},connections:{interfaces:[]},agent:null,modules:{},offered_tools:number>1?[{ref:'harness:read',channels:['tools']}]:[],toolboxes:[],expose:[],execution:number===1?{executor:'harness',strength:2,channels:['tools']}:null,inputs:null});
 }
 const get=id=>document.network.nodes.find(n=>n.node_id===id);
 for(const[from,to]of[['1','2'],['2','3'],['3','2'],['2','4'],['4','5'],['5','6']])get(from).connections.interfaces.push({target_node_id:to,metadata:{channels:['tools'],threshold:0,multiplier:1,attributes:{}}});
 for(const[id,strength]of[['1',2],['3',10]])get(id).modules['tools.collector']={config:{},state:{},access:{strength,channels:['tools']}};
 document.files['probe.txt']='tool collector six reached via three';
 await host.rpc('studio_apply',{document,base_commit:initial.live.commit,layout:{}});
 const collected=await host.rpc('module_access',{node:'1',module:'tools.collector',operation:'collect'});
 assert.equal(collected.status,'ok');assert.equal(collected.data.length,5);
 assert.deepEqual(collected.data.map(t=>t.origin.node_id).sort(),['2','3','4','5','6']);
 assert.equal(collected.data.filter(t=>t.origin.node_id==='2').length,1);
 assert.deepEqual(collected.data.find(t=>t.origin.node_id==='6').via,['3']);
 const visit=await host.rpc('executor_visit',{actor:'1',target:'1'});assert.equal(visit.tools.length,5);
 const six=visit.tools.find(t=>t.origin.node_id==='6');
 const prepared=await host.rpc('executor_prepare',{actor:'1'});
 assert.equal(prepared.tools.filter(t=>t.name.startsWith('mod_')).length,5);
 assert.equal(prepared.tools.filter(t=>t.name.startsWith('ext_')).length,0);
 const response=await host.rpc('executor_invoke',{actor:'1',name:six.alias,arguments:{file_path:'probe.txt'}});
 assert.equal(response.isError,false);assert.match(JSON.stringify(response),/tool collector six reached via three/);
 const latest=await host.rpc('studio_state');latest.live.document.network.nodes.find(n=>n.node_id==='3').connections.interfaces=[];
 await host.rpc('studio_apply',{document:latest.live.document,base_commit:latest.live.commit,layout:{}});
 const updated=await host.rpc('executor_prepare',{actor:'1'});
 assert.equal(updated.tools.filter(t=>t.name.startsWith('mod_')).length,3);
 assert.equal((await host.rpc('executor_invoke',{actor:'1',name:six.alias,arguments:{file_path:'probe.txt'}})).status,'forbidden');
 const report={passed:true,edges:['1→2','2→3','3→2','2→4','4→5','5→6'],strengths:{1:2,3:10},collected:collected.data,nodeTwoCopies:1,nativeHarnessReadViaSix:true,revocation:true,modelCalls:0};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(report,null,2));
 console.log('PASS requested topology + real Harness read:',directory);
}finally{await host.close();}
