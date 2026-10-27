// 真实 Python 服务与 Electron，资源整理和复制全流程，不调用模型。
import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
import {startStudio} from '../../../adapters/harness/studio/host.mjs';
import {copySubnet} from '../src/subnets.js';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=path.join(root,'build/unified-resources-e2e-'+Date.now());
let host=await startStudio({directory}),client,page;const errors=[];
const api=async(operation,params={})=>{const response=await fetch('http://'+host.authority+'/api',{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':new URL(host.url).hash.slice(7)},body:JSON.stringify({operation,params})});const result=await response.json();if(result.error)throw Error(result.error);return result.value;};
const library=()=>api('editor.library'),tree=kind=>page.locator('[data-resource-library="'+kind+'"]'),item=(kind,id)=>tree(kind).locator('[data-resource-id="'+id+'"]'),book=id=>page.locator('[data-bookmark-id="'+id+'"]'),canvas=()=>page.locator('.node-link-gesture');
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const launch=async()=>{client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir='+path.join(directory,'desktop-profile')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));await expect(canvas()).toBeVisible({timeout:20000});};
const draft=async()=>{await page.getByRole('button',{name:'保存',exact:true}).click();await expect(page.getByRole('button',{name:'保存',exact:true})).toBeEnabled();return (await api('state')).draft.document;};
const drop=async(source,count,x=430,y=320)=>{const before=await page.locator('.react-flow__node').count();await source.dragTo(canvas(),{targetPosition:{x,y}});await expect(page.locator('.react-flow__node')).toHaveCount(before+count);return draft();};
const openTree=async kind=>{if(!await tree(kind).evaluate(e=>e.open))await tree(kind).locator(':scope>summary').click();};
try{
 const initial=await api('state');let document=initial.live.document;
 for(const [id,kind] of [['a','text_file'],['b','node'],['c','node']])document=await api('template',{kind,options:{id,name:'节点 '+id},document});
 document.files['data/a.md']='独立缓存的文档';
 for(const [source,target] of [['a','b'],['b','a'],['a','c']])document=await api('connect',{document,connection:{source,target,channels:['links'],threshold:1,multiplier:1}});
 const layout={root:{x:0,y:0},a:{x:180,y:0},b:{x:360,y:120},c:{x:540,y:0}};await api('apply',{document,base_commit:initial.live.commit,layout});
 const books=['internal','external'].map((mode,i)=>({id:mode,name:mode==='internal'?'内部网络':'保留外联网络',mode,createdAt:i,category:'default',snapshot:copySubnet(document,['a','b'],mode,layout)}));
 await api('editor.library.update',{action:'bookmark.patch',changes:books.map(b=>({id:b.id,value:b}))});
 for(const [kind,id,name] of [['module','maker','制作目录'],['preset','dest','预设目录']])await api('editor.library.update',{action:'asset.folder.create',kind,id,name});
 await launch();
 for(const kind of ['node','tool','module','preset'])await expect(tree(kind)).not.toHaveAttribute('open','');
 await expect(page.locator('.left-panel .palette-item')).toHaveCount(0);
 // 左侧基础节点只预览和编辑，不进场；保存配置为独立书签。
 await openTree('node');await tree('node').getByRole('button',{name:'节点文件夹 官方节点',exact:true}).dblclick();await item('node','text_file').click();const detail=page.getByLabel('节点模板详情',{exact:true});await expect(detail).toBeVisible();expect(await page.locator('.react-flow__node').count()).toBe(4);
 await detail.getByLabel('资源书签名称',{exact:true}).fill('文字模板');await detail.getByLabel('模板节点名称',{exact:true}).fill('资料节点');await detail.getByLabel('模板节点文档',{exact:true}).fill('模板正文');
 await detail.getByRole('button',{name:'Save · 保存至书签',exact:true}).click();await expect.poll(async()=>(await library()).bookmarks.length).toBe(3);expect((await library()).history).toEqual([]);
 const textBook=(await library()).bookmarks.find(b=>b.name==='文字模板');let placed=await drop(book(textBook.id),1,560,220);let added=placed.network.nodes.at(-1);expect(added.name).toBe('资料节点');expect(placed.files[added.parameters.file_path]).toBe('模板正文');
 const once=(await library()).history.find(h=>h.snapshot?.nodes[0]?.name==='资料节点');expect(once).toBeTruthy();
 placed=await drop(item('node','node'),1,560,380);const basicId=placed.network.nodes.at(-1).node_id;expect(placed.network.nodes.at(-1).name).toBe('普通节点');
 placed=await drop(book(textBook.id),1,720,220);expect(placed.network.nodes.at(-1).node_id).not.toBe(added.node_id);
 await expect.poll(async()=>(await library()).history[0]?.snapshot?.nodes[0]?.name).toBe('资料节点');expect((await library()).history.filter(h=>h.snapshot?.nodes.length===1&&h.snapshot.nodes[0].name==='资料节点')).toHaveLength(1);
 expect((await library()).history[1].snapshot.nodes[0].name).toBe('普通节点');
 // A/B 内部引用均到新节点，B 外部引用仍到 c；同配置重复拖动历史不刷屏。
 for(const mode of ['internal','external']){
  placed=await drop(book(mode),2,360,400);const [a,b]=placed.network.nodes.slice(-2);
  expect(a.name).toBe('节点 a');expect(b.name).toBe('节点 b');expect(a.connections.interfaces[0].target_node_id).toBe(b.node_id);expect(b.connections.interfaces[0].target_node_id).toBe(a.node_id);
  expect(a.connections.interfaces.slice(1).map(l=>l.target_node_id)).toEqual(mode==='external'?['c']:[]);expect(placed.files[a.parameters.file_path]).toBe('独立缓存的文档');
 }
 const count=(await library()).history.length;await drop(book('external'),2,450,450);await expect.poll(async()=>(await library()).history.length).toBe(count);
 const cachedNetwork=(await library()).history.find(h=>h.kind==='network'&&h.mode==='external');expect(cachedNetwork.snapshot.nodes[0].connections.interfaces[1].target_node_id).toBe('c');
 // 当前预设目录：S 与右键保存都保留原始快照；再次保存不会重复登记。
 await openTree('preset');await tree('preset').getByRole('button',{name:'网络预设文件夹 预设目录',exact:true}).dblclick();await book('external').hover();await page.keyboard.press('s');await expect.poll(async()=>(await library()).presets.length).toBe(1);
 let preset=(await library()).presets[0];expect(preset.snapshot).toEqual(books[1].snapshot);expect(preset.mode).toBe('external');expect((await library()).assets.preset.items[preset.id].folder).toBe('dest');
 await book('external').click({button:'right'});await page.getByRole('menuitem',{name:'保存书签至网络预设',exact:true}).click();await expect.poll(async()=>(await library()).presets.length).toBe(1);
 await book('internal').click({button:'right'});await page.getByRole('menuitem',{name:'保存书签至网络预设',exact:true}).click();await expect.poll(async()=>(await library()).presets.length).toBe(2);
 placed=await drop(item('preset',preset.id),2,520,320);expect(placed.network.nodes.some(n=>n.node_id===basicId)).toBe(true);expect(new Set(placed.network.nodes.map(n=>n.node_id)).size).toBe(placed.network.nodes.length);
 // 多个基础节点一同拖入；整个批次可一次撤销，不影响预设资料。
 await item('node','node').click();await item('node','text_file').click({modifiers:['Control']});await drop(item('node','node'),2,500,250);await page.keyboard.press('Control+z');await expect(page.locator('.react-flow__node')).toHaveCount(placed.network.nodes.length);await page.keyboard.press('Control+y');await expect(page.locator('.react-flow__node')).toHaveCount(placed.network.nodes.length+2);
 // 制作入口在根和每层目录都有；生成工作副本记住目录，发布后归入该目录。
 await openTree('module');await expect(tree('module').getByRole('button',{name:'制作新模块',exact:true})).toBeVisible();await tree('module').getByRole('button',{name:'模块文件夹 制作目录',exact:true}).dblclick();await tree('module').getByRole('button',{name:'制作新模块',exact:true}).click();
 const studio=page.getByRole('dialog',{name:'组件工作室',exact:true});await expect(studio.getByRole('button',{name:'打开文件 module.py',exact:true})).toBeVisible();
 const work=(await api('studio.catalog')).workspaces.at(-1);expect(work.display_folder).toBe('maker');expect((await api('studio.read',{id:work.id})).display_folder).toBe('maker');
 const source=(await api('studio.read',{id:work.id})).files['module.json'],spec=JSON.parse(source);spec.id='test.folder_counter';await api('studio.save',{id:work.id,file:'module.json',content:JSON.stringify(spec),expected:createHash('sha256').update(source).digest('hex')});
 await studio.getByRole('button',{name:'重新读取',exact:true}).click();await studio.getByRole('button',{name:'验证模块',exact:true}).click();await expect(studio.getByRole('button',{name:'发布到组件库',exact:true})).toBeEnabled({timeout:30000});await studio.getByRole('button',{name:'发布到组件库',exact:true}).click();
 await expect.poll(async()=>(await library()).assets.module.items['test.folder_counter']?.folder).toBe('maker');await studio.getByRole('button',{name:'关闭组件工作室',exact:true}).click();await expect(item('module','test.folder_counter')).toBeVisible();
 await page.screenshot({path:path.join(directory,'01-unified-resources.png')});
 // 删除所有原节点和原书签，再从历史缓存拖出网络，文档、内部连接仍完整。
 for(const id of ['external','internal']){await book(id).click({button:'right'});await page.getByRole('menuitem',{name:'删除书签',exact:true}).click();await expect(book(id)).toHaveCount(0);}
 await page.getByRole('button',{name:'全选可见',exact:true}).click();await canvas().hover();await page.keyboard.press('Delete');await expect(page.locator('.react-flow__node')).toHaveCount(1);
 await page.getByRole('button',{name:'全局网络',exact:true}).click();const cached=page.locator('[data-history-kind="network"][data-history-id="'+cachedNetwork.id+'"]');await expect(cached).toBeVisible();placed=await drop(cached,2,420,250);const [a,b]=placed.network.nodes.slice(-2);
 expect(a.name).toBe('节点 a');expect(a.connections.interfaces.map(l=>l.target_node_id)).toEqual([b.node_id]);expect(b.connections.interfaces[0].target_node_id).toBe(a.node_id);expect(placed.files[a.parameters.file_path]).toBe('独立缓存的文档');
 // 保存的预设仍包含原外联，加载时 c 已不存在则清除，不污染持久化原件。
 expect((await library()).presets.find(p=>p.id===preset.id).snapshot.nodes[0].connections.interfaces[1].target_node_id).toBe('c');
 // 当前虚拟分类决定真实目录；书签保存与全网保存使用同一种磁盘网络文档。
 await tree('preset').getByRole('button',{name:'全部网络预设',exact:true}).click();await tree('preset').getByRole('button',{name:'网络预设文件夹 已存储网络',exact:true}).dblclick();
 await page.getByRole('button',{name:'全选可见',exact:true}).click();await canvas().hover();await page.keyboard.press('a');await expect.poll(async()=>(await library()).bookmarks.length).toBe(2);const fullBook=(await library()).bookmarks.find(b=>b.snapshot?.nodes.some(n=>n.node_id==='root'));
 await book(fullBook.id).hover();await page.keyboard.press('s');await expect.poll(async()=>(await library()).presets.filter(p=>p.storageKind==='network').length).toBe(1);
 const fromBook=(await library()).presets.find(p=>p.storageKind==='network');expect(path.dirname(fromBook.file)).toBe(path.join(directory,'network_presets/networks'));expect(JSON.parse(await fs.readFile(fromBook.file,'utf8')).network.nodes).toEqual(fullBook.snapshot.nodes);
 await tree('preset').getByRole('button',{name:'保存全网',exact:true}).click();const saveDialog=page.getByRole('dialog',{name:'保存全网',exact:true});await saveDialog.getByRole('textbox').fill('完整成品');await saveDialog.getByRole('button',{name:'确定',exact:true}).click();await expect.poll(async()=>(await library()).presets.filter(p=>p.storageKind==='network').length).toBe(2);
 const full=(await library()).presets.find(p=>p.name==='完整成品');expect(JSON.parse(await fs.readFile(full.file,'utf8'))).toEqual(placed);expect((await library()).assets.preset.items[full.id].folder).toBe('stored-networks');
 expect(path.dirname((await library()).presets.find(p=>p.id===preset.id).file)).toBe(path.join(directory,'network_presets/fragments'));expect(JSON.parse(await fs.readFile(path.join(directory,'editor-library.json'),'utf8')).presets).toBeUndefined();
 const loaded=await startStudio({directory:path.join(directory,'loaded-product'),initialNetwork:full.file});try{expect((await loaded.rpc('studio_state')).live.document.network.nodes.map(n=>n.node_id)).toEqual(placed.network.nodes.map(n=>n.node_id));}finally{await loaded.close();}
 const beforeRestart=(await library()).history;await client.close();client=null;await host.close();host=await startStudio({directory});await launch();expect((await library()).history).toEqual(beforeRestart);expect((await library()).assets.module.items['test.folder_counter'].folder).toBe('maker');
 await openTree('preset');await tree('preset').getByRole('button',{name:'网络预设文件夹 预设目录',exact:true}).dblclick();placed=await drop(item('preset',preset.id),2,450,320);expect(placed.network.nodes.at(-2).connections.interfaces).toHaveLength(1);expect(new Set(placed.network.nodes.map(n=>n.node_id)).size).toBe(placed.network.nodes.length);
 await page.screenshot({path:path.join(directory,'02-history-restored.png')});expect(errors).toEqual([]);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,explorerFourKinds:true,standaloneNodeEditor:true,unchangedNames:true,freshCollisionFreeIds:true,ABInternalRemapping:true,BExternalOriginal:true,independentDocumentCache:true,configurationDedup:true,MRU:true,SAndContextPresetSave:true,realPresetFiles:true,sharedProductNetworkFormat:true,virtualFolderChoosesPhysicalStorage:true,completeAndFragmentDirectories:true,fullNetworkLoadsInCore:true,rawABPreset:true,multiNodeDropUndo:true,moduleCreationOrigin:true,historyAfterSourceDeletion:true,restart:true,modelCalls:0,errors},null,2));console.log('PASS 统一资源、目录制作、A/B 拷贝与独立配置历史：'+directory);
}catch(error){if(page){await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(directory,'diagnostics.json'),JSON.stringify({errors,library:await library().catch(()=>null),state:await api('state').catch(()=>null)}));}throw error;}finally{if(client)await client.close();await host.close();}
