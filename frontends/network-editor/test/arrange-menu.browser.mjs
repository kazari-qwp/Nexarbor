import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const connection=JSON.parse(await fs.readFile('E:/Nexarbor项目/NPC小镇/.nexarbor/runs/main/editor-connection.json','utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1800,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api',async route=>{
  const data=route.request().postDataJSON();
  if(['workspace.view','workspace.save'].includes(data.operation))return route.fulfill({json:{value:{savedAt:new Date().toISOString()}}});
  return route.continue();
 });
 await page.goto(connection.url);
 const trigger=page.getByRole('button',{name:'整理',exact:true});
 await expect(trigger).toBeVisible({timeout:20000});
 const clickCentre=async locator=>{const box=await locator.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);};
 await clickCentre(trigger);
 await expect(trigger).toHaveAttribute('aria-expanded','true');
 const menu=page.getByRole('dialog',{name:'整理选项',exact:true});
 await expect(menu).toBeVisible();
 await page.screenshot({path:'../../build/town-migration/arrange-menu-open.png'});
 // Check actual painted hit targets; locator.click() alone can scroll a clipped
 // dropdown into a toolbar and falsely pass while it is unusable by a person.
 for(const name of ['层级整理','稠密整理']){
  const tab=page.getByRole('tab',{name,exact:true});
  const hittable=await tab.evaluate(element=>{const r=element.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return element===hit||element.contains(hit);});
  expect(hittable,`${name} must be painted and clickable below the toolbar`).toBeTruthy();
 }
 if(process.argv.includes('--reproduce'))process.exitCode=0;
 else{
  await clickCentre(page.getByRole('tab',{name:'稠密整理',exact:true}));
  await expect(page.getByRole('tab',{name:'稠密整理',exact:true})).toHaveAttribute('aria-selected','true');
  await clickCentre(page.getByRole('button',{name:'整理当前视图',exact:true}));
  await expect(menu).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('已整理当前视图',{timeout:30000});
  await clickCentre(trigger);await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);await expect(trigger).toBeFocused();
  await clickCentre(trigger);await page.mouse.click(500,500);await expect(menu).toHaveCount(0);
  for(const width of [1200,2560]){
   await page.setViewportSize({width,height:950});await trigger.scrollIntoViewIfNeeded();await clickCentre(trigger);
   await expect(menu).toBeVisible();const r=await menu.boundingBox();expect(r.x).toBeGreaterThanOrEqual(8);expect(r.x+r.width).toBeLessThanOrEqual(width-8);
   const tab=page.getByRole('tab',{name:'稠密整理',exact:true});
   expect(await tab.evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})).toBeTruthy();
   await page.keyboard.press('Escape');
  }
  expect(errors).toEqual([]);console.log('PASS real mouse clicks: visible tabs, arrange action, Escape/outside dismissal, 1200/1800/2560 widths; no page errors');
 }
}finally{await browser.close();}
