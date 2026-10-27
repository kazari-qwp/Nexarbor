// Actual HTTP host, original editor transport and current project/runtime.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {startStudio} from '../adapt/harness/studio/host.mjs';
import {createEditorClient} from '../frontends/shared/editor-client.js';
const root=process.cwd(),directory=path.resolve(process.argv[2]);await fs.mkdir(directory,{recursive:true});
const folder=path.join(directory,'project');await fs.cp(path.join(root,'resources/examples/npc-town'),folder,{recursive:true});
let studio;
try{
 studio=await startStudio({directory:path.join(directory,'runtime'),projectDirectory:folder,modelDirectory:path.join(directory,'models')});
 const url=new URL(studio.url),token=new URLSearchParams(url.hash.slice(1)).get('token'),api=createEditorClient({token,endpoint:url.origin+'/api'});
 const page=await fetch(url.origin);assert.equal(page.status,200);assert.match(await page.text(),/root/);
 const catalog=await api('catalog'),state=await api('state',{resume:true});assert.equal(state.live.document.network.nodes.length,52);assert.equal(Object.keys(catalog.modules).length,21);
 assert.ok(catalog.nodes.some(item=>item.id==='csv'));assert.ok(catalog.nodes.some(item=>item.id==='wiki'));
 const library=await api('editor.library');assert.ok(Number.isInteger(library.version)&&library.version>=0);
 assert.equal((await api('project.info')).format,'nexarbor-project/v2');assert.equal((await api('validate',{document:state.live.document})).valid,true);
 const text=state.live.document.network.nodes.find(node=>node.name==='世界时间');const preview=await api('data.preview',{node:text,files:state.live.document.files,operation:'read',arguments:{key:'content'}});assert.match(preview.result.items[0].content,/第1天/);
 const work=await api('studio.create',{kind:'network'});assert.match(work.git.branch,/agent-/);
 const advice=await api('advice.open',{role:'network',newConversation:true,selection:{nodes:[text.node_id]}});assert.equal(advice.snapshot.nodes,52);
 const status=await api('startup.status');assert.ok(status.timings.ready>=0);
 const evidence={status:'passed',nodes:52,catalog_modules:21,data_templates:catalog.nodes.filter(item=>['value','csv','sqlite','wiki'].includes(item.id)).length,workspace:work.id,advice:advice.id,paid_requests:0,frontend_url:studio.url};
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({...evidence,frontend_url:'local-authenticated-editor'}));
}finally{await studio?.close();}
