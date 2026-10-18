import {spawn} from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs/promises';
import readline from 'node:readline';
import {fileURLToPath} from 'node:url';

export class OfficialToolsRunner{
 constructor(directory){this.directory=directory;this.serial=0;this.pending=new Map();}
 async start(){
  if(this.starting)return this.starting;
  this.starting=(async()=>{
   const executable=process.env.DATANET_HARNESS_EXE??path.join(process.env.LOCALAPPDATA,'Programs/DeepSeek Harness/DeepSeek Harness.exe');
   await fs.access(executable);await fs.mkdir(path.join(this.directory,'temp'),{recursive:true});
   const child=this.child=spawn(executable,[fileURLToPath(new URL('./official-tools.cjs',import.meta.url))],{cwd:this.directory,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,ELECTRON_RUN_AS_NODE:'1',TEMP:path.join(this.directory,'temp'),TMP:path.join(this.directory,'temp')}});
   this.errors='';child.stderr.on('data',b=>this.errors=(this.errors+b).slice(-8000));
   const fail=error=>{for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(error);}this.pending.clear();};
   child.on('error',fail);child.on('exit',code=>{fail(Error('Official tool host exited '+code+' '+this.errors));this.child=null;this.starting=null;});
   readline.createInterface({input:child.stdout}).on('line',line=>{let v;try{v=JSON.parse(line);}catch{return;}const p=this.pending.get(v.id);if(!p)return;this.pending.delete(v.id);clearTimeout(p.timer);v.error?p.reject(Error(v.error)):p.resolve(v.result);});
   return this.send('init',{directory:this.directory,pwshPath:process.env.DATANET_PWSH_PATH});
  })().catch(error=>{this.starting=null;throw error;});return this.starting;
 }
 send(method,params={}){return new Promise((resolve,reject)=>{
  const id=++this.serial,timer=setTimeout(()=>{this.pending.delete(id);reject(Error('Official tool host timed out'));if(this.child)this.child.kill();},40000);
  this.pending.set(id,{resolve,reject,timer});this.child.stdin.write(JSON.stringify({id,method,params})+'\n');
 });}
 async request(method,params){await this.start();return this.send(method,params);}
 async close(){const child=this.child;if(!child)return;child.stdin.end();await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve();},5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});}
}
