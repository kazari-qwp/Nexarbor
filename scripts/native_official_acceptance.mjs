import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {requireCompatibleHarness} from '../adapt/harness/framework/harness-installation.js';
import {OfficialToolsRunner} from '../adapt/harness/official/official-runner.mjs';
const directory=await fs.mkdtemp(path.join(process.cwd(),'build/official-runner-'));
const status=await requireCompatibleHarness();
const runner=new OfficialToolsRunner(directory);
try{
 const tools=await runner.start();
 for(const name of ['pwsh','read','write','edit','glob','grep'])assert.ok(tools.some(tool=>tool.name===name),'Missing official tool '+name);
 const contracts=await runner.request('contracts',{});
 assert.equal(contracts.pwsh.format,'harness-tool-result/v1');
 const result=await runner.request('invoke',{actor:'verification',name:'pwsh',arguments:{description:'验证真实官方工具宿主',command:'Write-Output "official-runner-ok"',workdir:directory,timeoutMs:60000}});
 assert.equal(result.value.exitCode,0);
 assert.ok(result.value.stdout.text.includes('official-runner-ok'));
 const evidence={passed:true,version:status.version,compatible:status.compatible,tool_count:tools.length,official_runner:true,official_contracts:true,paid_api_calls:0};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));
 console.log(JSON.stringify({...evidence,directory}));
}finally{await runner.close();}
