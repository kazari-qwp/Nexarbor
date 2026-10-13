import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
export class Bridge {
  constructor(executable, directory, args=[], environment={}, host=null) {
    this.host=host;
    this.closed=false;
    this.pending=new Map(); this.next=0;
    this.process=spawn(executable,[...args,directory],{windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONUTF8:'1',...environment}});
    this.stderr=''; this.process.stderr.on('data',b=>{this.stderr=(this.stderr+b).slice(-8000)});
    this.process.stdin.on('error',e=>this.fail(e));
    createInterface({input:this.process.stdout}).on('line',line=>{
      let value; try{value=JSON.parse(line)}catch{return}
      if(value.host_id){
        Promise.resolve().then(()=>this.host(value.method,value.params)).then(
          result=>{if(!this.closed)this.process.stdin.write(JSON.stringify({host_id:value.host_id,result:result??null})+'\n');},
          error=>{if(!this.closed)this.process.stdin.write(JSON.stringify({host_id:value.host_id,error:String(error.message??error)})+'\n');}
        );return;
      }
      const item=this.pending.get(value.id); if(!item)return;
      this.pending.delete(value.id); clearTimeout(item.timer);
      value.error ? item.reject(new Error(value.error)) : item.resolve(value.result);
    });
    this.process.on('error',e=>this.fail(e));
    this.process.on('exit',code=>this.fail(new Error(`Backend exited (${code}): ${this.stderr}`)));
  }
  fail(error){for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(error)}this.pending.clear()}
  call(method,params={},timeout=30000){return new Promise((resolve,reject)=>{
    if(this.closed){reject(new Error('Plugin stopped'));return;}
    const id=++this.next;
    const timer=timeout>0?setTimeout(()=>{this.pending.delete(id);reject(new Error(`Backend timeout: ${method}`))},timeout):null;
    this.pending.set(id,{resolve,reject,timer});
    this.process.stdin.write(JSON.stringify({id,method,params})+'\n',error=>{if(error){clearTimeout(timer);this.pending.delete(id);reject(error)}});
  })}
  async close(){
    this.closed=true;
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
