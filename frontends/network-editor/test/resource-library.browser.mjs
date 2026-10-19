// 真实组件库、Python 后端和 Electron 客户端，模型调用为零。
import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/resource-library-e2e-'+Date.now());
let host=await startStudio({directory}),client,page;const errors=[];
const api=async(operation,params={})=>{const response=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})});const result=await response.json();if(result.error)throw Error(result.error);return result.value;};
const library=()=>api('editor.library'),node=id=>page.locator('.react-flow__node[data-id="'+id+'"]');
const tree=kind=>page.locator('[data-resource-library="'+kind+'"]'),item=(kind,id)=>tree(kind).locator('[data-resource-id="'+id+'"]');
const book=id=>page.locator('[data-bookmark-id="'+id+'"]');
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const launch=async()=>{client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));await expect(node('a')).toBeVisible({timeout:20000});};
const menuAction=async(kind,action,target)=>{await (target??tree(kind).locator('.resource-items')).click({button:'right'});await page.getByRole('menuitem',{name:(kind==='tool'?'工具':'模块')+action,exact:true}).click();};
const prompt=async(name,value)=>{const dialog=page.getByRole('dialog',{name,exact:true});await dialog.getByRole('textbox').fill(value);await dialog.getByRole('button',{name:'确定',exact:true}).click();};
try{
 // 通过工作室正常保存、验证、发布一个含可选预览图的现有样例。
 const workspace=await api('studio.create',{sample:'blank'}),original=workspace.files['module.json'],spec=JSON.parse(original);
 spec.description='计数展示';spec.preview='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40"><rect x="8" y="5" width="44" height="30" rx="6" fill="#e8bd62"/><text x="30" y="26" text-anchor="middle" font-size="20">+</text></svg>');
 await api('studio.save',{id:workspace.id,file:'module.json',content:JSON.stringify(spec),expected:createHash('sha256').update(original).digest('hex')});
 const job=await api('studio.validate',{id:workspace.id});await expect.poll(async()=>(await api('studio.job',{job:job.id})).status,{timeout:25000}).toBe('passed');await api('studio.publish',{id:workspace.id});
 const catalog=await api('catalog'),tool=catalog.tools[0];expect(catalog.modules['example.counter'].preview).toBe(spec.preview);
 const initial=await api('state'),document=await api('template',{kind:'node',options:{id:'a',name:'装配节点'},document:initial.live.document});
 await api('apply',{document,base_commit:initial.live.commit,layout:{root:{x:0,y:0},a:{x:210,y:0}}});await launch();
 for(const kind of ['tool','module']){await expect(tree(kind)).not.toHaveAttribute('open','');await tree(kind).locator(':scope>summary').click();}
 // 目录新建、文件夹移动、资源剪切／粘贴与别名，不触碰网络。
 const historyBefore=(await library()).history;await menuAction('module','新建文件夹');await prompt('新建模块文件夹','分类一');
 await expect(tree('module').getByRole('button',{name:'模块文件夹 分类一',exact:true})).toBeVisible();await tree('module').getByRole('button',{name:'模块文件夹 分类一',exact:true}).dblclick();
 await menuAction('module','新建文件夹');await prompt('新建模块文件夹','分类二');await expect.poll(async()=>(await library()).assets.module.folders.length).toBe(2);
 const folders=(await library()).assets.module.folders,parent=folders.find(f=>f.name==='分类一').id,child=folders.find(f=>f.name==='分类二').id;
 await expect(item('module','metadata.fields')).toHaveCount(0);await tree('module').getByRole('button',{name:'全部模块',exact:true}).click();
 await item('module','metadata.fields').click();await item('module','metadata.fields').press('Control+x');
 await tree('module').getByRole('button',{name:'模块文件夹 分类一',exact:true}).dblclick();await tree('module').getByRole('button',{name:'模块文件夹 分类二',exact:true}).dblclick();await menuAction('module','粘贴');
 await expect.poll(async()=>(await library()).assets.module.items['metadata.fields'].folder).toBe(child);
 // 中途路径可跳转；剪切文件夹后粘贴到根目录，里面的资源仍留在该文件夹。
 await tree('module').getByRole('button',{name:'模块路径 分类一',exact:true}).click();await menuAction('module','剪切',tree('module').getByRole('button',{name:'模块文件夹 分类二',exact:true}));await tree('module').getByRole('button',{name:'全部模块',exact:true}).click();await menuAction('module','粘贴');
 await expect.poll(async()=>(await library()).assets.module.folders.find(f=>f.id===child).parent).toBeNull();
 await menuAction('module','重命名',tree('module').getByRole('button',{name:'模块文件夹 分类二',exact:true}));await prompt('重命名模块资源','常用');
 await expect(tree('module').getByRole('button',{name:'模块文件夹 常用',exact:true})).toBeVisible();await tree('module').getByRole('button',{name:'模块文件夹 常用',exact:true}).dblclick();
 await expect(item('module','metadata.fields')).toBeVisible();await expect(item('module','example.counter')).toHaveCount(0);
 await tree('module').getByRole('button',{name:'模块上一级',exact:true}).click();await expect(item('module','example.counter')).toBeVisible();await tree('module').getByRole('button',{name:'模块返回',exact:true}).click();await expect(item('module','metadata.fields')).toBeVisible();
 await item('module','metadata.fields').click();await item('module','metadata.fields').press('F2');await prompt('重命名模块资源','元数据模板');
 expect((await library()).history).toEqual(historyBefore);await expect(item('module','metadata.fields')).toHaveAttribute('title',/^元数据模板：/);
 // 独立模块前端编辑，保存为配置书签，不改变节点或运行实例。
 await item('module','metadata.fields').click();const detail=page.getByLabel('模块资源详情',{exact:true}),frame=detail.frameLocator('iframe');
 await frame.getByRole('button',{name:'＋ 添加元数据',exact:true}).click();await frame.getByLabel('字段名称').fill('金币');await frame.getByLabel('字段类型').selectOption('number');await frame.getByLabel('字段值').fill('12');await frame.getByRole('button',{name:'保存配置',exact:true}).click();
 await expect(frame.getByText('已写入网络草稿，校验并更新网络后生效',{exact:true})).toBeVisible();
 await detail.getByRole('button',{name:'Save · 保存至书签',exact:true}).click();await expect.poll(async()=>(await library()).bookmarks.length).toBe(1);
 let preset=(await library()).bookmarks[0];expect(preset.asset.config).toEqual({fields:{金币:12}});expect((await api('state')).live.document.network.nodes.find(n=>n.node_id==='a').modules).toEqual({});expect((await library()).history).toEqual(historyBefore);
 await expect(book(preset.id)).toHaveClass(/module/);await expect(book(preset.id)).toHaveText('元数据模板');await expect(book(preset.id)).toHaveAttribute('title',/^元数据模板：/);
 await book(preset.id).dragTo(node('a'));await expect(node('a').getByRole('button',{name:'装配节点的模块，1 个',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'校验并更新网络',exact:true}).click();await expect(page.getByRole('button',{name:'校验并更新网络',exact:true})).toBeDisabled();expect((await api('state')).live.document.network.nodes.find(n=>n.node_id==='a').modules['metadata.fields'].config.fields.金币).toBe(12);
 // 当前挂载项顶部两个图标，保存配置和卸载；书签操作不截断撤销。
 await page.getByRole('button',{name:'保存模块 metadata.fields至书签',exact:true}).click();await expect.poll(async()=>(await library()).bookmarks.length).toBe(2);
 await page.getByRole('button',{name:'删除模块 metadata.fields',exact:true}).click();await expect(node('a').getByRole('button',{name:'装配节点的模块，0 个',exact:true})).toBeVisible();await page.keyboard.press('Control+z');await node('a').hover();await expect(node('a').getByRole('button',{name:'装配节点的模块，1 个',exact:true})).toBeVisible();
 // 直接资源拖放与重用历史；相同工具引用只挂载一次。
 await item('tool',tool.ref).dragTo(node('a'));await expect(node('a').getByRole('button',{name:'装配节点的工具，1 个',exact:true})).toBeVisible();
 await page.getByLabel('工具频道 '+tool.ref,{exact:true}).isVisible().then(async visible=>{if(!visible)await page.locator('.right-panel .module-section>summary').click();});
 await page.getByLabel('工具频道 '+tool.ref,{exact:true}).fill('tools, public');await page.getByRole('button',{name:'保存工具 '+tool.ref+'至书签',exact:true}).click();
 await expect.poll(async()=>(await library()).bookmarks.filter(b=>b.kind==='tool').length).toBe(1);const toolBook=(await library()).bookmarks.find(b=>b.kind==='tool');expect(toolBook.asset.channels).toEqual(['tools','public']);
 await expect(book(toolBook.id)).toHaveClass(/tool/);await expect(book(toolBook.id)).toHaveAttribute('title',toolBook.name+'：'+toolBook.description);
 await page.getByRole('button',{name:'删除工具 '+tool.ref,exact:true}).click();await book(toolBook.id).dragTo(node('a'));await expect(page.getByLabel('工具频道 '+tool.ref,{exact:true})).toHaveCount(1);
 const toolHistoryId=(await library()).history.find(e=>e.asset?.id===toolBook.asset.id&&e.asset.channels.join(',')===toolBook.asset.channels.join(',')).id;const toolHistory=page.locator('[data-history-kind="tool"][data-history-id="'+toolHistoryId+'"]');await toolHistory.dragTo(node('a'));await expect(node('a').getByRole('button',{name:'装配节点的工具，1 个',exact:true})).toBeVisible();
 const order=(await library()).history.map(e=>e.kind+e.id),time=(await library()).history.find(e=>e.id===toolHistoryId).time;
 await toolHistory.click({button:'middle'});await prompt('历史名称','常用工具');expect((await library()).history.map(e=>e.kind+e.id)).toEqual(order);expect((await library()).history.find(e=>e.id===toolHistoryId).time).toBe(time);await expect(toolHistory).toHaveAttribute('title','常用工具：'+toolBook.description);
 // 有图模块显示图片；无图模块显示名称，两类背景不同；两区均按资源类型过滤。
 await tree('module').getByRole('button',{name:'全部模块',exact:true}).click();await item('module','example.counter').click();await page.getByRole('button',{name:'Save · 保存至书签',exact:true}).click();const picture=(await library()).bookmarks.find(b=>b.asset?.id==='example.counter');
 await expect(book(picture.id).locator('img')).toBeVisible();expect(await book(picture.id).locator('img').evaluate(i=>i.complete&&i.naturalWidth>0)).toBe(true);await book(picture.id).dragTo(node('a'));await expect(page.locator('[data-history-id="'+(await library()).history.find(e=>e.asset?.id===picture.asset.id).id+'"] img')).toBeVisible();
 expect(await book(toolBook.id).evaluate(e=>getComputedStyle(e).backgroundColor)).not.toBe(await book(picture.id).evaluate(e=>getComputedStyle(e).backgroundColor));
 for(const label of ['书签类型','历史类型']){await page.getByLabel(label,{exact:true}).selectOption('module');const region=page.getByRole('region',{name:label==='书签类型'?'书签区':'历史区',exact:true});await expect(region.locator('.tool')).toHaveCount(0);await expect(region.locator('.module').first()).toBeVisible();await page.getByLabel(label,{exact:true}).selectOption('all');}
 const bookmarkCount=(await library()).bookmarks.length,stableHistory=(await library()).history;
 await item('module','example.counter').hover();await page.keyboard.press('a');await expect.poll(async()=>(await library()).bookmarks.length).toBe(bookmarkCount+1);await page.keyboard.press('a');await expect.poll(async()=>(await library()).bookmarks.length).toBe(bookmarkCount);
 await toolHistory.hover();await page.keyboard.press('b');await expect.poll(async()=>(await library()).bookmarks.length).toBe(bookmarkCount+1);await page.keyboard.press('b');await expect.poll(async()=>(await library()).bookmarks.length).toBe(bookmarkCount);expect((await library()).history).toEqual(stableHistory);
 await page.screenshot({path:path.join(directory,'01-resources.png')});
 // 小地图外框与 SVG 同尺寸且留在画布内；改变窗口大小会缩放视口而不移动节点。
 const map=page.locator('.react-flow__minimap'),svg=map.locator('svg');const mb=await map.boundingBox(),sb=await svg.boundingBox();expect(Math.abs(mb.width-sb.width)).toBeLessThan(3);expect(Math.abs(mb.height-sb.height)).toBeLessThan(3);
 // 两侧宽度拖动独立保存，不影响历史排序。
 const beforeResizeHistory=(await library()).history.map(e=>e.kind+e.id);await page.evaluate(()=>{window.resizeEvents=[];for(const type of ['pointerdown','pointermove','pointerup','pointercancel','lostpointercapture'])document.addEventListener(type,e=>{const target=e.target.closest('.sidebar-resizer');if(target)window.resizeEvents.push({type,side:target.className,x:e.clientX,pointer:e.pointerId});},true);});
 for(const [side,delta] of [['left',45],['right',-35]]){const separator=page.getByRole('separator',{name:'调整'+(side==='left'?'左':'右')+'侧栏宽度',exact:true}),box=await separator.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+60);await page.mouse.down();await page.mouse.move(box.x+box.width/2+delta,box.y+60,{steps:8});await page.mouse.up();await expect.poll(async()=>(await library()).settings.panels?.[side+'Width']).toBeGreaterThan(side==='left'?260:350);}
 expect((await library()).history.map(e=>e.kind+e.id)).toEqual(beforeResizeHistory);
 const positions=await page.locator('.react-flow__node').evaluateAll(ns=>ns.map(n=>n.style.transform)),zoom=await node('a').boundingBox();
 const win=await client.browserWindow(page);await win.evaluate(w=>w.setSize(1120,760));await page.waitForTimeout(400);const smaller=await node('a').boundingBox();expect(smaller.width).toBeLessThan(zoom.width);expect(await page.locator('.react-flow__node').evaluateAll(ns=>ns.map(n=>n.style.transform))).toEqual(positions);
 await win.evaluate(w=>w.maximize());await page.waitForTimeout(450);expect((await node('a').boundingBox()).width).toBeGreaterThan(smaller.width);await page.screenshot({path:path.join(directory,'02-window-resize.png')});
 await win.evaluate(w=>w.unmaximize());await page.waitForTimeout(350);expect(Math.abs((await node('a').boundingBox()).width-smaller.width)).toBeLessThan(3);
 await page.getByRole('button',{name:'保存',exact:true}).click();await client.close();client=null;await host.close();host=await startStudio({directory});await launch();
 for(const kind of ['tool','module']){await expect(tree(kind)).not.toHaveAttribute('open','');await tree(kind).locator(':scope>summary').click();}
 expect((await library()).assets.module.items['metadata.fields']).toEqual({folder:child,name:'元数据模板'});expect((await library()).assets.module.folders.find(f=>f.id===parent).name).toBe('分类一');
 expect((await page.locator('.left-panel').boundingBox()).width).toBe((await library()).settings.panels.leftWidth);await expect(book(picture.id).locator('img')).toBeVisible();expect(errors).toEqual([]);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,virtualFolders:true,explorerBreadcrumbs:true,oneDirectoryLevel:true,resizableSidebars:true,cutPasteFolderAndItem:true,aliasesPersist:true,standaloneModuleFrontend:true,configuredAssetBookmark:true,directLibraryDrop:true,historyDrop:true,deduplicatedTool:true,headerSaveAndDelete:true,historyStableOnManagement:true,resourceFilters:true,distinctColors:true,optionalPreview:true,nameAndDescriptionTooltip:true,resizeKeepsNodePositions:true,minimapMatchesFrame:true,restartRestores:true,modelCalls:0,errors},null,2));console.log('PASS 资源栏、配置书签、历史复用、窗口视口及小地图：'+directory);
}catch(error){if(page)await fs.writeFile(path.join(directory,'diagnostics.json'),JSON.stringify({errors,events:await page.evaluate(()=>window.resizeEvents??[]).catch(()=>[])}));if(page)await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});throw error;}finally{if(client)await client.close();await host.close();}
