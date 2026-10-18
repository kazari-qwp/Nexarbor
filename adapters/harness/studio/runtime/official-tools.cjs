// Official installed SDK tools, without model adapters, credentials or model calls.
const fs=require('node:fs/promises'),path=require('node:path'),readline=require('node:readline');
const {pathToFileURL}=require('node:url');
const lines=readline.createInterface({input:process.stdin});
let host,directory,owners=new Map(),sequence=0;
const sdk=process.env.DATANET_NATIVE_MODULES??path.join(path.dirname(process.execPath),'resources/app.asar/dsh/node_modules');
const native=async name=>import(pathToFileURL(require.resolve(path.join(sdk,'@deepseek-ai',name))).href);
async function initialize(p){
 directory=path.resolve(p.directory);await fs.mkdir(directory,{recursive:true});
 const cordis=await native('cordis');host=new cordis.Context();
 for(const name of ['dsh-system-prompt','dsh-tools','dsh-agent','dsh-fs-local','dsh-spill-local','dsh-attachment-local','dsh-jobs-local','dsh-shell-env','dsh-subprocess-local','dsh-pwsh-local','dsh-tool-fs','dsh-tool-fs-search','dsh-tool-jobs','dsh-tool-pwsh']){
  const mod=await native(name);await host.plugin(mod.default??mod,name==='dsh-pwsh-local'&&p.pwshPath?{pwshPath:p.pwshPath}:name==='dsh-tool-fs-search'?{sampleOverCapGlobResults:false}:{});
 }
 return catalog();
}
async function owner(actor){
 if(!owners.has(actor)){
  const fiber=host.plugin(()=>{}),id='nexarbor-tools-'+actor;
  const value={id,ctx:fiber.ctx,status:'running',inject:()=>{},followup:()=>{},session:{id,header:{version:4,id,createdAt:Date.now(),cwd:directory}}};
  await host.agents.register(value);owners.set(actor,value);
 }
 return owners.get(actor);
}
async function catalog(){
 const value=await owner('catalog');
 return host.tools.schemas(value).map(s=>({name:s.name,description:s.description??'',parameters:s.parameters}));
}
async function request(method,p){
 if(method==='init')return initialize(p);
 if(!host)throw Error('Official tools are not initialized');
 if(method==='catalog')return catalog();
 if(method==='invoke'){
  const agent=await owner(p.actor),controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(Error('Official tool deadline exceeded')),30000);
  try{return JSON.parse(JSON.stringify(await host.tools.execute({signal:controller.signal,callId:'external-'+(++sequence),name:p.name,arguments:p.arguments,agent})));}
  finally{clearTimeout(timer);}
 }
 throw Error('Unknown official tool operation');
}
lines.on('line',line=>{let value;try{value=JSON.parse(line);}catch{return;}
 Promise.resolve().then(()=>request(value.method,value.params??{})).then(result=>process.stdout.write(JSON.stringify({id:value.id,result})+'\n'),error=>process.stdout.write(JSON.stringify({id:value.id,error:error.stack??String(error)})+'\n'));
});
lines.on('close',async()=>{if(host)await host.dispose();process.exit(0);});
