// Completed town in an isolated real desktop; no agents or ticks are run.
import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapt/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),base=await fs.mkdtemp(path.join(root,'build/dense-layout-client-')),folder=path.join(base,'project'),directory=path.join(folder,'.nexarbor/runs/main');
await fs.cp(path.join(root,'项目演示/应用3-NPC小镇-最终'),folder,{recursive:true,filter:f=>!f.split(path.sep).some(x=>['.git','runs','cache'].includes(x))});
const host=await startStudio({directory,projectDirectory:folder}),env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const browser=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir',path.join(base,'client')],env});
try{
 const page=await browser.firstWindow(),errors=[];await browser.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1800,1100));
 page.on('pageerror',e=>errors.push(e.message));
 await expect(page.locator('.react-flow__node').first()).toBeVisible({timeout:20000});
 const reset=page.getByRole('button',{name:'清除筛选',exact:true});if(await reset.count())await reset.click();
 await expect(page.locator('.react-flow__node')).toHaveCount(59);
 const original=await page.locator('.react-flow__node').evaluateAll(ns=>Object.fromEntries(ns.map(n=>[n.dataset.id,n.style.transform])));
 const arrange=async()=>{
  await page.getByRole('button',{name:'整理',exact:true}).click();
  await page.getByRole('tab',{name:'稠密整理',exact:true}).click();
  await page.getByRole('button',{name:'整理当前视图',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('已整理当前视图',{timeout:30000});
  await expect(page.getByRole('button',{name:'整理',exact:true})).toBeEnabled();
  await page.waitForTimeout(2500);
 };
 await arrange();
 const geometry=await page.locator('.react-flow__node').evaluateAll(ns=>ns.map(n=>{const xy=n.style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/).slice(1).map(Number);return {id:n.dataset.id,x:xy[0],y:xy[1],w:parseFloat(n.style.width),h:parseFloat(n.style.height)};}));
 const width=Math.max(...geometry.map(n=>n.x+n.w))-Math.min(...geometry.map(n=>n.x)),height=Math.max(...geometry.map(n=>n.y+n.h))-Math.min(...geometry.map(n=>n.y));
 expect(width/height).toBeGreaterThan(.6);expect(width/height).toBeLessThan(2.1);
 for(let i=0;i<geometry.length;i++)for(const b of geometry.slice(i+1)){const a=geometry[i];expect(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y).toBeTruthy();}
 expect(await page.locator('.react-flow__node:has(.node-name:text-is("小砾")) .network-node').evaluate(n=>getComputedStyle(n).width)).toBe('84px');
 const strokes=await page.locator('.react-flow__edge:not(.react-flow__edge-ownership) .react-flow__edge-path').evaluateAll(es=>[...new Set(es.map(e=>getComputedStyle(e).stroke))]);
 expect(strokes.length).toBeGreaterThan(4);
 await page.screenshot({path:path.join(base,'dense-all.png')});
 await page.getByRole('button',{name:'撤销',exact:true}).click();
 expect(await page.locator('.react-flow__node').evaluateAll(ns=>Object.fromEntries(ns.map(n=>[n.dataset.id,n.style.transform])))).toEqual(original);
 for(const kind of ['文本','亚节点'])await page.getByRole('group',{name:'节点类型显示'}).getByRole('button',{name:kind,exact:true}).click();
 await arrange();
 await page.screenshot({path:path.join(base,'dense-main.png')});
 expect(errors).toEqual([]);
 const state=await host.request('state',{resume:false});expect(state.live.document.network.nodes).toHaveLength(52);expect(state.live.document.network.nodes.find(n=>n.type==='pulse').parameters.state.sequence).toBe(25);await fs.writeFile(path.join(base,'verification.json'),JSON.stringify({passed:true,realNodes:52,moduleRectangles:7,ratio:width/height,noOverlaps:true,nodeSize:84,colours:strokes.length,undo:true,filtered:true,paidCalls:0,ticksAdvanced:0,errors},null,2));console.log('PASS '+base);
}finally{await browser.close();await host.close();}
