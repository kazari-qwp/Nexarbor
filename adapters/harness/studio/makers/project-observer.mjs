// Any on-disk Nexarbor project can be studied without starting or modifying it.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {readProjectBundle} from '../project.mjs';
import {NetworkObserver,indexNetwork,readObservedResource,readObservedText} from './network-observer.mjs';

const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const projectPath=relative=>{
 if(typeof relative!=='string'||path.isAbsolute(relative)||relative.includes('\\')||relative.includes(':')||relative.split('/').some(p=>p==='..'||p==='.'||!p))throw Error('项目资源路径无效');
 return relative;
};
const textExtensions=new Set(['.py','.json','.md','.txt','.toml','.html','.css','.js','.mjs','.cjs','.yaml','.yml','.svg']);
export async function readProjectSnapshot(directory){
 if(typeof directory!=='string'||!path.isAbsolute(directory))throw Error('project 必须是项目文件夹的绝对路径');
 const root=await fs.realpath(directory),read=async relative=>{
  const file=await fs.realpath(path.join(root,projectPath(relative)));if(!file.startsWith(root+path.sep))throw Error('项目资源越出项目文件夹');
  return fs.readFile(file,'utf8');
 };
 const project=JSON.parse(await read('nexarbor.json'));if(project.format!=='nexarbor-project/v1')throw Error('项目清单格式无效');
 if(!project.networks?.[project.activeNetwork])throw Error('项目没有活动网络');
 const bundle=await readProjectBundle(root,{includeContexts:false});if(bundle?.document?.network?.version!==8)throw Error('项目没有有效网络');
 const document=structuredClone(bundle.document),resources={},missing=[];
 const visit=async id=>{
  if(Object.hasOwn(resources,id)||missing.includes(id))return;
  const folder=project.resources?.modules?.[id]?.folder;
  if(!folder){missing.push(id);return;}
  const files={},walk=async relative=>{
   const real=await fs.realpath(path.join(root,projectPath(relative)));if(!real.startsWith(root+path.sep))throw Error('模块资源越出项目文件夹');
   for(const entry of await fs.readdir(real,{withFileTypes:true})){
    if(entry.name.startsWith('.')||['__pycache__','node_modules','test','tests','reference','lessons','dependencies'].includes(entry.name))continue;
    const file=relative+'/'+entry.name;
    if(entry.isDirectory())await walk(file);
    else if(entry.isFile()&&textExtensions.has(path.extname(entry.name))&&entry.name!=='test-output.txt')files[file.slice(folder.length+1)]=await read(file);
   }
  };
  try{await walk(folder);}catch(error){if(error.code==='ENOENT'){missing.push(id);return;}throw error;}
  if(!files['module.json']){missing.push(id);return;}
  const manifest=JSON.parse(files['module.json']);if(manifest.id!==id)throw Error('项目模块声明与 ID 不符：'+id);
  resources[id]={files,readOnly:true,release:{id,version:manifest.version,manifest,digest:hash(files)}};
  for(const dependency of manifest.requires??[])await visit(dependency);
 };
 for(const id of new Set(document.network.nodes.flatMap(n=>Object.keys(n.modules??{}))))await visit(id);
 // Make the project's own configuration and templates available through the same paged text reader.
 const entry=project.networks[project.activeNetwork],network=JSON.parse(await read(entry.file));
 for(const file of ['nexarbor.json',entry.file,...network.nodes.map(n=>n.file)])document.files[file]=await read(file);
 for(const file of ['README.md','templates.json'])try{document.files[file]=await read(file);}catch(error){if(error.code!=='ENOENT')throw error;}
 if(bundle.runtime?.templates&&!document.files['templates.json'])document.files['templates.json']=JSON.stringify(bundle.runtime.templates,null,2);
 return {document,resources,source:'project',project:root,missing_modules:missing,selection:{nodes:[],edges:[]}};
}

export class ProjectObservations{
 constructor(renderer){this.renderer=renderer;this.states=new Map();}
 uses(id,args){return args.project!==undefined||(!args.source&&this.states.has(id));}
 clear(id){this.states.delete(id);}
 observe(id,name,args){
  if(args.project!==undefined&&args.source!==undefined)throw Error('project 与 source 二选一；source 用于当前工作流，project 用于磁盘项目');
  let state=this.states.get(id);if(!state){if(this.states.size>=24)this.states.delete(this.states.keys().next().value);state={tail:Promise.resolve(),views:new Map(),epoch:0};this.states.set(id,state);}
  const result=state.tail.then(async()=>{
   const directory=args.project??state.snapshot?.project;if(typeof directory!=='string'||!path.isAbsolute(directory))throw Error('project 必须是项目文件夹的绝对路径');
   const root=await fs.realpath(directory);
   if(!state.snapshot||root!==state.snapshot.project||args.refresh){
    const snapshot=await readProjectSnapshot(root),index=indexNetwork(snapshot.document,state.snapshot?.project===snapshot.project?state.snapshot.observerIndex:undefined);
    snapshot.observerIndex=index;const digest=hash([snapshot,++state.epoch]);state.views.clear();state.snapshot=snapshot;state.observer=new NetworkObserver(snapshot,digest,state.views);
   }
   const observer=state.observer;observer.check(args);
   if(name==='read_resource')return readObservedResource(state.snapshot,observer.id,args);
   if(name==='read_network_text')return readObservedText(state.snapshot,observer.id,args);
   return observer.execute(name,args,scene=>this.renderer.render(scene));
  });state.tail=result.catch(()=>{});return result;
 }
}
