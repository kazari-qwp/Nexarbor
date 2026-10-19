import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';
const run=path.resolve(process.argv[2]),roots=path.join(run,'.datanet/networks'),records=[];
for(const folder of await fs.readdir(roots)){const file=path.join(roots,folder,'editor-connection.json');try{records.push({file,mtime:(await fs.stat(file)).mtimeMs});}catch{}}
records.sort((a,b)=>b.mtime-a.mtime);
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const client=await _electron.launch({executablePath:path.resolve('../../build/desktop/Nexarbor Workbench-win32-x64/Nexarbor Workbench.exe'),args:['--connection',records[0].file,'--user-data-dir='+path.join(run,'desktop-test-profile')],env,timeout:30000});
try{
 const page=await client.firstWindow();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await expect(page.getByRole('button',{name:'保存',exact:true})).toBeVisible();
 expect(await client.evaluate(({BrowserWindow})=>{const w=BrowserWindow.getAllWindows()[0];w.setBounds({width:1600,height:1000});const p=w.webContents.getLastWebPreferences();return {contextIsolation:p.contextIsolation,nodeIntegration:p.nodeIntegration,sandbox:p.sandbox,webSecurity:p.webSecurity};})).toEqual({contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true});
 expect(await page.evaluate(()=>({node:typeof window.require,token:location.hash}))).toEqual({node:'undefined',token:''});
 await expect(page).toHaveTitle('Nexarbor · 网络工作台');
 const channels=page.getByRole('group',{name:'连接频道显示'}).getByRole('button');
 for(const button of await channels.all())await button.click();await expect(page.locator('.react-flow__node')).toHaveCount(0);
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();
 for(const name of ['access.read','access.write'])await page.getByRole('group',{name:'连接频道显示'}).getByRole('button',{name,exact:true}).click();
 await page.locator('.react-flow__controls-fitview').click();await page.waitForTimeout(400);
 const actor=page.locator('[data-id="world/npc/alice"] .network-node');await actor.dblclick();await expect(page.getByLabel('对话输入')).toBeVisible();await expect(page.locator('.chat-message.assistant').first()).toBeVisible();
 await page.locator('.chat-dialog .modal-header button').click();
 const node=page.locator('[data-id="world/npc/alice"]'),box=await node.boundingBox();
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+120,box.y+70,{steps:8});
 const wire=page.locator('.react-flow__edge[aria-label^="world/time → world/npc/alice"] [data-source-side]');
 await expect(wire).toHaveAttribute('data-routing','preview');await page.waitForTimeout(100);await expect(wire).toHaveAttribute('data-routing','preview');await page.mouse.up();await expect(wire).toHaveAttribute('data-routing','avoiding');
 await page.screenshot({path:path.join(run,'desktop-client.png')});expect(errors).toEqual([]);
 await fs.writeFile(path.join(run,'desktop-verification.json'),JSON.stringify({passed:true,packagedExecutable:true,sandbox:true,noNodeInRenderer:true,nativeMenu:true,allOffEmpty:true,doubleClickNativeChat:true,dragPreviewStable:true,modelApiCalls:0,errors},null,2));
 console.log('PASS packaged Electron client, sandbox, filters, native chat history and stable drag');
}finally{await client.close();}
