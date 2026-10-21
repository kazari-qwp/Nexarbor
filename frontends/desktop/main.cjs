if(process.argv.includes('--network-renderer')){require('./network-view.cjs');return;}
const {app,BrowserWindow,dialog,Menu,shell,ipcMain}=require('electron');
const fs=require('node:fs'),path=require('node:path');
const {readConnection,localNavigation,activeConnection}=require('./connection.cjs');
const {WorkspaceSession}=require('./workspace-session.cjs');
const {requireProject,briefReason}=require('./project-launch.cjs');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');
const {spawn}=require('node:child_process');
async function openExternalText({file,editor}){if(editor){if(!path.isAbsolute(editor)||!editor.toLowerCase().endsWith('.exe'))throw Error('编辑器须为完整 .exe 路径');await fs.promises.access(editor);await new Promise((resolve,reject)=>{const child=spawn(editor,[file],{windowsHide:true,detached:true,stdio:'ignore'});child.once('error',reject);child.once('spawn',()=>{child.unref();resolve();});});}else{const error=await shell.openPath(file);if(error)throw Error(error);}return {opened:true};}
async function chooseText(){const value=await dialog.showOpenDialog(window,{title:'选择文本文件（项目外文件仅保存引用）',properties:['openFile'],filters:[{name:'文本',extensions:['md','txt','json','csv','yaml','yml','log','py','js']},{name:'所有文件',extensions:['*']}]});return value.canceled?{canceled:true}:{file:value.filePaths[0]};}
app.setName('Nexarbor Workbench');let window,studio,closing=false,workspaceHome;
const started=performance.now(),retiring=new Set(),startup={};let transition=Promise.resolve(),desktopSession,projectMode=process.argv.some(value=>value==='--project'||value.startsWith('--project='));
function enqueueStart(fn){const next=transition.catch(()=>{}).then(()=>closing?undefined:fn()).catch(projectFailed);transition=next;return next;}
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
const folderProject=fs.existsSync(path.join(process.cwd(),'nexarbor.json'))?process.cwd():null;projectMode||=!!folderProject;
const userData=flag('--user-data-dir');if(userData){fs.mkdirSync(path.resolve(userData),{recursive:true});app.setPath('userData',path.resolve(userData));}
const primary=app.requestSingleInstanceLock({project:flag('--project')??folderProject??null});
if(!primary)app.quit();
else app.on('second-instance',(_event,argv,_workingDirectory,additionalData)=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}const index=argv.indexOf('--project'),chosen=additionalData?.project??(index>=0?argv[index+1]:argv.find(value=>value.startsWith('--project='))?.slice(10));if(chosen){switchProject(chosen).catch(projectFailed);}});

// 所有项目打开失败统一回到项目首页；诊断独立保存，避免阻塞错误弹窗。
async function projectFailed(error){
 if(closing||!window||window.isDestroyed())return;
 const reason=briefReason(error),previous=studio,failedHome=workspaceHome;
 await flushPage().catch(()=>{});studio=null;workspaceHome=undefined;desktopSession=undefined;projectMode=false;
 await fs.promises.writeFile(path.join(app.getPath('userData'),'last-project-error.json'),JSON.stringify({time:new Date().toISOString(),project:failedHome,reason,detail:String(error?.stack??error).replace(/([#&]token=)[a-f0-9]+/gi,'$1[redacted]').slice(-16000)},null,2)).catch(()=>{});
 await window.loadFile(path.join(__dirname,'projects.html'),{hash:'reason='+encodeURIComponent(reason)});
 if(previous){const job=previous.close().catch(()=>{}).finally(()=>retiring.delete(job));retiring.add(job);}
 return {error:reason};
}
function projectRoot(){
 for(const start of [process.env.NEXARBOR_ROOT,__dirname].filter(Boolean)){
  let directory=path.resolve(start);
  for(let i=0;i<9;i++){if(fs.existsSync(path.join(directory,'adapters/harness/studio/host.mjs')))return directory;const parent=path.dirname(directory);if(parent===directory)break;directory=parent;}
 }
 throw Error('找不到工作台后端。请完整解压运行包；源码开发可设置 NEXARBOR_ROOT 指向仓库目录。');
}
async function startWorkspace(spec,startupWarnings=spec.startupWarnings??[]){
 let next;
 try{
  progress('正在恢复网络…');record('backendStarting');
  if(studio&&path.resolve(studio.directory)===path.resolve(spec.directory)){await activate(studio.url,studio,spec);return;}
  const connection=await activeConnection(path.join(spec.directory,'editor-connection.json'));
  if(connection){await activate(connection,null,spec);return;}
  const root=projectRoot(),{startStudio}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href);
  next=await startStudio({...spec,startupWarnings,projectDirectory:workspaceHome,onOpenProject:()=>projectAction('open'),onCreateProject:()=>projectAction('new'),onOpenText:openExternalText,onChooseText:chooseText,onRevealFile:file=>{shell.showItemInFolder(file);return {revealed:true};},onOpenNetwork:openStoredNetwork,onImportNetwork:bundle=>enqueueStart(()=>startImportedNetwork(bundle)),onProgress:progress});next.launchSpec=spec;record('backendReady');await activate(next.url,next,spec);
 }catch(error){
  if(next&&next!==studio)await next.close().catch(()=>{});
  if(error.message.includes('runtime.lock'))for(let attempt=0;attempt<6;attempt++){const connection=await activeConnection(path.join(spec.directory,'editor-connection.json'));if(connection){await activate(connection,null,spec);return;}await new Promise(resolve=>setTimeout(resolve,400));}
  // 运行缓存坏了也先尝试项目中独立保存的网络；旧目录完整保留。
  try{
   const root=projectRoot(),{readProjectBundle}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/project.mjs')).href),bundle=await readProjectBundle(workspaceHome);
   if(bundle){
    const {startStudio}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href),recovery={...spec,directory:path.join(workspaceHome,'.nexarbor/runs','recovery-'+require('node:crypto').randomUUID()),initialNetwork:undefined,startupWarnings:[...startupWarnings,'原运行记录无法载入，已打开项目中保存的网络。原数据目录完整保留。原因：'+briefReason(error)]};
    next=await startStudio({...recovery,projectDirectory:workspaceHome,onOpenProject:()=>projectAction('open'),onCreateProject:()=>projectAction('new'),onOpenText:openExternalText,onChooseText:chooseText,onRevealFile:file=>{shell.showItemInFolder(file);return {revealed:true};},onOpenNetwork:openStoredNetwork,onImportNetwork:bundle=>enqueueStart(()=>startImportedNetwork(bundle)),onProgress:progress});next.launchSpec=recovery;await activate(next.url,next,recovery);return;
   }
  }catch(recoveryError){if(next&&next!==studio)await next.close().catch(()=>{});error=recoveryError;}
  await projectFailed(error);
 }
}
async function startDevelopment(profile,{useWorkspace=false}={}){
 const root=projectRoot();workspaceHome??=path.resolve(flag('--project')??folderProject??flag('--workspace')??process.env.NEXARBOR_WORKSPACE??path.join(root,'build/workbench-v3'));desktopSession??=new WorkspaceSession(workspaceHome);
 if(!profile&&!flag('--network'))await requireProject(workspaceHome);
 const startupWarnings=[];
 if(useWorkspace&&!profile&&!flag('--network')){
  let saved;
  try{saved=await desktopSession.read();}catch(error){
   const {readProjectBundle}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/project.mjs')).href);if(!await readProjectBundle(workspaceHome))throw error;
   const damaged=path.join(workspaceHome,'desktop-session.json');await fs.promises.rename(damaged,damaged+'.unreadable-'+require('node:crypto').randomUUID()+'.json');startupWarnings.push('上次打开位置的记录损坏，已从项目网络恢复；原记录已保留。');saved={};
  }
  if(saved.last){await startWorkspace(saved.last);return;}
 }
 const defaultDirectory=(!projectMode&&flag('--workspace')||fs.existsSync(path.join(workspaceHome,'checkpoints.sqlite3')))?workspaceHome:path.join(workspaceHome,'.nexarbor/runs/main');
 let spec={directory:defaultDirectory,...(flag('--network')?{initialNetwork:path.resolve(flag('--network'))}:{})};
 if(profile){const base=path.dirname(path.resolve(profile)),config=JSON.parse(await fs.promises.readFile(profile,'utf8')),application=path.dirname(base)===path.join(root,'configs')?path.basename(base):undefined;
  if(config.project){workspaceHome=path.resolve(base,config.project);projectMode=true;desktopSession=new WorkspaceSession(workspaceHome);await requireProject(workspaceHome);return startWorkspace({directory:path.join(workspaceHome,'.nexarbor/runs/main')},startupWarnings);}
  const fallback=path.resolve(base,config.runtime_directory??'runtime'),directory=useWorkspace&&flag('--workspace')?workspaceHome:application?await desktopSession.application(application):fallback;
  const relative=path.relative(path.join(root,'build'),directory),inWorkspace=directory===workspaceHome||directory.startsWith(workspaceHome+path.sep);if(!inWorkspace&&(relative.startsWith('..')||path.isAbsolute(relative)))throw Error('应用运行目录须位于项目 build 内；其他目录请显式指定 --workspace');
  spec={directory,application,initialNetwork:config.network?path.resolve(base,config.network):undefined,components:config.components??[],templates:config.templates?JSON.parse(await fs.promises.readFile(path.resolve(base,config.templates),'utf8')):[]};
 }
 await startWorkspace(spec,startupWarnings);
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
  next=await startStudio({...spec,projectDirectory:workspaceHome,onOpenProject:()=>projectAction('open'),onCreateProject:()=>projectAction('new'),onOpenText:openExternalText,onChooseText:chooseText,onRevealFile:file=>{shell.showItemInFolder(file);return {revealed:true};},initialNetwork:bootstrap,onOpenNetwork:openStoredNetwork,onImportNetwork:value=>enqueueStart(()=>startImportedNetwork(value)),onProgress:progress});await next.request('workspace.import.local',{bundle});next.launchSpec=spec;await activate(next.url,next,spec);
 }catch(error){await next?.close().catch(()=>{});await clearProgress();await dialog.showMessageBox(window,{type:'error',title:'无法导入网络',message:error.message});}
}
async function choose(){const result=await dialog.showOpenDialog(window,{title:'选择工作台连接记录',properties:['openFile'],filters:[{name:'工作台连接',extensions:['json']}]});if(!result.canceled)await open(result.filePaths[0]);}
async function switchProject(directory){const chosen=path.resolve(directory.replace(/^"(.*)"$/,'$1'));await flushPage();workspaceHome=chosen;projectMode=true;desktopSession=new WorkspaceSession(chosen);await development(undefined,{useWorkspace:true});}
async function chooseProject(){const result=await dialog.showOpenDialog(window,{title:'打开 Nexarbor 项目文件夹',properties:['openDirectory','createDirectory']});if(!result.canceled){await showLoading();await switchProject(result.filePaths[0]);}return {canceled:result.canceled};}
async function showLoading(){if(!studio&&window.webContents.getURL()!==pathToFileURL(path.join(__dirname,'loading.html')).href)await window.loadFile(path.join(__dirname,'loading.html'));}
async function createProject(){
 const result=await dialog.showSaveDialog(window,{title:'新建 Nexarbor 项目文件夹',buttonLabel:'新建项目文件夹',defaultPath:path.join(workspaceHome?path.dirname(workspaceHome):app.getPath('documents'),'新建 Nexarbor 项目')});
 if(result.canceled||!result.filePath)return {canceled:true};
 const directory=path.resolve(result.filePath);
 try{const files=await fs.promises.readdir(directory);if(files.length)throw Error('请选择一个新文件夹或空文件夹，避免混入已有文件。');}catch(error){if(error.code!=='ENOENT')throw error;}
 const root=projectRoot(),{Project}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/project.mjs')).href),project=new Project(directory,path.join(directory,'.nexarbor/runs/main'),()=>{throw Error('新建项目不需要加载资源库');});
 await project.initialize();await project.commitPaths(['nexarbor.json','.gitignore','打开项目.cmd','modules','tools','node_presets','network_presets','networks'],'初始化项目');
 await showLoading();await switchProject(directory);return {created:true,path:directory};
}
async function projectAction(action){try{return await (action==='new'?createProject():chooseProject());}catch(error){return projectFailed(error);}}
function dispatch(name){if(localNavigation(window.webContents.getURL()))window.webContents.executeJavaScript('window.dispatchEvent(new Event('+JSON.stringify(name)+'))').catch(()=>{});}
async function chooseProfile(){const result=await dialog.showOpenDialog(window,{title:'选择应用配置（profile.json）',properties:['openFile'],filters:[{name:'应用配置',extensions:['json']}]});if(!result.canceled)await development(result.filePaths[0]);}
async function startOpen(file){
 try{workspaceHome??=path.dirname(path.resolve(file));desktopSession??=new WorkspaceSession(workspaceHome);const url=readConnection(file);if(!await activeConnection(file))throw Error('工作台连接已经失效');await activate(url,null);fs.writeFileSync(path.join(app.getPath('userData'),'last-connection.json'),JSON.stringify({file:path.resolve(file)}));}
 catch(error){await projectFailed(error);}
}
let harnessWindow;
async function openHarnessSettings(){
 if(harnessWindow&&!harnessWindow.isDestroyed()){harnessWindow.show();harnessWindow.focus();return;}
 harnessWindow=new BrowserWindow({parent:window,width:760,height:510,resizable:true,title:'DeepSeek Harness 路径',backgroundColor:'#101720',webPreferences:{preload:path.join(__dirname,'project-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 harnessWindow.setMenu(null);harnessWindow.on('closed',()=>{harnessWindow=undefined;});
 await harnessWindow.loadFile(path.join(__dirname,'harness-settings.html'));
}
ipcMain.handle('nexarbor-harness',async(event,action,executable)=>{
 const sender=event.senderFrame?.url??'',page=pathToFileURL(path.join(__dirname,'harness-settings.html')).href;
 if(action==='open'){
  if(event.sender!==window?.webContents||!(localNavigation(sender)||sender.split('#')[0]===pathToFileURL(path.join(__dirname,'projects.html')).href))throw Error('Harness 设置入口不可用');
  await openHarnessSettings();return {opened:true};
 }
 if(event.sender!==harnessWindow?.webContents||sender!==page)throw Error('Harness 设置窗口不可用');
 const root=projectRoot(),settings=await import(pathToFileURL(path.join(root,'adapters/harness/framework/harness-installation.js')).href);
 if(action==='get'){const saved=await settings.harnessSettings(),executable=await settings.harnessExecutable();let status;try{status=await settings.inspectHarnessExecutable(executable);}catch(error){status={compatible:false,error:error.message};}return {saved:saved.executable??'',executable,environment:!!process.env.DATANET_HARNESS_EXE,status};}
 if(action==='save')return settings.saveHarnessExecutable(executable);
 if(action==='browse'){const selected=await dialog.showOpenDialog(harnessWindow,{title:'选择 DeepSeek Harness.exe',properties:['openFile'],filters:[{name:'可执行文件',extensions:['exe']}]});return selected.canceled?{canceled:true}:{executable:selected.filePaths[0]};}
 throw Error('未知 Harness 设置操作');
});

ipcMain.handle('nexarbor-project',async(event,action)=>{
 const sender=new URL(event.senderFrame?.url??'about:blank');sender.hash='';sender.search='';
 if(event.sender!==window?.webContents||sender.href!==pathToFileURL(path.join(__dirname,'projects.html')).href||!['open','new'].includes(action))throw Error('项目入口不可用');
 return projectAction(action);
});
if(primary)app.whenReady().then(async()=>{
 window=new BrowserWindow({width:1500,height:960,minWidth:1000,minHeight:680,title:'Nexarbor · 网络工作台',backgroundColor:'#101720',show:true,webPreferences:{preload:path.join(__dirname,'project-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
 // 先完成最后一次页面写入，再销毁窗口，覆盖右上角关闭按钮的退出路径。
 window.on('close',event=>{if(!closing){event.preventDefault();setImmediate(()=>app.quit());}});
 record('windowCreated');window.once('ready-to-show',()=>{window.show();record('firstFrame');});
 await window.loadFile(path.join(__dirname,'loading.html'));
 window.webContents.on('page-title-updated',event=>{event.preventDefault();window.setTitle('Nexarbor · 网络工作台');});
 window.webContents.on('will-navigate',(event,url)=>{if(!localNavigation(url))event.preventDefault();});
 window.webContents.setWindowOpenHandler(({url})=>{try{const target=new URL(url);if(['https:','http:'].includes(target.protocol)&&!localNavigation(url))shell.openExternal(url);}catch{}return {action:'deny'};});
 window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'工作台',submenu:[{label:'打开项目文件夹…',click:()=>projectAction('open')},{label:'新建项目文件夹…',click:()=>projectAction('new')},{label:'打开应用配置…',click:chooseProfile},{label:'打开工作台连接…',click:choose},{label:'刷新',role:'reload'},{type:'separator'},{role:'quit',label:'退出'}]},{label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},{label:'视图',submenu:[{role:'togglefullscreen',label:'全屏'},{role:'toggleDevTools',label:'开发者工具'}]},{label:'设置',submenu:[{label:'DeepSeek Harness 路径…',click:openHarnessSettings},{label:'模型与 API',click:()=>dispatch('nexarbor-open-models')},{label:'外部文本编辑器与快捷键',click:()=>dispatch('nexarbor-open-shortcuts')},{label:'资源归档',click:()=>dispatch('nexarbor-open-archive')}]} ]));
 let file=flag('--connection');
 if(file)await open(file);else if(flag('--project')||folderProject||flag('--workspace')||flag('--profile')||flag('--network'))await development(flag('--profile'),{useWorkspace:true});else await window.loadFile(path.join(__dirname,'projects.html'));
 if(!window.isDestroyed()&&!window.isVisible())window.show();
}).catch(projectFailed);
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(closing)return;event.preventDefault();closing=true;transition.catch(()=>{}).then(async()=>{await flushPage();record('pageSavedOnQuit');}).catch(error=>{startup.saveError=error.message;record('pageSaveFailedOnQuit');}).then(()=>Promise.allSettled([studio?.close(),...retiring])).finally(()=>app.quit());});
