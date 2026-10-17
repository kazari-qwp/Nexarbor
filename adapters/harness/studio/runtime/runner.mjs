// Generic native Harness executor; no town or other application rules.
import {spawn} from 'node:child_process';import readline from 'node:readline';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
export class NativeRunner{
 constructor(directory,callback){this.directory=directory;this.callback=callback;this.pending=new Map();this.serial=0;this.starting=null;}
 async start(){
  if(this.starting)return this.starting;
  this.starting=(async()=>{
   const connection=JSON.parse(await fs.readFile(path.join(this.directory,'studio/harness-connection.json'),'utf8'));
   const root=fileURLToPath(new URL('../../../../',import.meta.url));
   const executable=path.join(process.env.LOCALAPPDATA,'Programs/DeepSeek Harness/DeepSeek Harness.exe');
   const child=this.child=spawn(executable,['--experimental-vm-modules',fileURLToPath(new URL('./host.cjs',import.meta.url))],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,ELECTRON_RUN_AS_NODE:'1',TEMP:path.join(this.directory,'temp'),TMP:path.join(this.directory,'temp'),TMPDIR:path.join(this.directory,'temp')}});
   this.errors='';child.stderr.on('data',b=>{this.errors=(this.errors+b).slice(-12000);});
   const fail=error=>{for(const p of this.pending.values())p.reject(error);this.pending.clear();};child.on('error',fail);child.on('exit',code=>{fail(Error('Native Harness exited '+code+' '+this.errors));this.starting=null;this.child=null;});
   readline.createInterface({input:child.stdout}).on('line',line=>{
    let value;try{value=JSON.parse(line);}catch{return;}
    if(value.host_id){Promise.resolve(this.callback(value.method,value.params)).then(result=>child.stdin.write(JSON.stringify({host_id:value.host_id,result})+'\n'),error=>child.stdin.write(JSON.stringify({host_id:value.host_id,error:error.message})+'\n'));return;}
    const p=this.pending.get(value.id);if(!p)return;this.pending.delete(value.id);value.error?p.reject(Error(value.error)):p.resolve(value.result);
   });
   return this.send('init',{directory:this.directory,root,credentials:path.join(connection.home,'.credentials.yaml')});
  })().catch(error=>{this.starting=null;throw error;});return this.starting;
 }
 send(method,params){return new Promise((resolve,reject)=>{const id=++this.serial;this.pending.set(id,{resolve,reject});this.child.stdin.write(JSON.stringify({id,method,params})+'\n');});}
 async request(method,params){await this.start();return this.send(method,params);}
 async close(){if(!this.child)return;const child=this.child;child.stdin.end();await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve();},10000);child.once('exit',()=>{clearTimeout(timer);resolve();});});}
}
