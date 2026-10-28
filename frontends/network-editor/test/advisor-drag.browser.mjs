import {chromium,_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';
import {startStudio} from '../../../adapt/harness/studio/host.mjs';
const base=await fs.mkdtemp(path.resolve('../../build/advisor-regression-')),project=path.join(base,'project');
const host=await startStudio({directory:path.join(project,'.nexarbor/runs/main'),projectDirectory:project});let browser,electron;
try{
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[],results=[];
 page.on('pageerror',e=>errors.push({message:e.message,stack:e.stack}));
 await page.goto(host.url);
 const node=page.locator('.react-flow__node').first(),dialog=page.getByRole('dialog',{name:'Agent 咨询'}),title=dialog.locator('.advisor-title');
 const open=async()=>{await node.click({button:'right'});await page.getByRole('menuitem',{name:'咨询 Agent',exact:true}).click();await expect(dialog).toBeVisible();await expect(dialog.getByLabel('询问 Agent')).toBeEnabled();};
 const close=async()=>{await dialog.getByRole('button',{name:'关闭咨询',exact:true}).click();await expect(dialog).toHaveCount(0);};
 const drag=async(dx,dy)=>{const box=await title.boundingBox();await page.mouse.move(box.x+150,box.y+15);await page.mouse.down();await page.mouse.move(box.x+150+dx,box.y+15+dy,{steps:10});await page.mouse.up();};
 const rect=()=>dialog.boundingBox();
 const savedMatches=async()=>{const box=await rect(),viewport=page.viewportSize();await expect.poll(async()=>{const v=(await host.request('advice.ui',{})).advisor;return Math.abs(v.width-box.width)+Math.abs(v.height-box.height)+Math.abs(v.right-(viewport.width-box.x-box.width))+Math.abs(v.bottom-(viewport.height-box.y-box.height));}).toBeLessThan(3);};
 await open();
 for(let i=0;i<20;i++)await drag(i%2?-80:80,i%2?60:-60);
 expect(errors).toEqual([]);await expect(node).toBeVisible();await savedMatches();results.push('20 native drags preserve canvas and persist exact final position');
 await title.evaluate(title=>{
  const r=title.getBoundingClientRect(),options={bubbles:true,pointerId:17,pointerType:'mouse',button:0,buttons:1,clientX:r.x+150,clientY:r.y+15};
  const capture=title.setPointerCapture,release=title.releasePointerCapture;
  title.setPointerCapture=()=>{};title.releasePointerCapture=()=>{};
  try{title.dispatchEvent(new PointerEvent('pointerdown',options));for(let i=0;i<100;i++)title.dispatchEvent(new PointerEvent('pointermove',{...options,clientX:r.x+150-i,clientY:r.y+15+i}));title.dispatchEvent(new PointerEvent('pointerup',{...options,clientX:r.x+51,clientY:r.y+114,buttons:0}));}
  finally{title.setPointerCapture=capture;title.releasePointerCapture=release;}
 });
 await expect(title).toBeVisible();await savedMatches();expect(errors).toEqual([]);results.push('100 queued pointermoves + same-task release no longer unmount React');
 for(const eventName of ['pointercancel','lostpointercapture']){
  const b=await title.boundingBox();await page.mouse.move(b.x+140,b.y+16);await page.mouse.down();await page.mouse.move(b.x+160,b.y+36);
  await title.evaluate((el,type)=>el.dispatchEvent(new PointerEvent(type,{pointerId:1,bubbles:true})),eventName);
  const before=await rect();await page.mouse.move(b.x+170,b.y+40);await page.mouse.up();expect(await rect()).toEqual(before);
  await drag(-10,-10);await savedMatches();
 }results.push('pointer cancellation/lost capture stops movement and allows next drag');
 await close();await host.request('advice.ui',{key:'advisor',value:{width:700,height:610,right:24,bottom:24}});await open();await expect.poll(async()=>(await rect()).width).toBe(700);
 const beforeResize=await rect();await page.mouse.move(beforeResize.x+beforeResize.width-3,beforeResize.y+beforeResize.height-3);await page.mouse.down();await page.mouse.move(beforeResize.x+beforeResize.width-83,beforeResize.y+beforeResize.height-63,{steps:15});await page.mouse.up();
 const afterResize=await rect();console.log('RESIZE',JSON.stringify({beforeResize,afterResize}));expect(afterResize.width).toBeLessThan(beforeResize.width-20);expect(afterResize.height).toBeLessThan(beforeResize.height-20);await savedMatches();results.push('native CSS resize persists final dimensions');
 await dialog.getByRole('button',{name:'展开咨询页面',exact:true}).click();const studio=page.getByRole('dialog',{name:'组件工作室'});await expect(studio).toBeVisible();await expect(studio.getByLabel('模块制作需求')).toBeEnabled();await studio.getByLabel('收起为咨询窗口').click();await expect(dialog.getByLabel('询问 Agent')).toBeEnabled();expect(await rect()).toEqual(afterResize);
 await close();await open();await expect.poll(rect).toEqual(afterResize);results.push('maximize/restore and close/reopen retain geometry');
 await page.setViewportSize({width:900,height:650});await expect.poll(async()=>{const r=await rect();return r.x>=11&&r.y>=35&&r.x+r.width<=889&&r.y+r.height<=639;}).toBe(true);
 await drag(-1500,-1500);let bounds=await rect();expect(bounds.x).toBeGreaterThanOrEqual(11);expect(bounds.y).toBeGreaterThanOrEqual(35);
 await drag(1500,1500);bounds=await rect();expect(bounds.x+bounds.width).toBeLessThanOrEqual(889);expect(bounds.y+bounds.height).toBeLessThanOrEqual(639);results.push('window resize/edge drag keeps whole title and controls on screen');
 await page.setViewportSize({width:1600,height:1000});await close();await host.request('advice.ui',{key:'advisor',value:{width:'broken',height:-200,right:99999,bottom:-500}});await open();await expect.poll(async()=>(await rect()).height).toBe(280);bounds=await rect();expect(bounds.width).toBe(700);expect(bounds.height).toBe(280);expect(bounds.x).toBeGreaterThanOrEqual(11);expect(bounds.y).toBeGreaterThanOrEqual(35);await close();results.push('invalid/stale saved geometry falls back to visible dimensions');
 let release,intercepted=false;const gate=new Promise(resolve=>release=resolve);
 const delayLayout=async route=>{const p=route.request().postDataJSON();if(p.operation==='advice.ui'&&!p.params?.key){intercepted=true;await gate;await route.fulfill({json:{value:{advisor:{width:700,height:610,right:24,bottom:24}}}});}else await route.continue();};
 await page.route('**/api',delayLayout);await open();await expect.poll(()=>intercepted).toBe(true);await drag(-60,-50);const moved=await rect();release();await page.unrouteAll({behavior:'wait'});await page.waitForTimeout(150);expect(await rect()).toEqual(moved);results.push('late layout response cannot overwrite an active user gesture');
 await page.screenshot({path:path.join(base,'fixed-advisor.png')});
 expect(errors).toEqual([]);await close();
 const poison=async route=>{if(route.request().postDataJSON().operation==='advice.open'){const response=await route.fetch(),body=await response.json();body.value.snapshot.selection.nodes=null;await route.fulfill({response,json:body});}else await route.continue();};
 await page.route('**/api',poison);await node.click({button:'right'});await page.getByRole('menuitem',{name:'咨询 Agent',exact:true}).click();await expect(dialog.getByRole('alert')).toContainText('请关闭后重新打开咨询');await expect(node).toBeVisible();await expect(page.getByRole('button',{name:'Commit',exact:true})).toBeVisible();await page.screenshot({path:path.join(base,'isolated-error.png')});await close();await page.unroute('**/api',poison);await open();await expect(dialog.getByRole('log')).toBeVisible();results.push('injected panel render failure stays local; canvas remains usable and consultation can reopen');
 // Exercise the same regression in the shipped Electron renderer, without touching the user instance.
 const entry=path.join(base,'electron-check.cjs');await fs.writeFile(entry,`let window;const {app,BrowserWindow}=require('electron');app.setPath('userData',${JSON.stringify(path.join(base,'electron-profile'))});app.whenReady().then(()=>{window=new BrowserWindow({show:false,width:1600,height:1000,webPreferences:{nodeIntegration:false,contextIsolation:true,offscreen:true,backgroundThrottling:false}});window.loadURL(${JSON.stringify(host.url)});});app.on('window-all-closed',()=>app.quit());`);
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 electron=await _electron.launch({executablePath:path.resolve('../desktop/node_modules/electron/dist/electron.exe'),args:[entry],env,timeout:20000});
 const ep=await electron.firstWindow(),electronErrors=[];ep.setDefaultTimeout(15000);ep.on('pageerror',e=>electronErrors.push(e.message));await ep.locator('.react-flow__node').first().click({button:'right'});await ep.getByRole('menuitem',{name:'咨询 Agent',exact:true}).click();const ed=ep.getByRole('dialog',{name:'Agent 咨询'});await expect(ed.getByLabel('询问 Agent')).toBeEnabled();
 for(let i=0;i<20;i++){const b=await ed.locator('.advisor-title').boundingBox();await ep.mouse.move(b.x+130,b.y+16);await ep.mouse.down();await ep.mouse.move(b.x+130+(i%2?40:-40),b.y+16+(i%2?-25:25),{steps:8});await ep.mouse.up();}
 expect(electronErrors).toEqual([]);await expect(ed).toBeVisible();await expect(ep.locator('.react-flow__node')).toHaveCount(1);results.push('Electron 44 shipped renderer: 20 consecutive native drags, zero page errors');
 await fs.writeFile(path.join(base,'verification.json'),JSON.stringify({passed:true,results,errors,electronErrors},null,2));console.log(JSON.stringify({base,results,errors,electronErrors},null,2));
}finally{await electron?.close();await browser?.close();await host.close();}
