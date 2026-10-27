import {_electron as electron, expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve('build/release-20261021-unpacked/Nexarbor-0.8.0-win-x64');
const base=await fs.mkdtemp(path.resolve('build/release-client-smoke-'));
const result={source:JSON.parse(await fs.readFile(path.join(root,'release.json'),'utf8')).source_commit,checks:[],model_calls:0};
const env={...process.env};
for(const key of ['ELECTRON_RUN_AS_NODE','NEXARBOR_ROOT','NEXARBOR_WORKSPACE','DATANET_PYTHON','DATANET_PRODUCT_ROOT','DATANET_PROJECT_DIRECTORY','PYTHONPATH','PYTHONHOME'])delete env[key];
env.DATANET_HARNESS_EXE='E:/dsh/Harness/DeepSeek Harness.exe';
for(const [name,relative,count] of [['town','resources/examples/npc-town',59],['knowledge','projects/knowledge-archive',4]]){
 const project=path.join(base,name);await fs.cp(path.join(root,relative),project,{recursive:true});
 let app;const errors=[];
 try{
  app=await electron.launch({executablePath:path.join(root,'Nexarbor.exe'),args:['--user-data-dir='+path.join(base,'profile-'+name),'--project',project],cwd:root,env,timeout:60000});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(e.message));
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().forEach(w=>w.hide()));
  await page.waitForURL(/^http:\/\/127\.0\.0\.1:/,{timeout:90000});
  await page.locator('.node-link-gesture').waitFor({timeout:90000});
  const state=await page.evaluate(async()=>{const token=new URLSearchParams(location.hash.slice(1)).get('token')??sessionStorage.getItem('nexarbor-token')??'';const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation:'state',params:{}})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error??'state failed');return d.value;});
  const doc=state.live?.document??state.document??state.draft?.document;const nodes=doc?.network?.nodes;
  if(!Array.isArray(nodes))throw Error('No network in state: '+Object.keys(state));
  expect(nodes.length).toBe(count);expect(errors).toEqual([]);
  await page.screenshot({path:path.join(base,name+'.png')});
  result.checks.push({project:name,nodes:nodes.length,errors,passed:true});
 }finally{await app?.close();}
}
await fs.writeFile(path.join(base,'result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({passed:true,base,...result}));
