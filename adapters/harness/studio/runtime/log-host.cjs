// 只读日志与新建前缀分支；无需账户授权，不加载模型，也不执行工具。
const fs=require('node:fs/promises'),path=require('node:path'),readline=require('node:readline');
let host,positions,imageRuntime,keep=setInterval(()=>{},1000);
async function init(p){
 const loader=await require('./loader.cjs')(),{Context}=loader.native('cordis');host=new Context();
 await host.plugin(loader.native('dsh-llm').LlmRuntime);
 await host.plugin(loader.native('dsh-session').SessionStore);
 await host.plugin(loader.native('dsh-attachment-local').LocalAttachmentStore,{dshHome:p.directory});imageRuntime={host,native:loader.native};
 let options={};try{options=JSON.parse(await fs.readFile(path.join(p.directory,'native-model.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 const persistence=loader.native('dsh-session-persistence-jsonl');await host.plugin(persistence.default??persistence,{root:options.native_logs??path.join(p.directory,'native-logs')});
 const {NativePositions}=await loader.load(p.root+'/adapters/harness/framework/checkpoints.js');positions=new NativePositions(host);return {ready:true};
}
async function request(method,p){
 if(method==='init')return init(p);
 if(method==='shutdown'){await host?.fiber.dispose();clearInterval(keep);return {ok:true};}
 const result={};
 if(method==='capture')for(const [actor,id] of Object.entries(p.bindings))result[actor]=await positions.captureStored(id);
 else if(method==='export')for(const [actor,cursor] of Object.entries(p.contexts))result[actor]=await require('../makers/portable-images.cjs').exportImages(imageRuntime,await positions.exportPrefix(cursor));
 else if(method==='import')for(const [actor,prefix] of Object.entries(p.contexts)){await require('../makers/portable-images.cjs').admitImages(imageRuntime,prefix);result[actor]=await positions.importPrefix(prefix);}
 else if(method==='fork')for(const [actor,cursor] of Object.entries(p.contexts))result[actor]=await positions.captureStored(await positions.fork(cursor));
 else throw Error('Unknown log operation');return result;
}
readline.createInterface({input:process.stdin}).on('line',line=>{let value;try{value=JSON.parse(line);}catch{return;}Promise.resolve().then(()=>request(value.method,value.params??{})).then(result=>process.stdout.write(JSON.stringify({id:value.id,result})+'\n'),error=>process.stdout.write(JSON.stringify({id:value.id,error:String(error.stack??error)})+'\n'));}).on('close',()=>Promise.resolve(host?.fiber.dispose()).finally(()=>process.exit()));
