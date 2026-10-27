import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const connection=JSON.parse(await fs.readFile('E:/Nexarbor项目/NPC小镇/.nexarbor/runs/main/editor-connection.json','utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 // Display checks never overwrite the user's open page or its view preferences.
 await page.route('**/api',async route=>{
  const data=route.request().postDataJSON();
  if(['workspace.view','workspace.save'].includes(data.operation))return route.fulfill({json:{value:{savedAt:new Date().toISOString()}}});
  return route.continue();
 });
 await page.goto(connection.url);
 await page.waitForTimeout(3000);
 console.log('nodes',await page.locator('.react-flow__node').count(),'errors',errors,'text',(await page.locator('body').innerText()).slice(0,500));
 await page.screenshot({path:'../../build/town-migration/before-aggregation.png'});
 const reset=page.getByRole('button',{name:'清除筛选',exact:true});if(await reset.count())await reset.click();
 await expect(page.locator('.react-flow__node[data-id="world/save"]')).toHaveCount(1,{timeout:15000});
 await page.locator('.react-flow__node[data-id="world/save"]').dispatchEvent('click');
 const selector=page.getByLabel('信号汇总方式',{exact:true});
 await expect(selector).toHaveValue('max');
 expect(await selector.locator('option').allTextContents()).toEqual(['求和','最大值','最小值','平均值']);
 for(const value of ['sum','min','mean','max']){await selector.selectOption(value);await expect(selector).toHaveValue(value);}
 await page.screenshot({path:'../../build/town-migration/signal-aggregation.png'});
 expect(errors).toEqual([]);
 console.log('PASS real editor: four aggregation modes, save=max, no page errors');
}finally{await browser.close();}
