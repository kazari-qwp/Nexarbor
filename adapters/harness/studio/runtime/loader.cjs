// Load the existing ESM Harness adapter against an installed app.asar SDK.
const fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
module.exports=async function(){
 const root=process.env.DATANET_NATIVE_MODULES??path.join(path.dirname(process.execPath),'resources/app.asar/dsh/node_modules');
 const native=name=>require(path.join(root,'@deepseek-ai',name));
 const context=vm.createContext({process,console,Buffer,URL,AbortController,AbortSignal,structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,Symbol});const cache=new Map();
 async function get(spec,parent){
  const file=spec.startsWith('file:')?fileURLToPath(spec):spec.startsWith('.')?path.resolve(path.dirname(fileURLToPath(parent)),spec):null,key=file??spec;
  if(cache.has(key))return cache.get(key);
  let mod;
  if(!file){const ns=spec.startsWith('@deepseek-ai/')?native(spec.slice(13)):await import(spec);const keys=[...new Set([...Object.keys(ns),'default'])];mod=new vm.SyntheticModule(keys,function(){for(const key of keys)this.setExport(key,key==='default'?(ns.default??ns):ns[key])},{context,identifier:key});}
  else mod=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{context,identifier:pathToFileURL(file).href,initializeImportMeta:m=>m.url=pathToFileURL(file).href,importModuleDynamically:async(spec,ref)=>{const m=await get(spec,ref.identifier);if(m.status==='unlinked')await m.link(link);if(m.status==='linked')await m.evaluate();return m;}});
  cache.set(key,mod);return mod;
 }
 const link=(spec,ref)=>get(spec,ref.identifier);
 return {native,root,load:async(file)=>{const mod=await get(pathToFileURL(path.resolve(file)).href);if(mod.status==='unlinked')await mod.link(link);if(mod.status==='linked')await mod.evaluate();return mod.namespace;}};
};
