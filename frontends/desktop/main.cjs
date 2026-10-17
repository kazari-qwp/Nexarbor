const {app,BrowserWindow,dialog,Menu,shell}=require('electron');
const fs=require('node:fs'),path=require('node:path');
const {readConnection,localNavigation}=require('./connection.cjs');
const {pathToFileURL}=require('node:url');
app.setName('Nexarbor Workbench');let window,studio,closing=false;
function projectRoot(){
 for(const start of [process.env.NEXARBOR_ROOT,__dirname].filter(Boolean)){
  let directory=path.resolve(start);
  for(let i=0;i<9;i++){if(fs.existsSync(path.join(directory,'adapters/harness/studio/host.mjs')))return directory;const parent=path.dirname(directory);if(parent===directory)break;directory=parent;}
 }
 throw Error('找不到项目开发后端。请设置 NEXARBOR_ROOT 指向包含源码和Python运行时的目录。');
}
async function development(){
 try{
  if(!studio){const root=projectRoot();const {startStudio}=await import(pathToFileURL(path.join(root,'adapters/harness/studio/host.mjs')).href);studio=await startStudio({directory:flag('--workspace')??process.env.NEXARBOR_WORKSPACE??path.join(root,'build/workbench'),initialNetwork:flag('--network')});}
  await window.loadURL(studio.url);
 }catch(error){window.show();await dialog.showMessageBox(window,{type:'error',title:'组件工作室未启动',message:'请检查项目目录和Python运行时。',detail:error.message});}
}
const flag=name=>{const i=process.argv.indexOf(name);return i<0?undefined:process.argv[i+1];};
async function choose(){const result=await dialog.showOpenDialog(window,{title:'选择工作台连接记录',properties:['openFile'],filters:[{name:'工作台连接',extensions:['json']}]});if(!result.canceled)await open(result.filePaths[0]);}
async function open(file){
 try{const url=readConnection(file);await window.loadURL(url);fs.writeFileSync(path.join(app.getPath('userData'),'last-connection.json'),JSON.stringify({file:path.resolve(file)}));}
 catch(error){await dialog.showMessageBox(window,{type:'error',title:'无法打开工作台',message:'请先在 Harness 中启动工作台后重试。',detail:error.message});}
}
app.whenReady().then(async()=>{
 window=new BrowserWindow({width:1500,height:960,minWidth:1000,minHeight:680,title:'Nexarbor · 网络工作台',backgroundColor:'#101720',show:false,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
 window.once('ready-to-show',()=>window.show());
 window.webContents.on('page-title-updated',event=>{event.preventDefault();window.setTitle('Nexarbor · 网络工作台');});
 window.webContents.on('will-navigate',(event,url)=>{if(!localNavigation(url))event.preventDefault();});
 window.webContents.setWindowOpenHandler(({url})=>{try{const target=new URL(url);if(['https:','http:'].includes(target.protocol)&&!localNavigation(url))shell.openExternal(url);}catch{}return {action:'deny'};});
 window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'工作台',submenu:[{label:'打开工作台连接…',click:choose},{label:'刷新',role:'reload'},{type:'separator'},{role:'quit',label:'退出'}]},{label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},{label:'视图',submenu:[{role:'togglefullscreen',label:'全屏'},{role:'toggleDevTools',label:'开发者工具'}]}]));
 let file=flag('--connection');
 if(file)await open(file);else await development();
 if(!window.isVisible())window.show();
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(!studio||closing)return;event.preventDefault();closing=true;studio.close().finally(()=>app.quit());});
