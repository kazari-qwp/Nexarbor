import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
import {copySubnet} from '../src/subnets.js';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/node-badges-e2e-'+Date.now());
const host=await startStudio({directory});let client,page;const errors=[];
const api=async(operation,params={})=>{const response=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})});const result=await response.json();if(result.error)throw Error(result.error);return result.value;};
const library=()=>api('editor.library');
try{
 const initial=await api('state'),catalog=await api('catalog');let document=await api('template',{kind:'node',options:{id:'a',name:'测试节点'},document:initial.live.document});
 const a=document.network.nodes.find(n=>n.node_id==='a'),agent=document.network.nodes.find(n=>n.node_id==='root');
 a.offered_tools=catalog.tools.slice(0,2).map(t=>({ref:t.ref,channels:['tools']}));agent.offered_tools=catalog.tools.slice(0,1).map(t=>({ref:t.ref,channels:['tools']}));
 for(const node of [a,agent])node.modules['metadata.fields']=structuredClone(catalog.modules['metadata.fields'].defaults);
 const layout={root:{x:0,y:0},a:{x:210,y:0}};await api('apply',{document,base_commit:initial.live.commit,layout});
 const snapshot=copySubnet(document,['a'],'internal',layout),books=Array.from({length:4},(_,i)=>({id:'book-'+i,name:'书签 '+i,mode:'internal',category:'default',createdAt:i,snapshot}));
 await api('editor.library.update',{action:'bookmark.patch',changes:books.map(b=>({id:b.id,expected:null,value:b}))});
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});
 page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));
 const node=id=>page.locator('.react-flow__node[data-id="'+id+'"]'),tools=node('a').getByRole('button',{name:'测试节点的工具，2 个',exact:true}),modules=node('a').getByRole('button',{name:'测试节点的模块，1 个',exact:true});
 await expect(node('a')).toBeVisible({timeout:20000});await page.locator('.brand').hover();await expect(tools).toBeHidden();await expect(modules).toBeHidden();
 const before=await node('a').boundingBox();await node('a').hover();await expect(tools).toBeVisible();await expect(modules).toBeVisible();await expect(page.locator('.node-details')).toHaveCount(0);
 await expect(node('a').locator('.node-actions button')).toHaveCount(2);for(const button of [tools,modules]){await expect(button.locator('svg')).toHaveCount(1);await expect(button.locator('span')).toHaveCount(1);}
 expect((await node('a').boundingBox()).width).toBe(before.width);expect((await node('a').boundingBox()).height).toBe(before.height);
 await page.screenshot({path:path.join(directory,'01-circular-node-actions.png')});
 // 分别点同一按钮里的图标和数字，均直接打开相应页，不启动 Agent。
 await tools.locator('svg').click();await expect(page.locator('.inspector-tabs button.active')).toHaveText('工具');await expect(page.getByLabel('添加节点工具',{exact:true})).toBeVisible();await page.waitForTimeout(400);await expect(page.locator('.inspector-tabs button.active')).toHaveText('工具');
 await modules.locator('span').click();await expect(page.locator('.inspector-tabs button.active')).toHaveText('模块');await expect(page.locator('.module-section')).toHaveCount(1);
 await page.locator('.brand').hover();await expect(modules).toBeVisible();
 await page.locator('.right-panel .module-section>summary').click();await page.getByRole('button',{name:'卸载模块',exact:true}).click();await expect(node('a').getByRole('button',{name:'测试节点的模块，0 个',exact:true})).toBeVisible();
 await node('root').hover();const agentTools=node('root').getByRole('button',{name:'DataNet根节点的工具，1 个',exact:true});await agentTools.click();await page.waitForTimeout(400);await expect(page.locator('.inspector-tabs button.active')).toHaveText('工具');await expect(page.locator('.chat-overlay')).toHaveCount(0);await expect(node('root')).toHaveClass(/selected/);
 await page.locator('.react-flow__pane').dispatchEvent('click');await page.locator('.brand').hover();await expect(agentTools).toBeHidden();await expect(page.getByRole('button',{name:'展开右侧栏',exact:true})).toBeVisible();
 // 鼠标只定位一次，删除后不移动：后续按键继续命中补位后的书签。
 const history=(await library()).history.map(e=>e.kind+e.id);await page.locator('.bookmark-card').first().hover();
 for(let remaining=3;remaining>=0;remaining--){await page.keyboard.press('a');await expect.poll(async()=>(await library()).bookmarks.length).toBe(remaining);}
 expect((await library()).history.map(e=>e.kind+e.id)).toEqual(history);
 // 书签和点选不入撤销历史：撤销直接回到之前的模块卸载，书签保持删除。
 await page.keyboard.press('Control+z');await node('a').hover();await expect(node('a').getByRole('button',{name:'测试节点的模块，1 个',exact:true})).toBeVisible();expect((await library()).bookmarks.length).toBe(0);
 await page.keyboard.press('Control+y');await expect(node('a').getByRole('button',{name:'测试节点的模块，0 个',exact:true})).toBeVisible();expect((await library()).bookmarks.length).toBe(0);
 await node('a').click();await node('a').hover();for(const key of ['a','b','a','b'])await page.keyboard.press(key);await expect(page.locator('.bookmark-card')).toHaveCount(4);
 await page.locator('.bookmark-card').first().hover();for(const key of ['a','b','a','b'])await page.keyboard.press(key);await expect.poll(async()=>(await library()).bookmarks.length).toBe(0);
 await page.keyboard.press('a');await expect.poll(async()=>(await library()).bookmarks.length).toBe(0);expect(errors).toEqual([]);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,noSquarePreview:true,fixedCircleSize:true,twoCombinedButtons:true,hoverOrSelectionOnly:true,iconAndNumberBothClickable:true,toolsAndModulesTabs:true,liveCounts:true,agentTabStable:true,stationaryRepeatedDeletion:true,fastAlternatingDeletion:true,undoSkipsBookmarksAndSelection:true,historyUnchanged:true,modelCalls:0,errors},null,2));console.log('PASS 圆形节点快捷按钮和静止悬停连续删除：'+directory);
}catch(error){if(page)await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});throw error;}finally{if(client)await client.close();await host.close();}
