import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
import {startStudio as oldStudio} from '../../../build/release-0.9.0-unpacked/Nexarbor-0.9.0-win-x64/adapters/harness/studio/host.mjs';
import {inspectHarnessExecutable,saveHarnessExecutable} from '../../../adapters/harness/framework/harness-installation.js';
const base=await fs.mkdtemp(path.resolve('build/project-restore-retry-')),project=path.join(base,'project');await fs.cp(path.resolve('项目演示/应用1-讨论协作-最终'),project,{recursive:true});
const old=path.join(process.env.LOCALAPPDATA,'Programs/DeepSeek Harness/DeepSeek Harness.exe'),good='E:/dsh/Harness/DeepSeek Harness.exe';const previous=process.env.DATANET_HARNESS_EXE;
const shape=s=>({nodes:s.live.document.network.nodes.length,modules:s.live.document.network.nodes.reduce((n,x)=>n+Object.keys(x.modules).length,0),edges:s.live.document.network.nodes.reduce((n,x)=>n+x.connections.interfaces.length,0)});
let host;
try{
 const unsupported=await inspectHarnessExecutable(old);assert.equal(unsupported.compatible,false);assert.ok(unsupported.missing.includes('dsh-working-directory'));await assert.rejects(saveHarnessExecutable(old),/Harness.*缺少原生服务/);
 process.env.DATANET_HARNESS_EXE=old;await assert.rejects(oldStudio({directory:path.join(project,'.nexarbor/runs/legacy'),projectDirectory:project}),/dsh-working-directory/);
 process.env.DATANET_HARNESS_EXE=good;host=await oldStudio({directory:path.join(project,'.nexarbor/runs/legacy'),projectDirectory:project});const broken=shape(await host.request('state',{}));assert.equal(broken.modules,0);assert.equal(broken.edges,0);await host.close();host=null;
 host=await startStudio({directory:path.join(project,'.nexarbor/runs/legacy'),projectDirectory:project});const recovered=shape(await host.request('state',{}));assert.equal(recovered.nodes,18);assert.ok(recovered.modules>0);assert.ok(recovered.edges>0);await host.close();host=null;
 // New starts fail before writing placeholders when the installed SDK is incompatible.
 process.env.DATANET_HARNESS_EXE=old;const fresh=path.join(project,'.nexarbor/runs/fresh');await assert.rejects(startStudio({directory:fresh,projectDirectory:project}),/Harness.*缺少原生服务/);await assert.rejects(fs.access(path.join(fresh,'checkpoints.sqlite3')));
 // A pending import always retries the full saved project, even with an existing checkpoint.
 process.env.DATANET_HARNESS_EXE=good;await fs.writeFile(path.join(project,'.nexarbor/runs/legacy/project-restore-pending.json'),'{}');host=await startStudio({directory:path.join(project,'.nexarbor/runs/legacy'),projectDirectory:project});const retried=shape(await host.request('state',{}));assert.deepEqual(retried,recovered);await assert.rejects(fs.access(path.join(project,'.nexarbor/runs/legacy/project-restore-pending.json')));await host.close();host=null;
 console.log(JSON.stringify({passed:true,base,oldVersion:unsupported.version,broken,recovered,retried,model_calls:0}));
}finally{await host?.close();if(previous===undefined)delete process.env.DATANET_HARNESS_EXE;else process.env.DATANET_HARNESS_EXE=previous;}
