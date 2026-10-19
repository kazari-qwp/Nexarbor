const {app,BrowserWindow,dialog,Menu,MenuItem,shell}=require('electron');
const fs=require('node:fs'),path=require('node:path');
const {readConnection,localNavigation,activeConnection}=require('./connection.cjs');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');
app.setName('Nexarbor Workbench');let window,studio,closing=false,workspaceHome;
const flag=name=>{const i=process.argv.indexOf(name);return i>=0?process.argv[i+1]:process.argv.find(value=>value.startsWith(name+'='))?.slice(name.length+1);};
const userData=flag('--user-data-dir');if(userData){fs.mkdirSync(path.resolve(userData),{recursive:true});app.setPath('userData',path.resolve(userData));}
const primary=app.requestSingleInstanceLock();
if(!primary)app.quit();
else app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});

function projectRoot(){
 for(const start of [process.env.NEXARBOR_ROOT,__dirname].filter(Boolean)){
  let directory=path.resolve(start);
  for(let i=0;i<9;i++){if(fs.existsSync(path.join(directory,'adapters/harness/studio/host.mjs')))return directory;const parent=path.dirname(directory);if(parent===directory)break;directory=parent;}
 }
 throw Error('找不到项目开发后端。请设置 NEXARBOR_ROOT 指向包含源码和Python运行时的目录。');
}
async function development(profile,{useWorkspace=false}={}){
 let requestedDirectory;
 try{
  if(profile&&studio){await studio.close();studio=null;}
  if(!studio){
   const root=projectRoot(),override=useWorkspace&&flag('--workspace');
   const spec=profile?JSON.parse(fs.readFileSync(profile,'utf8')):null;
   const directory=path.resolve(override||(profile?path.resolve(path.dirname(profile),spec.runtime_directory??'runtime'):flag('--workspace')??process.env.NEXARBOR_WORKSPACE??path.join(root,'build/workbench-v3')));
   requestedDirectory=directory;workspaceHome??=directory;
   const connection=await activeConnection(path.join(directory,'editor-connection.json'));
   if(connection){await window.loadURL(connection);return;}
   const {startStudio,startStudioProfile}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href);
   studio=profile?await startStudioProfile(profile,{...(override?{directory}:{}),onOpenNetwork:openStoredNetwork}):await startStudio({directory,initialNetwork:flag('--network'),onOpenNetwork:openStoredNetwork});
  }
  await window.loadURL(studio.url);
 }catch(error){
  if(requestedDirectory&&error.message.includes('runtime.lock')){
   for(let attempt=0;attempt<6;attempt++){const connection=await activeConnection(path.join(requestedDirectory,'editor-connection.json'));if(connection){await window.loadURL(connection);return;}await new Promise(resolve=>setTimeout(resolve,400));}
   window.show();await dialog.showMessageBox(window,{type:'info',title:'工作区已打开',message:'该工作区正在启动或已由另一个客户端打开。请切回已有窗口。'});return;
  }
  window.show();await dialog.showMessageBox(window,{type:'error',title:'组件工作室未启动',message:'请检查项目目录和Python运行时。',detail:error.message});
 }
}
async function openStoredNetwork(preset){
 try{
  const root=projectRoot(),{startStudio}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href);
  const key=preset.application??createHash('sha256').update(preset.file).digest('hex').slice(0,20);
  if(!/^[a-zA-Z0-9_-]+$/.test(key))throw Error('完整网络标识无效');
  if(studio){await studio.close();studio=null;}
  const directory=path.join(workspaceHome??path.join(root,'build/workbench-v3'),'network_runs',key),connection=await activeConnection(path.join(directory,'editor-connection.json'));
  if(connection){await window.loadURL(connection);return;}
  studio=await startStudio({directory,initialNetwork:preset.file,components:preset.runtime?.components??[],templates:preset.runtime?.templates??[],onOpenNetwork:openStoredNetwork});
  await window.loadURL(studio.url);
 }catch(error){await dialog.showMessageBox(window,{type:'error',title:'无法打开完整网络',message:error.message});}
}
async function choose(){const result=await dialog.showOpenDialog(window,{title:'选择工作台连接记录',properties:['openFile'],filters:[{name:'工作台连接',extensions:['json']}]});if(!result.canceled)await open(result.filePaths[0]);}
async function chooseProfile(){const result=await dialog.showOpenDialog(window,{title:'选择应用配置（profile.json）',properties:['openFile'],filters:[{name:'应用配置',extensions:['json']}]});if(!result.canceled)await development(result.filePaths[0]);}
async function open(file){
 try{const url=readConnection(file);await window.loadURL(url);fs.writeFileSync(path.join(app.getPath('userData'),'last-connection.json'),JSON.stringify({file:path.resolve(file)}));}
 catch(error){await dialog.showMessageBox(window,{type:'error',title:'无法打开工作台',message:'请先在 Harness 中启动工作台后重试。',detail:error.message});}
}
if(primary)app.whenReady().then(async()=>{
 window=new BrowserWindow({width:1500,height:960,minWidth:1000,minHeight:680,title:'Nexarbor · 网络工作台',backgroundColor:'#101720',show:false,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
 window.once('ready-to-show',()=>window.show());
 window.webContents.on('page-title-updated',event=>{event.preventDefault();window.setTitle('Nexarbor · 网络工作台');});
 window.webContents.on('will-navigate',(event,url)=>{if(!localNavigation(url))event.preventDefault();});
 window.webContents.setWindowOpenHandler(({url})=>{try{const target=new URL(url);if(['https:','http:'].includes(target.protocol)&&!localNavigation(url))shell.openExternal(url);}catch{}return {action:'deny'};});
 window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'工作台',submenu:[{label:'打开应用配置…',click:chooseProfile},{label:'打开工作台连接…',click:choose},{label:'刷新',role:'reload'},{type:'separator'},{role:'quit',label:'退出'}]},{label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},{label:'视图',submenu:[{role:'togglefullscreen',label:'全屏'},{role:'toggleDevTools',label:'开发者工具'}]},{label:'归档',click:()=>window.webContents.executeJavaScript("window.dispatchEvent(new Event('nexarbor-open-archive'))")} ]));
 const examples=new Menu();for(const [label,name] of [['NPC小镇','npc_town_v3'],['固定讨论与协作组','fixed_groups_v3'],['知识归档与恢复','knowledge_v3']])examples.append(new MenuItem({label,click:()=>development(path.join(projectRoot(),'configs',name,'profile.json'))}));Menu.getApplicationMenu().items[0].submenu.insert(0,new MenuItem({label:'示例应用',submenu:examples}));
 let file=flag('--connection');
 if(file)await open(file);else await development(flag('--profile'),{useWorkspace:true});
 if(!window.isVisible())window.show();
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(!studio||closing)return;event.preventDefault();closing=true;studio.close().finally(()=>app.quit());});
