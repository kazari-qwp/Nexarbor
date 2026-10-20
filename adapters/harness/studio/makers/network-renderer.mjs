import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
const root=fileURLToPath(new URL('../../../../',import.meta.url));
// Start Chromium only when an image is requested. Reuse it, and release it after inactivity.
export class NetworkRenderer{
 constructor(directory=path.join(root,'build')){this.directory=directory;this.queue=Promise.resolve();this.serial=0;this.pending=new Map();this.epoch=0;this.views=new Map();}
 async start(){
  if(this.starting)return this.starting;
  const epoch=this.epoch;this.starting=(async()=>{
   const page=path.join(root,'extensions/editor/capabilities/network_editor/web/network-view.html');await fs.access(page);
   const source=path.join(root,'frontends/desktop');let executable;
   for(const candidate of [process.versions.electron?process.execPath:null,path.join(source,'node_modules/electron/dist/electron.exe'),path.join(root,'build/desktop/Nexarbor Workbench-win32-x64/Nexarbor.exe')].filter(Boolean)){try{await fs.access(candidate);executable=candidate;break;}catch{}}
   if(!executable)throw Error('未找到桌面图片渲染器，请使用 Nexarbor 桌面客户端。');
   if(epoch!==this.epoch)throw Error('网络图片请求已取消');
   const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
   const viewHome=path.resolve(this.directory,'temp/network-views');
   const child=this.child=spawn(executable,[...(executable.toLowerCase().endsWith('electron.exe')?[source]:[]),'--network-renderer','--view-page',page,'--view-home',viewHome],{cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe','ipc']});
   this.errors='';child.stderr.on('data',b=>{this.errors=(this.errors+b).slice(-2000);});
   const fail=error=>{for(const [id,p] of this.pending)if(p.child===child){clearTimeout(p.timer);this.pending.delete(id);p.reject(error);}};
   child.on('error',fail);child.on('exit',code=>{if(this.child===child){this.child=null;this.starting=null;}fail(Error('网络图片渲染器已关闭 '+code+' '+this.errors));
    const profile=path.resolve(viewHome,'renderer-'+child.pid);if(child.pid&&path.dirname(profile)===viewHome)fs.rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:300}).catch(()=>{});
   });
   child.on('message',value=>{const p=this.pending.get(value.id);if(!p)return;clearTimeout(p.timer);this.pending.delete(value.id);const {id,...result}=value;value.error?p.reject(Error(value.error)):p.resolve(result);});
  })().catch(e=>{this.starting=null;throw e;});return this.starting;
 }
 render(scene){const result=this.queue.then(async()=>{
  let request;
  if(scene.region){
   const saved=this.views.get(scene.view);if(!saved||saved.snapshot!==scene.snapshot)throw Error('视图已失效或属于其他快照；请重新获取概览。');
   request={...saved,region:scene.region};
  }else{
   const view='V'+createHash('sha256').update(JSON.stringify(scene)).digest('hex').slice(0,16);request={...scene,view};
   this.views.delete(view);this.views.set(view,request);if(this.views.size>24)this.views.delete(this.views.keys().next().value);
  }
  clearTimeout(this.idle);await this.start();
  try{const result=await new Promise((resolve,reject)=>{const id=++this.serial,child=this.child,timer=setTimeout(()=>{this.pending.delete(id);reject(Error('网络图片渲染超时'));this.close();},35000);this.pending.set(id,{resolve,reject,timer,child});child.send({id,scene:request},error=>{if(error){clearTimeout(timer);this.pending.delete(id);reject(error);}});});return {...result,view:request.view,counts:request.counts,page:request.page,pages:request.pages};}
  finally{this.idle=setTimeout(()=>this.close(),60000);this.idle.unref();}
 });this.queue=result.catch(()=>{});return result;}
 close(){this.epoch++;clearTimeout(this.idle);const child=this.child;this.child=null;this.starting=null;for(const [id,p] of this.pending)if(p.child===child){clearTimeout(p.timer);this.pending.delete(id);p.reject(Error('网络图片请求已取消'));}child?.kill();}
}
