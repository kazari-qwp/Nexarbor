import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
import {copySubnet} from '../src/subnets.js';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/bookmark-views-e2e-'+Date.now());
let host=await startStudio({directory}),client,page;const errors=[];
const api=async(operation,params={})=>{const response=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})});const result=await response.json();if(result.error)throw Error(result.error);return result.value;};
const library=()=>api('editor.library');
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const launch=async()=>{client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));await expect(page.locator('.bookmark-dock')).toBeVisible({timeout:20000});};
const node=id=>page.locator('.react-flow__node[data-id="'+id+'"]');
const history=(kind,id)=>page.locator('.history-card[data-history-kind="'+kind+'"][data-history-id="'+id+'"]');
const canvas=()=>page.locator('.node-link-gesture');
try{
 const initial=await api('state');let document=initial.live.document;
 for(const id of ['a','b'])document=await api('template',{kind:'node',options:{id,name:'节点 '+id},document});
 document=await api('connect',{document,connection:{source:'a',target:'b',channels:['tools'],threshold:1,multiplier:1,attributes:{note:'边参数'}}});
 const layout={root:{x:0,y:0},a:{x:210,y:0},b:{x:420,y:100}};
 await api('apply',{document,base_commit:initial.live.commit,layout});
 const one=copySubnet(document,['a'],'internal',layout),line=copySubnet(document,[],'internal',layout,['a|0']),network=copySubnet(document,['a','b'],'internal',layout);
 const books=[{id:'one',name:'单点名称',mode:'internal',snapshot:one},{id:'line',name:'单边名称',mode:'external',snapshot:line},{id:'network',name:'网络名称',mode:'internal',snapshot:network}].map((b,i)=>({...b,createdAt:i,category:'default'}));
 await api('editor.library.update',{action:'bookmark.patch',changes:books.map(b=>({id:b.id,expected:null,value:b}))});
 await api('editor.library.update',{action:'history.push',entries:[{kind:'node',id:'a',label:'节点 a',snapshot:one},{kind:'edge',id:'a|0',label:'历史边',source:'a',target:'b',metadata:document.network.nodes.find(n=>n.node_id==='a').connections.interfaces[0].metadata},{kind:'bookmark',id:'removed-network',label:'已删除书签的网络',mode:'internal',snapshot:network},{kind:'bookmark',id:'removed-line',label:'已删除书签的纯边',mode:'internal',snapshot:line}]});
 await launch();await expect(page.locator('.bookmark-dock')).toHaveClass(/thumbnail-view/);
 const bookmarks=page.getByRole('region',{name:'书签区'}); // section 通过 aria-label 暴露为区域。
 const left=await bookmarks.boundingBox(),right=await page.getByRole('region',{name:'历史区'}).boundingBox();expect(left.width/right.width).toBeGreaterThan(2.9);expect(left.width/right.width).toBeLessThan(3.1);
 for(const item of await page.locator('.bookmark-card,.history-card').all()){expect((await item.innerText()).trim()).toBe('');await expect(item).toHaveAttribute('draggable','true');const box=await item.boundingBox();expect(box.width).toBeLessThan(60);expect(box.height).toBeLessThan(50);}
 const single=page.locator('[data-bookmark-id="one"]'),edge=page.locator('[data-bookmark-id="line"]'),subnet=page.locator('[data-bookmark-id="network"]');
 await expect(single.locator('circle.single-node')).toHaveCount(1);await expect(single.locator('path')).toHaveCount(0);await expect(single).toHaveAttribute('title','单点名称');
 await expect(edge.locator('circle')).toHaveCount(0);await expect(edge.locator('path')).toHaveCount(1);await expect(subnet.locator('circle')).toHaveCount(2);await expect(subnet.locator('path')).toHaveCount(1);
 const runbar=await page.locator('.runbar').boundingBox(),panel=await page.locator('.canvas-panel').boundingBox();expect(Math.abs(panel.x+panel.width-runbar.x-runbar.width-18)).toBeLessThan(2);expect(runbar.width).toBeLessThan(panel.width-50);
 await page.screenshot({path:path.join(directory,'01-thumbnail-ribbon.png')});
 const top=await page.locator('.topbar-actions').boundingBox();const heading=await page.locator('.topbar-heading').boundingBox();expect(top.x).toBeLessThan(heading.x+heading.width+25);expect(Math.abs(top.y-heading.y)).toBeLessThan(10);expect((await page.getByRole('button',{name:'网络文档',exact:true}).boundingBox()).height).toBeLessThan(35);await expect(page.locator('.topbar .canvas-toolbar')).toHaveCount(1);await expect(page.locator('.canvas-panel>.canvas-toolbar')).toHaveCount(0);
 await page.getByRole('button',{name:'设置',exact:true}).hover();await page.getByRole('menuitem',{name:'自定义快捷键',exact:true}).click();await expect(page.getByRole('dialog',{name:'客户端设置',exact:true})).toBeVisible();await page.getByRole('button',{name:'关闭客户端设置',exact:true}).click();
 await history('node','a').dragTo(canvas(),{targetPosition:{x:130,y:90}});await expect(page.locator('.react-flow__node')).toHaveCount(4);await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__node')).toHaveCount(3);
 await history('edge','a|0').dragTo(node('root'));await expect(page.locator('.react-flow__edge')).toHaveCount(2);await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__edge')).toHaveCount(1);
 await history('bookmark','removed-network').dragTo(canvas(),{targetPosition:{x:170,y:90}});await expect(page.locator('.react-flow__node')).toHaveCount(5);await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__node')).toHaveCount(3);
 await history('bookmark','removed-line').dragTo(node('root'));await expect(page.getByLabel('连接起点',{exact:true})).toHaveValue('root');await expect(page.getByLabel('连接终点',{exact:true})).toHaveValue('');await page.getByRole('button',{name:'取消',exact:true}).click();
 const order=(await library()).history.map(e=>e.kind+e.id);await page.getByRole('button',{name:'切换为文字视图',exact:true}).click();await expect(page.locator('.bookmark-dock')).toHaveClass(/text-view/);expect((await single.innerText()).trim()).toBe('A · 1 点');await expect(history('node','a')).toContainText('节点 a');expect((await library()).history.map(e=>e.kind+e.id)).toEqual(order);
 await history('node','a').dragTo(canvas(),{targetPosition:{x:150,y:100}});await expect(page.locator('.react-flow__node')).toHaveCount(4);await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__node')).toHaveCount(3);
 await page.screenshot({path:path.join(directory,'02-text-view.png')});
 // 删除至仅剩根节点，撤销和重做后它始终保留。
 await node('a').click();await page.keyboard.press('Delete');await expect(page.locator('.react-flow__node')).toHaveCount(2);await node('b').dispatchEvent('click');await expect(node('b')).toHaveClass(/selected/);await page.keyboard.press('Delete');await expect(node('root')).toBeVisible();await expect(page.locator('.react-flow__node')).toHaveCount(1);await expect(page.locator('.welcome')).toHaveCount(0);
 await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__node')).toHaveCount(2);await page.keyboard.press('Control+y');await expect(page.locator('.react-flow__node')).toHaveCount(1);await expect(node('root')).toBeVisible();await page.keyboard.press('Control+s');await expect.poll(async()=>(await api('state')).draft.document.network.nodes.length).toBe(1);
 await page.screenshot({path:path.join(directory,'03-root-remains.png')});
 const oldWidth=(await canvas().boundingBox()).width;
 await page.getByRole('button',{name:'折叠左侧栏',exact:true}).click();await expect(page.getByRole('button',{name:'展开左侧栏',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'折叠右侧栏',exact:true}).click();await expect(page.getByRole('button',{name:'展开右侧栏',exact:true})).toBeVisible();expect((await canvas().boundingBox()).width).toBeGreaterThan(oldWidth+400);expect((await page.locator('.left-panel').boundingBox()).width).toBe(32);expect((await page.locator('.right-panel').boundingBox()).width).toBe(32);await expect(node('root')).toBeVisible();
 await page.screenshot({path:path.join(directory,'04-collapsed-sidebars.png')});
 await client.close();client=null;await host.close();host=await startStudio({directory});await launch();await expect(page.locator('.bookmark-dock')).toHaveClass(/text-view/);await expect(node('root')).toBeVisible();await expect(page.locator('.react-flow__node')).toHaveCount(1);
 await expect(page.getByRole('button',{name:'展开左侧栏',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'展开右侧栏',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'展开左侧栏',exact:true}).click();await expect(page.getByRole('button',{name:'折叠左侧栏',exact:true})).toBeVisible();await page.getByRole('button',{name:'展开右侧栏',exact:true}).click();await expect(page.getByRole('button',{name:'折叠右侧栏',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'切换为缩略图视图',exact:true}).click();await expect(page.locator('.bookmark-dock')).toHaveClass(/thumbnail-view/);expect(errors).toEqual([]);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,ratio:'3:1',compactImageOnly:true,tooltipNameOnly:true,historyDrags:['node','edge','network','pure-edge'],textToggle:true,viewPersists:true,singleRowToolbar:true,settingsHoverMenu:true,rootRemains:true,sidebarsCollapseAndPersist:true,undoRedo:true,modelCalls:0,errors},null,2));console.log('PASS 缩略图、历史拖入、单行工具栏及折叠侧栏：'+directory);
}catch(error){if(page)await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});throw error;}finally{if(client)await client.close();await host.close();}
