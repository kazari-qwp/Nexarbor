import {_electron,expect} from '@playwright/test';import fs from 'node:fs/promises';import path from 'node:path';
const root=path.resolve('../..'),run=path.join(root,'build/studio/generated-ui-'+Date.now());await fs.mkdir(run,{recursive:true});
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const client=await _electron.launch({executablePath:path.join(root,'build/desktop/Nexarbor Workbench-win32-x64/Nexarbor Workbench.exe'),args:['--workspace',run,'--network',path.join(root,'configs/npc_town/network.json'),'--user-data-dir='+path.join(run,'desktop-profile')],env});
try{
 const page=await client.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await expect(page.locator('.react-flow__node')).toHaveCount(31,{timeout:20000});
 await page.getByRole('button',{name:'全选可见',exact:true}).click();await page.getByRole('button',{name:/整理选中/}).click();await expect(page.getByRole('status')).toContainText('已整理 31');
 await page.getByRole('button',{name:'组件工作室',exact:true}).first().click();const dialog=page.getByRole('dialog',{name:'组件工作室',exact:true});
 await dialog.getByRole('button',{name:'family.household',exact:false}).click();
 await expect(dialog.locator('.studio-toolbar')).toContainText('已发布，只读');
 await expect(dialog.locator('.cm-content')).toContainText('class Module');
 await page.screenshot({path:path.join(run,'generated-source.png')});
 await dialog.getByRole('button',{name:'关闭组件工作室',exact:true}).click();await page.locator('.react-flow__controls-fitview').click();await page.waitForTimeout(400);
 await page.screenshot({path:path.join(run,'generated-town.png')});
 await page.getByRole('button',{name:'网络文档',exact:true}).click();
 const docs=page.getByRole('dialog',{name:'网络文档',exact:true});await docs.getByRole('button',{name:'world/common.md',exact:true}).click();
 await docs.locator('.cm-content').click();await page.keyboard.press('Control+End');await page.keyboard.insertText('\n桌面文档验证。');
 await docs.getByRole('button',{name:'关闭网络文档',exact:true}).click();await page.getByRole('button',{name:'校验并更新网络',exact:true}).click();
 await expect(page.getByRole('button',{name:'校验并更新网络',exact:true})).toBeDisabled();
 const state=await page.evaluate(async()=>{const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':sessionStorage.getItem('nexarbor-token')},body:JSON.stringify({operation:'state',params:{}})});return (await r.json()).value;});
 expect(state.live.document.files['world/common.md']).toContain('桌面文档验证。');
 expect(errors).toEqual([]);await fs.writeFile(path.join(run,'verification.json'),JSON.stringify({passed:true,pureNetworkConfig:true,nodes:31,generatedComponents:12,immutableSourceVisible:true,documentEditingAndApply:true,modelCalls:0,errors},null,2));console.log('PASS Agent-made town desktop:',run);
}finally{await client.close();}
