// Restricted, invisible frontend renderer. No project paths or credentials are exposed to the page.
const {app,BrowserWindow,ipcMain}=require('electron');
const path=require('node:path'),http=require('node:http'),fs=require('node:fs/promises');
const page=process.argv[process.argv.indexOf('--view-page')+1];
const home=process.argv[process.argv.indexOf('--view-home')+1];
app.setPath('userData',path.join(home,'renderer-'+process.pid));
app.commandLine.appendSwitch('disable-gpu');
let window,ready;const initialized=app.whenReady().then(async()=>{
 const folder=path.dirname(page),types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.wasm':'application/wasm'};
 const server=http.createServer(async(req,res)=>{try{const name=new URL(req.url,'http://localhost').pathname;if(!/^\/(?:network-view\.html|assets\/[a-zA-Z0-9_.-]+)$/.test(name))throw Error('Unknown resource');const bytes=await fs.readFile(path.join(folder,name.slice(1)));res.writeHead(200,{'Content-Type':types[path.extname(name)]??'application/octet-stream','Cache-Control':'no-store'});res.end(bytes);}catch{res.writeHead(404);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 app.once('will-quit',()=>server.close());
 window=new BrowserWindow({show:false,width:2400,height:1800,useContentSize:true,backgroundColor:'#101923',webPreferences:{preload:path.join(__dirname,'network-view-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false,backgroundThrottling:false,offscreen:true}});
 window.webContents.debugger.attach('1.3');
 window.webContents.on('console-message',event=>{if(event.level==='error')process.stderr.write(String(event.message)+'\n');});
 window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 window.webContents.on('will-navigate',(e,url)=>{if(url!==origin+'/network-view.html')e.preventDefault();});
 window.webContents.session.webRequest.onBeforeRequest((request,done)=>done({cancel:!request.url.startsWith(origin+'/')&&!request.url.startsWith('data:')}));

 const boot=new Promise(resolve=>ipcMain.once('network-view:boot',(event)=>{if(event.sender===window.webContents)resolve();}));
 ipcMain.on('network-view:ready',(event,value)=>{if(event.sender===window.webContents)ready?.(value);});
 await window.loadURL(origin+'/network-view.html');await boot;
});
initialized.catch(error=>{process.stderr.write(error.message+'\n');app.quit();});
async function render(value){
 await initialized;
 const size={width:1500,height:1250};
 // Windows may clamp a hidden native window to the display's work area.
 // An explicit export viewport keeps the full diagram independent of screen size.
 await window.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride',{width:size.width,height:size.height,deviceScaleFactor:1,mobile:false,screenWidth:size.width,screenHeight:size.height});
 const done=new Promise(resolve=>{ready=resolve;});window.webContents.send('network-view:render',{...value.scene,size});
 const status=await done;ready=null;if(!status?.ok)throw Error(status?.error??'网络图片尚未完成排版');
 // Keep the compositor surface fixed. Capture the acknowledged frontend region,
 // avoiding stale offscreen paint buffers and Windows resize/Viz races.
 const image=await window.webContents.debugger.sendCommand('Page.captureScreenshot',{format:'png',fromSurface:true,clip:{x:0,y:0,width:size.width,height:size.height,scale:1},captureBeyondViewport:true});
 if(Buffer.byteLength(image.data,'base64')>8*1024*1024)throw Error('网络图片超过 8 MiB，请缩小筛选范围');const {ok,...info}=status;return {image:image.data,...info};
}
let queue=Promise.resolve();process.on('message',value=>{queue=queue.then(async()=>{try{const result=await render(value);process.send({id:value.id,...result});}catch(error){process.send({id:value.id,error:error.message});}});});process.on('disconnect',()=>app.quit());
app.on('window-all-closed',()=>app.quit());
