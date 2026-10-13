import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
export class Bridge {
  constructor(executable, directory, args=[], environment={}) {
    this.pending=new Map(); this.next=0;
    this.process=spawn(executable,[...args,directory],{windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONUTF8:'1',...environment}});
    this.stderr=''; this.process.stderr.on('data',b=>{this.stderr=(this.stderr+b).slice(-8000)});
    createInterface({input:this.process.stdout}).on('line',line=>{
      let value; try{value=JSON.parse(line)}catch{return}
      const item=this.pending.get(value.id); if(!item)return;
      this.pending.delete(value.id); clearTimeout(item.timer);
      value.error ? item.reject(new Error(value.error)) : item.resolve(value.result);
    });
    this.process.on('error',e=>this.fail(e));
    this.process.on('exit',code=>this.fail(new Error(`Backend exited (${code}): ${this.stderr}`)));
  }
  fail(error){for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(error)}this.pending.clear()}
  call(method,params={}){return new Promise((resolve,reject)=>{
    const id=++this.next;
    const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`Backend timeout: ${method}`))},30000);
    this.pending.set(id,{resolve,reject,timer});
    this.process.stdin.write(JSON.stringify({id,method,params})+'\n',error=>{if(error){clearTimeout(timer);this.pending.delete(id);reject(error)}});
  })}
  async close(){
    this.fail(new Error('Plugin stopped'));
    if(this.process.exitCode!==null||this.process.signalCode!==null)return;
    await new Promise(resolve=>{
      const timer=setTimeout(()=>this.process.kill(),1000);
      const done=()=>{clearTimeout(timer);resolve()};
      this.process.once('exit',done);this.process.once('error',done);
      this.process.stdin.end();
    });
  }
}
