// Existing recovery RPC restores native prefix forks and then acknowledges the executor bindings.
import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import crypto from 'node:crypto';import {fileURLToPath} from 'node:url';
import {Bridge} from '../../adapt/harness/framework/bridge.js';import {NativeRunner} from '../../adapt/harness/native/runner.mjs';import readAgentDefaults from '../../adapt/harness/framework/agent-defaults.cjs';
const root=fileURLToPath(new URL('../../',import.meta.url)),directory=path.resolve(process.argv[2]);let bridge,native;
const base=(process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com').replace(/\/$/,''),model=process.env.DEEPSEEK_MODEL??'deepseek-flash';
const signature=crypto.createHash('sha256').update('newcore-town:'+base+':'+model+':'+JSON.stringify({...readAgentDefaults(root),max_tokens:16000,reasoning_effort:'low'})).digest('hex');
try{
 native=new NativeRunner(directory,(method,p)=>bridge.call(method,p,86460000),{noCredentials:true});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8','-m','adapt.harness.backend.server'],{PYTHONPATH:root,NEXARBOR_APPLICATION:'npc_town'},(method,p)=>native.request(method,p));
 const info=await bridge.call('persistence_info'),before=await bridge.call('state');assert.equal(Object.keys(info.executor_restore_required).length,7);
 const {contexts}=await native.request('agent-context-restore',{contexts:info.executor_restore_required,transactional:false});
 const sessions=Object.fromEntries(Object.entries(contexts).map(([actor,cursor])=>[actor,cursor.session_id]));
 await bridge.call('persistence_executor_restored',{sessions});
 for(const [actor,cursor]of Object.entries(contexts))await bridge.call('executor_bind',{actor,session_id:cursor.session_id,context_cursor:cursor,model_signature:signature});
 const restored=await bridge.call('state');assert.deepEqual(restored.files,before.files);assert.deepEqual(restored.signals,before.signals);
 const pulse=restored.network.nodes.find(n=>n.type==='pulse');assert.equal(pulse.parameters.state.sequence,16);assert.equal(pulse.parameters.state.active_signal,null);
 const ready=await bridge.call('persistence_info');assert.deepEqual(ready.executor_restore_required,{});
 const point=await bridge.call('persistence_checkpoint',{contexts,bindings:ready.bindings,expected_commit:ready.commit_id,kind:'full'});
 await fs.writeFile(path.join(directory,'continuation-bindings.json'),JSON.stringify({passed:true,paid_api_calls:0,source_sessions:info.bindings,sessions,point,model_signature:signature},null,2));
 console.log(JSON.stringify({passed:true,paid_api_calls:0,restored_agents:7,tick:16,point:point.id}));
}finally{await native?.close();await bridge?.close();}
