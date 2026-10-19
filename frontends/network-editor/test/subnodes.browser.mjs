import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=await fs.mkdtemp(path.join(root,'build/subnode-ui-'));
let host,client,page;const errors=[];
try{
 const document=JSON.parse(await fs.readFile(path.join(root,'configs/npc_town_v3/network.json'),'utf8')),ids=['npc/lu','context/npc/lu','tools/npc/lu'];
 document.network.nodes=document.network.nodes.filter(n=>ids.includes(n.node_id));
 for(const n of document.network.nodes)n.connections.interfaces=[];
 const owner=document.network.nodes.find(n=>n.node_id===ids[0]),context=document.network.nodes.find(n=>n.node_id===ids[1]);
 Object.assign(context.modules['context.assembler'].config,{bindings:[],sources:[{id:'test','kind':'system_prompt','type':'text','text':'客户端亚节点验证'}]});
 const initial=path.join(directory,'initial.json');await fs.writeFile(initial,JSON.stringify(document));host=await startStudio({directory,initialNetwork:initial});
 const state=await host.request('state',{});await host.request('apply',{document,base_commit:state.live.commit,layout:{[ids[0]]:{x:0,y:0},[ids[1]]:{x:220,y:0},[ids[2]]:{x:220,y:120}}});
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'profile')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));
 const node=id=>page.locator('.react-flow__node[data-id="'+id+'"]');await expect(node(ids[1])).toBeVisible({timeout:20000});
 const style=await node(ids[1]).locator('.subnode').evaluate(e=>{const c=getComputedStyle(e);return {width:c.width,height:c.height,radius:c.borderRadius,color:c.backgroundColor}});expect(style.width).toBe('106px');expect(style.height).toBe('38px');expect(style.color).toBe('rgb(48, 40, 63)');
 await expect(page.locator('.react-flow__edge[data-id^="ownership:"]')).toHaveCount(2);
 await node(ids[0]).hover();await expect(node(ids[0]).getByRole('button',{name:owner.name+'的模块，'+Object.keys(owner.modules).length+' 个',exact:true})).toBeVisible();
 await node(ids[1]).hover();await node(ids[1]).getByRole('button',{name:context.name+'的模块，1 个',exact:true}).click();
 const mounted=page.locator('[data-mounted-id="context.assembler"]');await mounted.locator(':scope>summary').click();
 const frame=page.frameLocator('iframe.module-frontend-frame');await frame.locator('#preview').click();await expect(frame.locator('#result')).toContainText('客户端亚节点验证',{timeout:15000});
 await mounted.getByRole('button',{name:'切换到通用表单',exact:true}).click();const channels=mounted.locator('.channel-list');expect(await channels.count()).toBeGreaterThanOrEqual(5);
 await channels.first().getByRole('combobox').selectOption('deny');await expect(channels.first()).toContainText('空黑名单不限制频道');
 const initialInputs=await channels.first().getByRole('textbox').count();await channels.first().getByRole('button',{name:'添加频道',exact:true}).click();await expect(channels.first().getByRole('textbox')).toHaveCount(initialInputs+1);
 await node(ids[0]).click();await expect(node(ids[0])).toHaveClass(/selected/);await node(ids[0]).hover();await page.keyboard.down('Shift');await page.mouse.wheel(0,-100);await page.keyboard.up('Shift');await expect(node(ids[1])).toHaveClass(/selected/);await expect(page.locator('.react-flow__edge.selected')).toHaveCount(0);
 await page.screenshot({path:path.join(directory,'subnodes.png')});expect(errors).toEqual([]);console.log('PASS '+directory);
}catch(e){if(page&&!page.isClosed()){await page.screenshot({path:path.join(directory,'failed.png')});await fs.writeFile(path.join(directory,'failed.txt'),await page.locator('body').innerText());}console.error(errors);throw e;}finally{await client?.close();await host?.close();}
