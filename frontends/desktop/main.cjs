const {app,BrowserWindow,dialog,Menu,MenuItem,shell}=require('electron');
const fs=require('node:fs'),path=require('node:path');
const {readConnection,localNavigation,activeConnection}=require('./connection.cjs');
const {WorkspaceSession}=require('./workspace-session.cjs');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');
app.setName('Nexarbor Workbench');let window,studio,closing=false,workspaceHome;
const started=performance.now(),retiring=new Set(),startup={};let transition=Promise.resolve(),desktopSession,projectMode=process.argv.some(value=>value==='--project'||value.startsWith('--project='));
function enqueueStart(fn){const next=transition.catch(()=>{}).then(()=>closing?undefined:fn());transition=next;return next;}
function open(...args){return enqueueStart(()=>startOpen(...args));}
function development(...args){return enqueueStart(()=>startDevelopment(...args));}
function openStoredNetwork(...args){return enqueueStart(()=>startStoredNetwork(...args));}
function record(name){startup[name]=Math.round(performance.now()-started);if(workspaceHome)fs.promises.writeFile(path.join(workspaceHome,'desktop-startup-timings.json'),JSON.stringify(startup,null,2)).catch(()=>{});}
function progress(message){
 if(!window||window.isDestroyed())return;
 window.webContents.executeJavaScript(`(()=>{let el=document.getElementById("stage");if(!el){const canvas=document.querySelector(".node-link-gesture");if(!canvas)return;el=document.getElementById("network-transition");if(!el){el=document.createElement("div");el.id="network-transition";el.setAttribute("role","status");el.style.cssText="position:absolute;inset:0;z-index:1000;background:#101720e8;display:grid;place-content:center;justify-items:center;gap:14px;color:#a6e1d1;font:14px Segoe UI";const spinner=document.createElement("span");spinner.style.cssText="width:26px;height:26px;border:2px solid #33464e;border-top-color:#83d5bf;border-radius:50%";spinner.animate([{transform:"rotate(0deg)"},{transform:"rotate(360deg)"}],{duration:850,iterations:Infinity});el.append(spinner,document.createElement("span"));canvas.append(el);}el=el.lastElementChild;}el.textContent=${JSON.stringify(message)};})()`).catch(()=>{});
}
async function clearProgress(){if(window&&!window.isDestroyed())await window.webContents.executeJavaScript('document.getElementById("network-transition")?.remove()').catch(()=>{});}
async function restoreStudio(){if(!studio||window.isDestroyed())return;try{if(new URL(window.webContents.getURL()).origin!==new URL(studio.url).origin)await window.loadURL(studio.url);}finally{await clearProgress();}}
async function flushPage(){if(window&&!window.isDestroyed()&&localNavigation(window.webContents.getURL()))await window.webContents.executeJavaScript('window.nexarborWorkspace?.flush()');}
async function activate(url,next,spec=next?.launchSpec){if(closing||window.isDestroyed()){await next?.close();return;}const previous=studio;await flushPage();if(window.webContents.getURL().split('#')[0]!==url.split('#')[0])await window.loadURL(url);studio=next;if(spec&&desktopSession)await desktopSession.remember(spec);await clearProgress();record("networkLoaded");if(previous&&previous!==next){const job=previous.close().catch(error=>{startup.retirementError=error.message;}).finally(()=>retiring.delete(job));retiring.add(job);}}
const flag=name=>{const i=process.argv.indexOf(name);return i>=0?process.argv[i+1]:process.argv.find(value=>value.startsWith(name+'='))?.slice(name.length+1);};
const userData=flag('--user-data-dir');if(userData){fs.mkdirSync(path.resolve(userData),{recursive:true});app.setPath('userData',path.resolve(userData));}
const primary=app.requestSingleInstanceLock({project:flag('--project')??null});
if(!primary)app.quit();
else app.on('second-instance',(_event,argv,_workingDirectory,additionalData)=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}const index=argv.indexOf('--project'),chosen=additionalData?.project??(index>=0?argv[index+1]:argv.find(value=>value.startsWith('--project='))?.slice(10));if(chosen){switchProject(chosen).catch(error=>dialog.showErrorBox('无法打开项目',error.message));}});

function projectRoot(){
 for(const start of [process.env.NEXARBOR_ROOT,__dirname].filter(Boolean)){
  let directory=path.resolve(start);
  for(let i=0;i<9;i++){if(fs.existsSync(path.join(directory,'adapters/harness/studio/host.mjs')))return directory;const parent=path.dirname(directory);if(parent===directory)break;directory=parent;}
 }
 throw Error('找不到项目开发后端。请设置 NEXARBOR_ROOT 指向包含源码和Python运行时的目录。');
}
async function startWorkspace(spec){
 let next;
 try{
  progress('正在恢复网络…');record('backendStarting');
  if(studio&&path.resolve(studio.directory)===path.resolve(spec.directory)){await activate(studio.url,studio,spec);return;}
  const connection=await activeConnection(path.join(spec.directory,'editor-connection.json'));
  if(connection){await activate(connection,null,spec);return;}
  const root=projectRoot(),{startStudio}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href);
  next=await startStudio({...spec,projectDirectory:workspaceHome,onOpenProject:chooseProject,onRevealFile:file=>{shell.showItemInFolder(file);return {revealed:true};},onOpenNetwork:openStoredNetwork,onImportNetwork:bundle=>enqueueStart(()=>startImportedNetwork(bundle)),onProgress:progress});next.launchSpec=spec;record('backendReady');await activate(next.url,next,spec);
 }catch(error){
  if(next&&next!==studio)await next.close().catch(()=>{});
  if(error.message.includes('runtime.lock'))for(let attempt=0;attempt<6;attempt++){const connection=await activeConnection(path.join(spec.directory,'editor-connection.json'));if(connection){await activate(connection,null,spec);return;}await new Promise(resolve=>setTimeout(resolve,400));}
  if(closing)return;if(studio)await restoreStudio();else progress('工作区暂未就绪，请从工作台菜单重试');
  await dialog.showMessageBox(window,{type:'error',title:'工作台未启动',message:error.message});
 }
}
async function startDevelopment(profile,{useWorkspace=false}={}){
 const root=projectRoot();workspaceHome??=path.resolve(flag('--project')??flag('--workspace')??process.env.NEXARBOR_WORKSPACE??path.join(root,'build/workbench-v3'));desktopSession??=new WorkspaceSession(workspaceHome);
 if(useWorkspace&&!profile&&!flag('--network')){const saved=await desktopSession.read();if(saved.last){await startWorkspace(saved.last);return;}}
 const defaultDirectory=(!projectMode&&flag('--workspace')||fs.existsSync(path.join(workspaceHome,'checkpoints.sqlite3')))?workspaceHome:path.join(workspaceHome,'.nexarbor/runs/main');
 let spec={directory:defaultDirectory,...(flag('--network')?{initialNetwork:path.resolve(flag('--network'))}:{})};
 if(profile){const base=path.dirname(path.resolve(profile)),config=JSON.parse(await fs.promises.readFile(profile,'utf8')),application=path.dirname(base)===path.join(root,'configs')?path.basename(base):undefined;
  const fallback=path.resolve(base,config.runtime_directory??'runtime'),directory=useWorkspace&&flag('--workspace')?workspaceHome:application?await desktopSession.application(application):fallback;
  const relative=path.relative(path.join(root,'build'),directory),inWorkspace=directory===workspaceHome||directory.startsWith(workspaceHome+path.sep);if(!inWorkspace&&(relative.startsWith('..')||path.isAbsolute(relative)))throw Error('应用运行目录须位于项目 build 内；其他目录请显式指定 --workspace');
  spec={directory,application,initialNetwork:config.network?path.resolve(base,config.network):undefined,components:config.components??[],templates:config.templates?JSON.parse(await fs.promises.readFile(path.resolve(base,config.templates),'utf8')):[]};
 }
 await startWorkspace(spec);
}
async function startStoredNetwork(preset){
 const root=projectRoot(),key=preset.application??createHash('sha256').update(preset.file).digest('hex').slice(0,20);
 if(!/^[a-zA-Z0-9_-]+$/.test(key))throw Error('完整网络标识无效');
 const directory=preset.application?await desktopSession.application(preset.application):path.join(workspaceHome,'.nexarbor/runs',key);
 await startWorkspace({directory,application:preset.application,initialNetwork:preset.file,components:preset.runtime?.components??[],templates:preset.runtime?.templates??[]});
}
async function startImportedNetwork(bundle){
 let next;
 try{
  progress('正在导入网络和 Agent 上下文…');
  const root=projectRoot(),{startStudio}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href),spec={directory:path.join(workspaceHome,'.nexarbor/runs','import-'+require('node:crypto').randomUUID()),components:bundle.runtime?.components??[],templates:bundle.runtime?.templates??[]};
  const document=bundle.format==='nexarbor-network/v1'?bundle.document:bundle;
  if(!Array.isArray(document?.network?.nodes))throw Error('网络文件缺少节点列表');
  const {editorNode}=await import(pathToFileURL(path.join(root,'adapters/harness/framework/editor-nodes.js')).href);await fs.promises.mkdir(spec.directory,{recursive:true});
  // 固定模板先登记现有节点身份；业务配置与上下文在校验更新时一起装配。
  const bootstrap=path.join(spec.directory,'import-bootstrap.json');await fs.promises.writeFile(bootstrap,JSON.stringify({network:{version:8,nodes:document.network.nodes.map(n=>editorNode('node',n.node_id,n.name)),signals:{},delegations:[]},files:{}}));
  next=await startStudio({...spec,projectDirectory:workspaceHome,onOpenProject:chooseProject,onRevealFile:file=>{shell.showItemInFolder(file);return {revealed:true};},initialNetwork:bootstrap,onOpenNetwork:openStoredNetwork,onImportNetwork:value=>enqueueStart(()=>startImportedNetwork(value)),onProgress:progress});await next.request('workspace.import.local',{bundle});next.launchSpec=spec;await activate(next.url,next,spec);
 }catch(error){await next?.close().catch(()=>{});await clearProgress();await dialog.showMessageBox(window,{type:'error',title:'无法导入网络',message:error.message});}
}
async function choose(){const result=await dialog.showOpenDialog(window,{title:'选择工作台连接记录',properties:['openFile'],filters:[{name:'工作台连接',extensions:['json']}]});if(!result.canceled)await open(result.filePaths[0]);}
async function switchProject(directory){const chosen=path.resolve(directory.replace(/^"(.*)"$/,'$1'));await flushPage();workspaceHome=chosen;projectMode=true;desktopSession=new WorkspaceSession(chosen);await development(undefined,{useWorkspace:true});}
async function chooseProject(){const result=await dialog.showOpenDialog(window,{title:'打开 Nexarbor 项目文件夹',properties:['openDirectory','createDirectory']});if(!result.canceled)await switchProject(result.filePaths[0]);}
async function chooseProfile(){const result=await dialog.showOpenDialog(window,{title:'选择应用配置（profile.json）',properties:['openFile'],filters:[{name:'应用配置',extensions:['json']}]});if(!result.canceled)await development(result.filePaths[0]);}
async function startOpen(file){
 try{workspaceHome??=path.dirname(path.resolve(file));desktopSession??=new WorkspaceSession(workspaceHome);const url=readConnection(file);await activate(url,null);fs.writeFileSync(path.join(app.getPath('userData'),'last-connection.json'),JSON.stringify({file:path.resolve(file)}));}
 catch(error){await dialog.showMessageBox(window,{type:'error',title:'无法打开工作台',message:'请先在 Harness 中启动工作台后重试。',detail:error.message});}
}
if(primary)app.whenReady().then(async()=>{
 window=new BrowserWindow({width:1500,height:960,minWidth:1000,minHeight:680,title:'Nexarbor · 网络工作台',backgroundColor:'#101720',show:true,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
 // 先完成最后一次页面写入，再销毁窗口，覆盖右上角关闭按钮的退出路径。
 window.on('close',event=>{if(!closing){event.preventDefault();setImmediate(()=>app.quit());}});
 record('windowCreated');window.once('ready-to-show',()=>{window.show();record('firstFrame');});
 await window.loadFile(path.join(__dirname,'loading.html'));
 window.webContents.on('page-title-updated',event=>{event.preventDefault();window.setTitle('Nexarbor · 网络工作台');});
 window.webContents.on('will-navigate',(event,url)=>{if(!localNavigation(url))event.preventDefault();});
 window.webContents.setWindowOpenHandler(({url})=>{try{const target=new URL(url);if(['https:','http:'].includes(target.protocol)&&!localNavigation(url))shell.openExternal(url);}catch{}return {action:'deny'};});
 window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'工作台',submenu:[{label:'打开项目文件夹…',click:chooseProject},{label:'打开应用配置…',click:chooseProfile},{label:'打开工作台连接…',click:choose},{label:'刷新',role:'reload'},{type:'separator'},{role:'quit',label:'退出'}]},{label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},{label:'视图',submenu:[{role:'togglefullscreen',label:'全屏'},{role:'toggleDevTools',label:'开发者工具'}]},{label:'归档',click:()=>window.webContents.executeJavaScript("window.dispatchEvent(new Event('nexarbor-open-archive'))")} ]));
 const examples=new Menu();for(const [label,name] of [['NPC小镇','npc_town_v3'],['固定讨论与协作组','fixed_groups_v3'],['知识归档与恢复','knowledge_v3']])examples.append(new MenuItem({label,click:()=>development(path.join(projectRoot(),'configs',name,'profile.json'))}));Menu.getApplicationMenu().items[0].submenu.insert(0,new MenuItem({label:'示例应用',submenu:examples}));
 let file=flag('--connection');
 if(file)await open(file);else await development(flag('--profile'),{useWorkspace:true});
 if(!window.isDestroyed()&&!window.isVisible())window.show();
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(closing)return;event.preventDefault();closing=true;transition.catch(()=>{}).then(async()=>{await flushPage();record('pageSavedOnQuit');}).catch(error=>{startup.saveError=error.message;record('pageSaveFailedOnQuit');}).then(()=>Promise.allSettled([studio?.close(),...retiring])).finally(()=>app.quit());});
