import {_electron as electron,expect} from '@playwright/test';import fs from 'node:fs/promises';import path from 'node:path';import {spawnSync} from 'node:child_process';
const root=path.resolve('build/release-0.9.0-unpacked/Nexarbor-0.9.0-win-x64'),base=await fs.mkdtemp(path.resolve('build/release09-smoke-'));
const env={...process.env,NEXARBOR_HARNESS_CONFIG:path.join(base,'harness.json')};for(const k of ['ELECTRON_RUN_AS_NODE','DATANET_HARNESS_EXE','NEXARBOR_ROOT','NEXARBOR_WORKSPACE','DATANET_PYTHON','DATANET_PRODUCT_ROOT','DATANET_PROJECT_DIRECTORY','PYTHONPATH','PYTHONHOME'])delete env[k];
const launch=args=>electron.launch({executablePath:path.join(root,'Nexarbor.exe'),args,cwd:root,env,timeout:60000});let app;
try{app=await launch(['--user-data-dir='+path.join(base,'home-profile')]);const page=await app.firstWindow();await page.getByRole('button',{name:'选择 DeepSeek Harness 路径…',exact:true}).waitFor();const opened=app.waitForEvent('window');await page.getByRole('button',{name:'选择 DeepSeek Harness 路径…',exact:true}).click();const settings=await opened;await settings.getByLabel('Harness .exe 路径').fill('E:/dsh/Harness/DeepSeek Harness.exe');await settings.getByRole('button',{name:'保存路径',exact:true}).click();await expect(settings.getByRole('status')).toContainText('已保存');}finally{await app?.close();}
const checks=[];
for(const [name,count]of [['应用1-讨论协作-初始',2],['应用1-讨论协作-最终',18],['应用2-资料库-初始',4],['应用2-资料库-最终',8],['应用3-小镇-初始',59],['应用3-小镇-最终',59]]){
 const project=path.join(base,name);await fs.cp(path.join(root,'项目演示',name),project,{recursive:true});
 if(name==='应用1-讨论协作-最终'){const p=spawnSync(path.join(root,'runtime/python/python.exe'),['-X','utf8',path.join(project,'准备项目.py')],{encoding:'utf8',windowsHide:true});if(p.status)throw Error(p.stderr);}
 let app;const errors=[];
 try{app=await launch(['--user-data-dir='+path.join(base,'profile-'+checks.length),'--project',project]);const page=await app.firstWindow();page.on('pageerror',e=>errors.push(e.message));await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().forEach(w=>w.hide()));await page.waitForURL(/^http:\/\/127\.0\.0\.1:/,{timeout:90000});await page.locator('.node-link-gesture').waitFor({timeout:90000});
 const data=await page.evaluate(async()=>{const token=sessionStorage.getItem('nexarbor-token');async function api(operation,params={}){const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation,params})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error??'api failed');return d.value;}return {state:await api('state'),models:await api('models.list')};});
 expect(data.state.live.document.network.nodes.length).toBe(count);expect(data.models.defaults).toEqual({context_window:600000,max_tokens:50000});expect(errors).toEqual([]);
 checks.push({name,nodes:count,errors,passed:true});console.log(JSON.stringify(checks.at(-1)));
 }finally{await app?.close();}
}
const result={passed:true,base,checks,harness_chooser:true,model_calls:0};await fs.writeFile(path.join(base,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
