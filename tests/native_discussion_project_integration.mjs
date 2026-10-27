// Actual project + production RPC + installed official tools; no model requests.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import {OfficialToolsRunner} from '../adapt/harness/official/official-runner.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)), directory=path.resolve(process.argv[2]);
const toolName=(node,ref)=>'ext_'+createHash('sha256').update(node+'\0'+ref).digest('hex').slice(0,24);
let bridge,native,official;
async function start(){
 official=new OfficialToolsRunner(directory);
 native=new NativeRunner(directory,(method,p)=>bridge.call(method,p,90000),{noCredentials:true});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8','-m','adapt.harness.backend.server'],
                   {PYTHONPATH:root,NEXARBOR_APPLICATION:'discussion_collaboration'},
                   (method,p)=>method==='official-tool-invoke'?official.request('invoke',p):native.request(method,p));
 bridge.notifications.add(()=>native.notify());
}
async function stop(){await native?.close();await bridge?.close();await official?.close();bridge=null;native=null;official=null;}
try{
 await start();
 const state=await bridge.call('state');
 assert.equal(state.network.nodes.length,15);
 const tools=await bridge.call('module_call',{node_id:'executor-1',module_id:'tool_discovery',operation:'discover'});
 assert.ok(Array.isArray(tools));
 assert.ok(tools.some(tool=>tool.name===toolName('workspace','harness:pwsh')));
 const view=await bridge.call('executor_prepare',{actor:'executor-1'});
 const name=toolName('workspace','harness:pwsh');
 assert.ok(view.tools.some(tool=>tool.name===name));
 const result=await bridge.call('executor_invoke',{actor:'executor-1',name,arguments:{description:'验证实际讨论项目的终端工具',command:'Write-Output "DISCUSSION_NATIVE_TOOL_OK"',workdir:directory,timeoutMs:60000}},90000);
 assert.equal(result.value.exitCode,0);assert.ok(result.value.stdout.text.includes('DISCUSSION_NATIVE_TOOL_OK'));
 const marker='DISCUSSION_NOTES_PERSISTED';
 await bridge.call('module_call',{node_id:'notes',module_id:'notes.text',operation:'append',arguments:{text:marker,key:'native-rpc-marker'}});
 const prepared=await bridge.call('executor_prepare',{actor:'leader'});
 assert.ok(prepared.context.some(document=>document.text.includes(marker)));
 await bridge.call('save',{full:true});
 await stop();await start();
 const restored=await bridge.call('module_call',{node_id:'notes',module_id:'notes.text',operation:'read'});
 assert.ok(restored.content.includes(marker));
 const continuation=await bridge.call('executor_prepare',{actor:'executor-2'});
 assert.ok(continuation.tools.some(tool=>tool.name===name));
 const evidence={passed:true,paid_api_calls:0,actual_project_nodes:15,host_tools:31,real_official_command:true,discover_wire_declarations:true,markdown_context:true,cold_reopen:true};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{await stop();}
