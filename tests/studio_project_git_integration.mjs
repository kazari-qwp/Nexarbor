// Actual project Git storage round-trip, using the current town runtime and Studio RPC.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {Project,readProjectBundle} from '../adapt/harness/studio/project.mjs';
import {SkillResources} from '../adapt/harness/studio/skills.mjs';
const root=process.cwd(),directory=path.resolve(process.argv[2]),folder=path.join(directory,'project'),runtime=path.join(directory,'runtime');
await fs.cp(path.join(root,'resources/examples/npc-town'),folder,{recursive:true});
const bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),runtime,['-B','-X','utf8','-m','adapt.harness.backend.server'],{NEXARBOR_STUDIO:'1',NEXARBOR_APPLICATION:'npc_town',NEXARBOR_PROJECT_DIRECTORY:folder});
const rpc=(method,parameters={})=>bridge.call(method,parameters,86460000),project=new Project(folder,runtime,rpc);
try{
 await project.initialize();const skills=new SkillResources(project,rpc);project.skillResources=skills;
 const state=await rpc('studio_state');assert.equal(state.live.document.network.nodes.length,45);
 const builtin=await skills.catalog();assert.ok(builtin['nexarbor-basics'].available);assert.equal(builtin['nexarbor-basics'].local,false);
 await skills.install('nexarbor-basics');assert.equal((await skills.bundles(['nexarbor-basics']))[0].name,'nexarbor-basics');
 const work=await rpc('studio_create',{kind:'tool'});work.git=await project.branch(work);assert.match(work.git.branch,/^agent-/);
 const files=await project.workFiles({id:work.id,kind:work.kind,module:JSON.parse(work.files['module.json']).id,git:work.git});assert.equal(files['module.py'],work.files['module.py']);
 await fs.writeFile(path.join(folder,'personal.txt'),'keep staged');await project.command(['add','personal.txt']);
 const saved={document:state.live.document,agents:{},signals:{},layout:{},view:{}};
 await project.ensureResources(saved.document);const commit=await project.commit({saved,message:'实际小镇保存',runtime:await rpc('studio_runtime_settings')});assert.match(commit.commit,/^[0-9a-f]{40}$/);
 assert.equal((await project.command(['diff','--cached','--name-only'])).trim(),'personal.txt');
 const bundle=await readProjectBundle(folder);assert.deepEqual(bundle.document,saved.document);assert.equal(bundle.document.network.nodes.length,45);
 const active=(await project.read()).activeNetwork,manifest=JSON.parse(await fs.readFile(path.join(folder,(await project.read()).networks[active].file),'utf8'));assert.equal(manifest.format,'nexarbor-project-network/v2');assert.ok(manifest.files.every(file=>typeof file.name==='string'));
 await project.conversation('advice',{id:'saved-advice',turns:[{question:'网络说明'}],job:{messages:[{role:'assistant',content:'真实归档消息'}]}});
 assert.equal((await project.conversations('advice'))[0].job.messages[0].content,'真实归档消息');
 const result={status:'passed',project:folder,runtime,nodes:45,modules:Object.keys((await project.read()).resources.modules).length,git:commit.commit,work_branch:work.git.branch,skills:1,paid_requests:0};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await bridge.close();}
