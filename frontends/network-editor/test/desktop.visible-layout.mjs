import {_electron,expect} from '@playwright/test';import fs from 'node:fs/promises';import path from 'node:path';import {visualFixture} from './visual-fixture.mjs';
const run=path.resolve('../../build/visible-layout-'+Date.now()),fixture=await visualFixture(run),env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const client=await _electron.launch({executablePath:path.resolve('../../build/desktop/Nexarbor Workbench-win32-x64/Nexarbor Workbench.exe'),args:['--connection',path.join(run,'editor-connection.json'),'--user-data-dir='+path.join(run,'desktop-profile')],env});
try{
 const page=await client.firstWindow(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await expect(page.locator('.react-flow__node')).toHaveCount(5);
 const snapshot=()=>page.locator('.react-flow__node').evaluateAll(nodes=>Object.fromEntries(nodes.map(n=>[n.dataset.id,n.style.transform])));
 const area=positions=>{const points=Object.values(positions).map(s=>s.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/).slice(1).map(Number));return (Math.max(...points.map(p=>p[0]))-Math.min(...points.map(p=>p[0]))+92)*(Math.max(...points.map(p=>p[1]))-Math.min(...points.map(p=>p[1]))+92);};
 const original=await snapshot(),toggle=page.getByRole('group',{name:'节点类型显示'}).getByRole('button',{name:'Agent',exact:true});
 await toggle.click();await expect(page.locator('.react-flow__node')).toHaveCount(3);
 const filtered=await snapshot();for(const [id,p]of Object.entries(filtered))expect(p).toBe(original[id]);
 await expect(page.getByRole('button',{name:/整理选中/})).toBeDisabled();
 await page.screenshot({path:path.join(run,'before.png')});
 await page.getByRole('button',{name:'整理当前视图',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('已整理当前视图的 3 个节点及连线');
 await expect(page.locator('[data-routing="avoiding"]')).toHaveCount(2);await page.waitForTimeout(450);
 const compact=await snapshot();expect(area(compact)).toBeLessThan(area(filtered)*.6);
 const boxes=await page.locator('.react-flow__node').evaluateAll(nodes=>nodes.map(n=>({id:n.dataset.id,rect:n.getBoundingClientRect().toJSON()})));
 const canvas=await page.locator('.react-flow').boundingBox();
 for(const {rect}of boxes){expect(rect.width).toBeGreaterThan(80);expect(rect.x).toBeGreaterThanOrEqual(canvas.x);expect(rect.y).toBeGreaterThanOrEqual(canvas.y);expect(rect.right).toBeLessThanOrEqual(canvas.x+canvas.width);expect(rect.bottom).toBeLessThanOrEqual(canvas.y+canvas.height);}
 await page.screenshot({path:path.join(run,'after.png')});
 await toggle.click();await expect(page.locator('.react-flow__node')).toHaveCount(5);
 const shown=await snapshot();for(const id of ['world/npc/alice','world/npc/bob'])expect(shown[id]).toBe(original[id]);for(const [id,p]of Object.entries(compact))expect(shown[id]).toBe(p);
 await page.getByRole('button',{name:'撤销',exact:true}).click();expect(await snapshot()).toEqual(original);
 expect(errors).toEqual([]);await fs.writeFile(path.join(run,'verification.json'),JSON.stringify({passed:true,visibleOnly:true,noSelectionRequired:true,hiddenPositionsPreserved:true,filterDoesNotRelayout:true,undoRestoresLayout:true,beforeArea:area(filtered),afterArea:area(compact),modelCalls:0,errors},null,2));
 console.log('PASS visible compact layout:',run);
}finally{await client.close();await fixture.close();}
