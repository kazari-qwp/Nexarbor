import {textWindow} from './text-window.mjs';
// Read-only project materials for makers; bounded text windows and directory pages.
import fs from 'node:fs/promises';
import path from 'node:path';
const privateFolders=new Set(['.git','.nexarbor','node_modules','__pycache__']);
const privateName=name=>name.startsWith('.')||/^(?:native-model|model-connections|harness-connection)\.json$/i.test(name)||/credentials?/i.test(name);
function relative(value){
 if(typeof value!=='string'||path.isAbsolute(value)||value.includes('\\')||value.includes(':')||value.split('/').some(part=>!part||part==='.'||part==='..'))throw Error('使用项目内的相对路径，不含 ..');
 const parts=value.split('/');if(parts.some(part=>privateFolders.has(part)||privateName(part)))throw Error('该路径属于本地私有配置或运行记录');
 return value;
}
export async function projectFiles(directory,args={},hidden=[]){
 if(typeof directory!=='string'||!path.isAbsolute(directory))throw Error('project 必须是项目文件夹的绝对路径');
 const root=await fs.realpath(directory),manifest=JSON.parse(await fs.readFile(path.join(root,'nexarbor.json'),'utf8'));
 if(manifest.format!=='nexarbor-project/v1')throw Error('需要 Nexarbor 项目文件夹');
 const blocked=hidden.map(id=>(manifest.resources?.modules?.[id]?.folder??'modules/'+id).replaceAll('\\','/').toLowerCase());
 const isBlocked=name=>blocked.some(folder=>name.toLowerCase()===folder||name.toLowerCase().startsWith(folder+'/'));
 const resolve=async name=>{
  relative(name);if(isBlocked(name))throw Error('本任务隐藏的模块源码不可读取');
  const file=await fs.realpath(path.join(root,name));if(!file.startsWith(root+path.sep))throw Error('文件链接越出项目目录');
  const canonical=path.relative(root,file).replaceAll('\\','/');relative(canonical);
  if(isBlocked(canonical))throw Error('本任务隐藏的模块源码不可读取');
  return file;
 };
 if(args.file!==undefined){
  const name=relative(args.file),file=await resolve(name),stat=await fs.stat(file);
  if(!stat.isFile())throw Error('file 必须指定普通文件');
  if(stat.size>1024*1024)return {path:name,bytes:stat.size,large:true,hint:'超过 1 MiB；用相应数据节点或已有文件端口处理，先按目录定位材料。'};
  const buffer=await fs.readFile(file);let source;
  try{source=new TextDecoder('utf-8',{fatal:true}).decode(buffer);}catch{throw Error('文件不是 UTF-8 文本；请使用其数据节点接口');}
  if(source.includes('\0'))throw Error('文件包含二进制数据；请使用其数据节点接口');
  return {project:root,path:name,bytes:stat.size,...textWindow(source,args)};
 }
 const prefix=args.path===undefined||args.path===''||args.path==='.'?'':relative(args.path),folder=prefix?await resolve(prefix):root;
 const offset=args.offset??0,limit=args.limit??40;
 if(!Number.isInteger(offset)||offset<0||!Number.isInteger(limit)||limit<1||limit>100)throw Error('offset 从0开始，limit 为1至100');
 const rows=[];let scanned=0;
 async function visit(base,relativeBase){
  for(const entry of await fs.readdir(base,{withFileTypes:true})){
   if(privateName(entry.name)||privateFolders.has(entry.name))continue;
   const name=(relativeBase?relativeBase+'/':'')+entry.name;
   if(isBlocked(name))continue;
   if(++scanned>5000)throw Error('目录较大，请指定更精确的 path；每次最多检查5000项');
   if(entry.isSymbolicLink())continue;
   const real=await resolve(name);
   const stat=await fs.stat(real),kind=stat.isDirectory()?'directory':stat.isFile()?'file':null;if(!kind)continue;
   if(!args.query||name.toLowerCase().includes(args.query.toLowerCase()))rows.push({path:name,kind,...(kind==='file'?{bytes:stat.size}:{})});
   if(kind==='directory'&&args.recursive)await visit(real,name);
  }
 }
 await visit(folder,prefix);rows.sort((a,b)=>a.path.localeCompare(b.path));
 return {project:root,path:prefix||'.',entries:rows.slice(offset,offset+limit),total:rows.length,next_offset:offset+limit<rows.length?offset+limit:null};
}
