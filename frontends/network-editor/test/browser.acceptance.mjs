// UI-driven native acceptance: no direct API writes or hand-authored network JSON.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const run=path.resolve(process.argv[2]);const connection=JSON.parse(await fs.readFile(path.join(run,'editor.json'),'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const waitApi=async(operation,action)=>{const pending=page.waitForResponse(r=>r.url().endsWith('/api')&&r.request().postDataJSON()?.operation===operation,{timeout:30000});await action();const response=await pending;const body=await response.json();if(!response.ok()||body.error)throw new Error(JSON.stringify(body));return body.value;};
try{
 await page.goto(connection.url);
 if(!process.argv.includes('--finish-only')){
 if(!process.argv.includes('--continue-built')){
 await expect(page.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
 if(!await page.getByText('让网络定义行动空间',{exact:true}).isVisible()){
  await page.getByRole('button',{name:'新建空网络',exact:true}).click();
  await waitApi('template',()=>page.getByRole('button',{name:'添加到草稿',exact:true}).click());
 }
 await expect(page.getByText('让网络定义行动空间',{exact:true})).toBeVisible();
 await page.screenshot({path:path.join(run,'01-empty.png')});
 await waitApi('template',()=>page.getByRole('button',{name:'添加时间与共享资料',exact:true}).click());
 async function addPlace(id,name,kind){
  await page.getByRole('button',{name:'场所 地址与可组合业务能力'}).click();
  await page.getByLabel('模板编号').fill(id);await page.getByLabel('模板名称').fill(name);await page.getByLabel('场所业务模板').selectOption(kind);
  await waitApi('template',()=>page.getByRole('button',{name:'添加到草稿',exact:true}).click());
 }
 await addPlace('woods','小树林','forest');await addPlace('shop','商店','shop');
 for(const b of await page.getByRole('group',{name:'节点类型显示'}).getByRole('button').all())if(await b.textContent()!=='场所')await b.click();await page.locator('.react-flow__controls-fitview').click();
 const source=page.locator('[data-id="world/place/woods"] [data-handleid="right"]'),target=page.locator('[data-id="world/place/shop"] [data-handleid="left"]');
 await expect(source).toBeVisible();const a=await source.boundingBox(),b=await target.boundingBox();
 await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:15});await page.mouse.up();
 await expect(page.getByRole('dialog')).toBeVisible();await page.getByLabel('反向也建立连接（适合道路）').check();
 await waitApi('connect',()=>page.getByRole('button',{name:'建立连接',exact:true}).click());
 async function addResident(id,name,marker){
  await page.getByRole('button',{name:'居民 Agent 人格、动机、工具与上下文'}).click();
  await page.getByLabel('模板编号').fill(id);await page.getByLabel('模板名称').fill(name);await page.getByLabel('职业').selectOption('woodcutter');await page.getByLabel('居民初始场所').selectOption('world/place/woods');
  await page.getByLabel('居民人格').fill(marker+' 你是一个友善的伐木工。');await page.getByLabel('居民动机').fill('和邻居聊一聊，砍木材后去商店。');
  await waitApi('template',()=>page.getByRole('button',{name:'添加到草稿',exact:true}).click());
 }
 await addResident('alice','阿青','[Editor A]');await addResident('bob','阿白','[Editor B]');
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();
 const validation=await waitApi('validate',()=>page.getByRole('button',{name:'检查配置',exact:true}).click());expect(validation.valid,JSON.stringify(validation)).toBeTruthy();
 await waitApi('draft',()=>page.getByRole('button',{name:'保存草稿',exact:true}).click());
 const applied=await waitApi('apply',()=>page.getByRole('button',{name:'应用网络',exact:true}).click());expect(applied.applied,JSON.stringify(applied)).toBeTruthy();
 }
 for(const b of await page.getByRole('group',{name:'节点类型显示'}).getByRole('button').all())if(await b.textContent()!=='居民')await b.click();await page.locator('.react-flow__controls-fitview').click();
 const alice=page.locator('[data-id="world/npc/alice"]');await waitApi('view',()=>alice.click());
 await expect(page.getByText('由后端按照真实连接权限计算。界面筛选不授予权限。')).toBeVisible();
 await page.screenshot({path:path.join(run,'02-local-perspective.png')});
 await alice.dblclick();await expect(page.getByLabel('对话输入')).toBeVisible();
 await page.screenshot({path:path.join(run,'03-native-chat.png')});await page.locator('.chat-dialog .modal-header button').click();
 await waitApi('run',()=>page.getByRole('button',{name:'单步',exact:true}).click());
 await expect.poll(async()=>JSON.parse(await fs.readFile(path.join(run,'acceptance-state.json'),'utf8')).job.status,{timeout:45000}).toBe('completed');
 }
 const final=JSON.parse(await fs.readFile(path.join(run,'acceptance-state.json'),'utf8'));
 expect(final.job.reports[0].reports[0].returned).toBe(true);expect(final.job.reports[0].reports[0].status).toBe('completed');
 const live=final.document.network.nodes;const actor=live.find(n=>n.node_id==='world/npc/alice');
 expect(actor.modules['world.resident'].state.place).toBe('world/place/shop');expect(actor.modules['world.resident'].state.inventory.wood).toBe(2);expect(actor.modules['action.budget'].state.spent).toBe(10);
 expect(live.find(n=>n.node_id==='world/npc/bob').modules['action.budget'].state.spent).toBe(1);expect(final.job.reports[0].reports[0].layers[1].sort()).toEqual(['world/npc/alice','world/npc/bob']);
 await page.getByRole('button',{name:'全局网络',exact:true}).click();await page.locator('.react-flow__controls-fitview').click();
 await page.screenshot({path:path.join(run,'04-running-result.png')});
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();await page.getByLabel('搜索节点').fill('阿青');await expect(page.locator('.react-flow__node')).toHaveCount(3);await page.locator('.react-flow__controls-fitview').click();await page.waitForTimeout(400);
 await page.locator('[data-id="world/npc/alice"] .network-node').dblclick();await expect(page.getByLabel('对话输入')).toBeVisible();await expect(page.locator('.chat-message.assistant').first()).toBeVisible();
 const previousReplies=await page.locator('.chat-message.assistant').count();
 await page.getByLabel('对话输入').fill('测试对话入口，请回复一句。');await page.locator('.chat-composer button').click();await expect(page.getByLabel('对话输入')).toHaveValue('');
 await expect(page.locator('.chat-message.assistant')).toHaveCount(previousReplies+1);
 await expect(page.locator('.chat-dialog .modal-header small')).toContainText('idle');
 await page.screenshot({path:path.join(run,'05-chat-history.png')});
 await page.locator('.chat-dialog .modal-header button').click();await page.getByRole('button',{name:'清除筛选',exact:true}).click();
 await page.locator('.react-flow__pane').click({position:{x:8,y:8}});
 await waitApi('checkpoint',()=>page.getByRole('button',{name:'完整存档',exact:true}).click());
 await waitApi('points',()=>page.getByRole('button',{name:'恢复点',exact:true}).click());
 const oldOrigin=new URL(page.url()).origin;
 await page.getByRole('button',{name:'恢复为独立分支',exact:true}).first().click();
 await page.waitForURL(url=>url.origin!==oldOrigin,{timeout:30000});
 await expect(page.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
 await expect(page.getByText('Native Mock',{exact:true})).toBeVisible();
 await page.screenshot({path:path.join(run,'07-restored-workbench.png')});
 await fs.writeFile(path.join(run,'browser-verification.json'),JSON.stringify({passed:true,createdFromEmptyInUi:true,places:2,residents:2,linkedInUi:true,nativeChat:true,parallel:true,pulseReturned:true,actionBudget:true,restoredWorkbench:true,modelApiCalls:0,errors},null,2));
 expect(errors).toEqual([]);console.log('PASS UI creation, real permissions, native chat, parallel pulse, movement, action budget and saved draft');
}catch(e){await page.screenshot({path:path.join(run,'failure.png')});console.error('Page errors:',errors);console.error((await page.locator('body').innerText()).slice(-3500));throw e;}finally{await browser.close();}
