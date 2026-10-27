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
 await expect(page.locator('.react-flow__node').first()).toBeVisible({timeout:20000});
 const reset=page.getByRole('button',{name:'清除筛选',exact:true});if(await reset.count())await reset.click();
 await expect(page.locator('.react-flow__node')).toHaveCount(61);
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
 expect(await page.locator('[data-id="npc/lin"] .network-node').evaluate(n=>getComputedStyle(n).width)).toBe('84px');
 const strokes=await page.locator('.react-flow__edge:not(.react-flow__edge-ownership) .react-flow__edge-path').evaluateAll(es=>[...new Set(es.map(e=>getComputedStyle(e).stroke))]);
 expect(strokes.length).toBeGreaterThan(4);
 await page.screenshot({path:'../../build/town-migration/v3-dense-all.png'});
 await page.getByRole('button',{name:'撤销',exact:true}).click();
 expect(await page.locator('.react-flow__node').evaluateAll(ns=>Object.fromEntries(ns.map(n=>[n.dataset.id,n.style.transform])))).toEqual(original);
 for(const kind of ['文本','亚节点'])await page.getByRole('group',{name:'节点类型显示'}).getByRole('button',{name:kind,exact:true}).click();
 await arrange();
 await page.screenshot({path:'../../build/town-migration/v3-dense-main.png'});
 expect(errors).toEqual([]);
 console.log('PASS actual client: 61 nodes, dense aspect',Number((width/height).toFixed(2)),', no overlaps, 84px nodes,',strokes.length,'bright edge colours, undo and filtered arrangement; no page errors');
}finally{await browser.close();}
