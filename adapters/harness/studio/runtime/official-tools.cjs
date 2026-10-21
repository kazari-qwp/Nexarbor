// Official installed SDK tools, without model adapters, credentials or model calls.
const fs=require('node:fs/promises'),path=require('node:path'),readline=require('node:readline'),crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const lines=readline.createInterface({input:process.stdin});
let host,directory,timeoutSeconds=30,owners=new Map(),sequence=0;
const sdk=process.env.DATANET_NATIVE_MODULES??path.join(path.dirname(process.execPath),'resources/app.asar/dsh/node_modules');
const native=async name=>{
 let resolved;try{resolved=require.resolve(path.join(sdk,'@deepseek-ai',name));}catch(error){if(error.code==='MODULE_NOT_FOUND')throw Error('当前 DeepSeek Harness 缺少原生服务 '+name+'；本适配已实测 Harness 0.2.1，请升级 Harness，非默认安装位置设置 DATANET_HARNESS_EXE。');throw error;}
 return import(pathToFileURL(resolved).href);
};
async function initialize(p){
 timeoutSeconds=p.timeout_seconds??30;directory=path.resolve(p.directory);await fs.mkdir(directory,{recursive:true});
 const cordis=await native('cordis');host=new cordis.Context();
 for(const name of ['dsh-system-prompt','dsh-tools','dsh-agent','dsh-session','dsh-session-projection','dsh-fs-local','dsh-working-directory','dsh-spill-local','dsh-attachment-local','dsh-jobs-local','dsh-shell-env','dsh-subprocess-local','dsh-pwsh-local','dsh-tool-fs','dsh-tool-fs-search','dsh-tool-jobs','dsh-tool-pwsh']){
  const mod=await native(name);await host.plugin(mod.default??mod,name==='dsh-pwsh-local'&&p.pwshPath?{pwshPath:p.pwshPath}:name==='dsh-working-directory'?{defaultDirectory:directory}:name==='dsh-tool-fs-search'?{sampleOverCapGlobResults:false}:{});
 }
 return catalog();
}
async function owner(actor){
 if(!owners.has(actor)){
  const fiber=host.plugin(()=>{}),id='nexarbor-tools-'+actor;
  const value={id,ctx:fiber.ctx,status:'running',inject:()=>{},followup:()=>{},session:host.sessions.create(id,{meta:{cwd:directory}})};
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
 if(method==='contracts'){
  const value=await owner('catalog');
  return Object.fromEntries(host.tools.sdkSchemas(value).map(tool=>[tool.name,{format:'harness-tool-result/v1',value_schema:tool.output}]));
 }
 if(method==='invoke'){
  const agent=await owner(p.actor),controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(Error('Official tool deadline exceeded')),timeoutSeconds*1000);
  const id=crypto.randomUUID(),started=Date.now();let result,error;
  try{result=JSON.parse(JSON.stringify(await host.tools.execute({signal:controller.signal,callId:'external-'+(++sequence),name:p.name,arguments:p.arguments,agent})));return result;}
  catch(e){error=String(e.message??e);throw e;}
  finally{
   clearTimeout(timer);
   if(p.name==='pwsh'){
    const home=path.join(directory,'.nexarbor','command-logs');await fs.mkdir(home,{recursive:true});
    await fs.writeFile(path.join(home,id+'.json'),JSON.stringify({id,actor:p.actor,started_at:started/1000,finished_at:Date.now()/1000,arguments:p.arguments,result,error}));
   }
  }
 }
 throw Error('Unknown official tool operation');
}
lines.on('line',line=>{let value;try{value=JSON.parse(line);}catch{return;}
 Promise.resolve().then(()=>request(value.method,value.params??{})).then(result=>process.stdout.write(JSON.stringify({id:value.id,result})+'\n'),error=>process.stdout.write(JSON.stringify({id:value.id,error:error.stack??String(error)})+'\n'));
});
lines.on('close',async()=>{if(host)await host.dispose();process.exit(0);});
