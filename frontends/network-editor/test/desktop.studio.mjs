import {_electron,expect} from '@playwright/test';import fs from 'node:fs/promises';import path from 'node:path';
const root=path.resolve('../..'),run=path.join(root,'build/studio/desktop-'+Date.now());await fs.mkdir(run,{recursive:true});
const env={...process.env,NEXARBOR_WORKSPACE:run};delete env.ELECTRON_RUN_AS_NODE;
const client=await _electron.launch({executablePath:path.join(root,'build/desktop/Nexarbor Workbench-win32-x64/Nexarbor Workbench.exe'),args:['--user-data-dir='+path.join(run,'desktop-profile')],env});
try{
 const page=await client.firstWindow();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await expect(page.getByRole('button',{name:'组件工作室',exact:true})).toBeVisible({timeout:20000});await page.getByRole('button',{name:'组件工作室',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'组件工作室',exact:true});await expect(dialog).toBeVisible();
 await dialog.getByRole('button',{name:'空白标准模块',exact:true}).click();await expect(dialog.locator('.cm-content[contenteditable="true"]')).toBeVisible();
 await dialog.locator('.cm-content[contenteditable="true"]').click();await page.keyboard.press('Control+End');await page.keyboard.insertText('\n# 桌面手工编辑验证\n');
 await dialog.getByRole('button',{name:'变更',exact:true}).click();await expect(dialog.locator('.cm-mergeView')).toBeVisible();
 await dialog.getByRole('button',{name:'保存源码',exact:true}).click();await expect(dialog.getByRole('button',{name:'保存源码',exact:true})).toBeDisabled();
 await dialog.getByRole('button',{name:'验证模块',exact:true}).click();await expect(dialog.locator('.studio-validation')).toContainText('passed',{timeout:15000});
 await dialog.getByRole('button',{name:'发布到组件库',exact:true}).click();await expect(dialog.locator('.studio-mount')).toContainText('example.counter');
 await dialog.getByRole('button',{name:'建立小镇组件实验场',exact:true}).click();await dialog.getByLabel('模块装配节点').selectOption('town/save');await dialog.getByRole('button',{name:'装配到节点',exact:true}).click();await expect(dialog.getByRole('status')).toContainText('已挂到节点');
 await page.screenshot({path:path.join(run,'component-studio.png')});
 await dialog.getByRole('button',{name:'关闭组件工作室',exact:true}).click();await page.locator('.react-flow__controls-fitview').click();
 await page.getByRole('button',{name:'单步',exact:true}).click();
    await expect(page.getByRole('button',{name:'单步',exact:true})).toBeEnabled({timeout:15000});
 const state=await page.evaluate(async()=>{const response=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':sessionStorage.getItem('nexarbor-token')},body:JSON.stringify({operation:'state',params:{}})});return (await response.json()).value;});
 expect(state.live.document.network.nodes.find(n=>n.node_id==='town/save').modules['example.counter'].state.count).toBe(1);
 expect(Object.values(state.live.document.network.signals).some(s=>s.status==='completed')).toBe(true);
 expect(errors).toEqual([]);await fs.writeFile(path.join(run,'verification.json'),JSON.stringify({passed:true,desktopAutostart:true,codeEditor:'CodeMirror',manualEdit:true,diff:true,validation:true,publish:true,mount:true,pulseReturns:true,modelCalls:0,errors},null,2));console.log('PASS desktop studio:',run);
}finally{await client.close();}
