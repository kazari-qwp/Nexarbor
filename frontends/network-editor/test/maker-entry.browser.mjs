// 真实客户端与后端：仅验证入口、目录与发布，不调用模型。
import {_electron,expect} from '@playwright/test';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/maker-entry-'+Date.now()),host=await startStudio({directory});let client,page;const errors=[];
const api=async(operation,params={})=>{const r=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})});const v=await r.json();if(v.error)throw Error(v.error);return v.value;};
try{
 for(const kind of ['tool','preset'])await api('editor.library.update',{action:'asset.folder.create',kind,id:'test-'+kind,name:'制作目录'});
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));await expect(page.locator('.react-flow__node')).toBeVisible({timeout:20000});
 for(const [kind,label,button] of [['tool','工具','制作新工具'],['preset','网络预设','制作网络预设']]){
  const tree=page.locator('[data-resource-library="'+kind+'"]');await tree.locator(':scope>summary').click();await tree.getByRole('button',{name:label+'文件夹 制作目录',exact:true}).dblclick();await tree.getByRole('button',{name:button,exact:true}).click();const dialog=page.getByRole('dialog',{name:'组件工作室',exact:true});await expect(dialog).toBeVisible();
  const expectedKind=kind==='preset'?'network':'tool';let work;
  await expect.poll(async()=>{work=(await api('studio.catalog')).workspaces.find(w=>w.kind===expectedKind&&w.display_folder==='test-'+kind);return work?.kind;},{timeout:15000}).toBe(expectedKind);
  await expect(dialog.locator('.studio-toolbar>strong')).toHaveText(work.id);expect(work.display_folder).toBe('test-'+kind);
  const testing=dialog.getByRole('checkbox',{name:'允许在当前网络副本内测试',exact:true});await expect(testing).not.toBeChecked();await testing.check();await expect(testing).toBeChecked();await testing.uncheck();
  await dialog.getByRole('button',{name:'复制当前网络测试',exact:true}).click();await expect(dialog.getByText(/"ok": true/)).toBeVisible({timeout:20000});expect((await api('state')).live.document.network.nodes[0].modules).toEqual({});
  if(kind==='preset'){
   await expect(dialog.getByRole('heading',{name:'网络预设制作 Agent',exact:true})).toBeVisible();const toggle=dialog.getByRole('checkbox',{name:'允许委托制作模块和工具',exact:true});await expect(toggle).not.toBeChecked();await toggle.check();await expect(toggle).toBeChecked();await toggle.uncheck();
   await dialog.getByRole('button',{name:'验证网络',exact:true}).click();await expect(dialog.getByText('验证结果 · passed',{exact:true})).toBeVisible({timeout:20000});await dialog.getByRole('button',{name:'保存为网络预设',exact:true}).click();await expect(dialog.getByText(/网络预设已保存到磁盘/)).toBeVisible();
  }else{await expect(dialog.getByRole('heading',{name:'模块／工具制作 Agent',exact:true})).toBeVisible();await expect(dialog.getByRole('checkbox',{name:'允许委托制作模块和工具',exact:true})).toHaveCount(0);}
  await dialog.getByRole('button',{name:'关闭组件工作室',exact:true}).click();
 }
 const library=await api('editor.library');expect(library.presets.some(p=>p.display_folder==='test-preset')).toBe(true);expect(errors).toEqual([]);await page.screenshot({path:path.join(directory,'entries.png')});await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,toolEntry:true,networkEntry:true,originFolders:true,creationSwitch:true,testEnvironmentSwitch:true,independentCurrentNetworkCopy:true,realPresetFile:true,modelCalls:0,errors},null,2));console.log('PASS 制作入口、开关、网络测试副本与目录保存：'+directory);
}finally{if(client)await client.close();await host.close();}
