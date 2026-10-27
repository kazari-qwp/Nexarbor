// 真实 Python 后端与 Electron；仅使用独立 E 盘测试工作区，不调用模型。
import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/stored-nodes-e2e-'+Date.now());
let host=await startStudio({directory}),client,page;const errors=[];
const api=async(operation,params={})=>{const r=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})}),result=await r.json();if(result.error)throw Error(result.error);return result.value;};
const library=()=>api('editor.library'),tree=()=>page.locator('[data-resource-library="node"]'),item=id=>tree().locator('[data-resource-id="'+id+'"]'),book=id=>page.locator('[data-bookmark-id="'+id+'"]'),canvas=()=>page.locator('.node-link-gesture');
const folder=name=>tree().getByRole('button',{name:'节点文件夹 '+name,exact:true});
const launch=async()=>{const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));await expect(canvas()).toBeVisible({timeout:20000});await tree().locator(':scope>summary').click();};
const saveDraft=async()=>{await page.getByRole('button',{name:'保存',exact:true}).click();await expect(page.getByRole('button',{name:'保存',exact:true})).toBeEnabled();return (await api('state')).draft.document;};
const drop=async source=>{const before=await page.locator('.react-flow__node').count();await source.dragTo(canvas(),{targetPosition:{x:450,y:280}});await expect(page.locator('.react-flow__node')).toHaveCount(before+1);return saveDraft();};
const copy=async key=>{await page.locator('.react-flow__node[data-id="configured"]').click();await canvas().hover({position:{x:200,y:350}});const before=(await library()).bookmarks.length;await page.keyboard.press(key);await expect.poll(async()=>(await library()).bookmarks.length).toBe(before+1);return (await library()).bookmarks[0];};
try{
 const initial=await api('state'),catalog=await api('catalog');let document=initial.live.document;
 for(const [kind,id,name] of [['agent','configured','资料管理员'],['node','outside','外部地点']])document=await api('template',{kind,options:{id,name},document});
 const actor=document.network.nodes.find(n=>n.node_id==='configured'),tool=catalog.tools.find(t=>t.ref.startsWith('harness:'));expect(tool).toBeTruthy();
 actor.description='携带记录、工具和文档';actor.divergence=3;actor.offered_tools=[{ref:tool.ref,channels:['tools','local']}];
 actor.modules['records.store']={...structuredClone(catalog.modules['records.store'].defaults),config:{initial:{coins:10},references:[],minimum:{}},state:{values:{coins:27,bag:['面包']},references:[],receipts:[]}};
 actor.connections.interfaces=[{target_node_id:'outside',metadata:{channels:['tools'],threshold:0,multiplier:1,attributes:{label:'到地点'}}}];document.files[actor.parameters.file_path]='这个节点独有的资料正文';
 const applied=await api('apply',{document,base_commit:initial.live.commit,layout:{root:{x:0,y:0},configured:{x:200,y:0},outside:{x:440,y:0}}});expect(applied.valid).toBe(true);
 await api('editor.library.update',{action:'asset.folder.create',kind:'node',id:'places',name:'地点',parent:'stored-nodes'});
 await launch();await expect(folder('官方节点')).toBeVisible();await expect(folder('已保存节点')).toBeVisible();await folder('官方节点').dblclick();await expect(item('node')).toBeVisible();
 // A 通过 S 保存；即使浏览官方目录，自制节点也只进入已保存节点。
 const a=await copy('a');await book(a.id).hover();await page.keyboard.press('s');await expect.poll(async()=>(await library()).nodeTemplates.length).toBe(1);
 const savedA=(await library()).nodeTemplates[0];expect((await library()).assets.node.items[savedA.id].folder).toBe('stored-nodes');expect((await library()).history).toEqual([]);
 expect(savedA.snapshot.nodes[0].modules['records.store'].state.values.coins).toBe(27);expect(savedA.snapshot.nodes[0].offered_tools).toEqual(actor.offered_tools);expect(savedA.snapshot.files[savedA.snapshot.nodes[0].parameters.file_path]).toBe('这个节点独有的资料正文');expect(savedA.snapshot.nodes[0].connections.interfaces).toEqual([]);
 await tree().getByRole('button',{name:'全部节点',exact:true}).click();await folder('已保存节点').dblclick();await expect(item(savedA.id)).toBeVisible();await folder('地点').dblclick();
 // B 通过右键保存到当前自建分类，并保留原外联；重复保存覆盖同一文件。
 const b=await copy('b');await book(b.id).click({button:'right'});await page.getByRole('menuitem',{name:'保存书签至节点栏',exact:true}).click();await expect.poll(async()=>(await library()).nodeTemplates.length).toBe(2);
 const savedB=(await library()).nodeTemplates.find(n=>n.originBookmark===b.id);expect((await library()).assets.node.items[savedB.id].folder).toBe('places');await expect(item(savedB.id)).toBeVisible();expect(savedB.snapshot.nodes[0].connections.interfaces[0].target_node_id).toBe('outside');
 await book(b.id).hover();await page.keyboard.press('s');await expect.poll(async()=>(await library()).version).toBeGreaterThan(5);expect((await library()).nodeTemplates).toHaveLength(2);expect((await library()).history).toEqual([]);
 await item(savedB.id).click();const details=page.getByLabel('节点模板详情',{exact:true});await expect(details).toContainText('磁盘节点文件');await expect(details.getByLabel('模板节点文档',{exact:true})).toHaveValue('这个节点独有的资料正文');
 let placed=await drop(item(savedB.id));const first=placed.network.nodes.at(-1);expect(first.name).toBe('资料管理员');expect(first.modules['records.store'].state.values).toEqual({coins:27,bag:['面包']});expect(first.offered_tools).toEqual(actor.offered_tools);expect(first.connections.interfaces[0].target_node_id).toBe('outside');expect(placed.files[first.parameters.file_path]).toBe('这个节点独有的资料正文');
 placed=await drop(item(savedB.id));const second=placed.network.nodes.at(-1);expect(second.node_id).not.toBe(first.node_id);expect(second.parameters.file_path).not.toBe(first.parameters.file_path);expect(new Set(placed.network.nodes.map(n=>n.node_id)).size).toBe(placed.network.nodes.length);
 const before=(await library()).history;await tree().getByRole('button',{name:'归档节点 资料管理员',exact:true}).click();await expect(item(savedB.id)).toHaveCount(0);expect((await library()).history).toEqual(before);
 await client.evaluate(({Menu})=>Menu.getApplicationMenu().items.find(i=>i.label==='归档').click());const archive=page.getByRole('dialog',{name:'资源归档',exact:true});await expect(archive.getByRole('button',{name:'检查删除 资料管理员',exact:true})).toBeEnabled();await archive.getByRole('button',{name:'恢复 资料管理员',exact:true}).click();await archive.getByRole('button',{name:'关闭资源归档',exact:true}).click();await expect(item(savedB.id)).toBeVisible();expect((await library()).history).toEqual(before);
 // 独立快照不依赖原节点或原书签；重开整个后端后仍可拖入。
 await api('editor.library.update',{action:'bookmark.patch',changes:[{id:b.id,expected:b,value:null}]});
 await page.screenshot({path:path.join(directory,'node-library.png')});await client.close();client=null;await host.close();host=await startStudio({directory});await launch();await folder('已保存节点').dblclick();await folder('地点').dblclick();await expect(item(savedB.id)).toBeVisible();
 placed=await drop(item(savedB.id));const restored=placed.network.nodes.at(-1);expect(restored.modules['records.store'].state.values.coins).toBe(27);expect(placed.files[restored.parameters.file_path]).toBe('这个节点独有的资料正文');expect((await library()).nodeTemplates.find(n=>n.id===savedB.id).snapshot).toEqual(savedB.snapshot);
 expect(errors).toEqual([]);await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,officialSeparation:true,bookmarkShortcutAndMenu:true,currentVirtualFolder:true,fullNodeConfigAndState:true,toolsAndChannels:true,independentDocuments:true,abLinks:true,freshIds:true,archiveRestore:true,historyStable:true,coldRestart:true,modelCalls:0,errors},null,2));console.log('PASS 节点预设真实客户端：'+directory);
}catch(error){if(page&&!page.isClosed()){await page.screenshot({path:path.join(directory,'failed.png')});await fs.writeFile(path.join(directory,'failed.txt'),await page.locator('body').innerText());}throw error;}finally{if(client)await client.close();await host.close();}
