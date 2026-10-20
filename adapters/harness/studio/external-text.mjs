import {replaceFile} from './atomic-write.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
const hash=value=>createHash('sha256').update(value).digest('hex');
const validText=value=>{if(typeof value!=='string'||Buffer.byteLength(value)>5*1024*1024)throw Error('文本须为 5 MiB 以内的 UTF-8 正文');return value;};
export const externalPath=name=>path.isAbsolute(name)||name.replaceAll('\\','/').split('/').includes('..');

// Bodies live in versioned project files; only synchronization metadata is cached.
export class ExternalTextFiles{
 constructor({directory,project,onOpen,onChoose,onReveal,preferences}){this.directory=directory;this.project=project;this.root=path.join(directory,'temp/external-text');this.onOpen=onOpen;this.onReveal=onReveal;this.onChoose=onChoose;this.preferences=preferences;this.queue=Promise.resolve();}
 folder(id){if(!/^[a-f0-9]{64}$/.test(id))throw Error('文本会话无效');return path.join(this.root,id);}
 async atomic(file,text){await fs.mkdir(path.dirname(file),{recursive:true});const temporary=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temporary,text,'utf8');await replaceFile(temporary,file);}
 async locate(name){const external=externalPath(name),file=external?path.resolve(this.directory,name):path.join(this.project.directory,this.project.textRelative(name));const real=await fs.realpath(file);if(!external){const root=await fs.realpath(this.project.directory);if(!real.startsWith(root+path.sep))throw Error('项目文本链接越界');}return {file:real,external};}
 async body(file){const stat=await fs.stat(file);if(stat.size>5*1024*1024)throw Error('文本超过 5 MiB');return fs.readFile(file,'utf8');}
 async ensure(node,name,content){
  const session=hash(node+'\0'+name),folder=this.folder(session),meta=path.join(folder,'record.json');let record;
  try{record=JSON.parse(await fs.readFile(meta,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;record={node,path:name,base:content};}
  if(!externalPath(name)){const relative=this.project.textRelative(name);try{await fs.access(path.join(this.project.directory,relative));}catch(error){if(error.code!=='ENOENT')throw error;let initial=content;if(record.name)try{initial=await fs.readFile(path.join(folder,path.basename(record.name)),'utf8');}catch{}await this.project.write(relative,initial);}}
  await this.atomic(meta,JSON.stringify({node,path:name,base:record.base}));return session;
 }
 async record(id){const record=JSON.parse(await fs.readFile(path.join(this.folder(id),'record.json'),'utf8'));return {...record,...await this.locate(record.path),folder:this.folder(id)};}
 async read(p){const record=await this.record(p.session),content=await this.body(record.file),digest=hash(content);return {session:p.session,node:record.node,path:record.path,base:record.base,digest,file:record.file,external:record.external,changed:p.digest!==digest,...(p.digest!==digest?{content}:{})};}
 async open(p,reveal=false){
  if(!(reveal?this.onReveal:this.onOpen))throw Error('请在桌面客户端中打开外部编辑器');
  const node=p.node;if(node?.type!=='text_file'||typeof node.node_id!=='string'||typeof node.parameters?.file_path!=='string')throw Error('请选择具有文本文件的文本节点');
  const name=node.parameters.file_path,content=externalPath(name)?await this.body((await this.locate(name)).file):validText(p.content),session=await this.ensure(node.node_id,name,content),record=await this.record(session);
  if(reveal)await this.onReveal(record.file);else await this.onOpen({file:record.file,editor:(await this.preferences()).external_editor??''});return this.read({session});
 }
 async update(p){
  const record=await this.record(p.session),current=await this.body(record.file);if(hash(current)!==p.digest)throw Error('文本再次发生变化，请重新同步后选择');
  const content=Object.hasOwn(p,'content')?validText(p.content):current;if(Object.hasOwn(p,'content')){if(record.external)throw Error('外部引用请在文件编辑器中修改');await this.project.write(this.project.textRelative(record.path),content);}
  await this.atomic(path.join(record.folder,'record.json'),JSON.stringify({node:record.node,path:record.path,base:content}));return {session:p.session,digest:hash(content),base:content};
 }
 async choose(){
  if(!this.onChoose)throw Error('请从桌面客户端选择文本文件');const chosen=await this.onChoose();if(!chosen||chosen.canceled)return {canceled:true};const file=await fs.realpath(chosen.file),content=validText(await this.body(file)),root=await fs.realpath(this.project.directory);
  if(file.startsWith(root+path.sep)){const name='imports/'+randomUUID()+'/'+path.basename(file);await this.project.write(this.project.textRelative(name),content);return {path:name,content,external:false};}
  return {path:file.replaceAll('\\','/'),content,external:true};
 }
 async clear(p){if(p.node?.type!=='text_file'||!externalPath(p.node.parameters?.file_path??''))throw Error('请选择外部文本引用');const {file}=await this.locate(p.node.parameters.file_path);await this.atomic(file,'');return {content:''};}
 sync(document){const task=this.queue.then(()=>this.syncDocument(document));this.queue=task.catch(()=>{});return task;}
 async syncDocument(document){
  const next=structuredClone(document),nodes=new Map(next.network.nodes.filter(n=>n.parameters?.file_path).map(n=>[n.parameters.file_path,n.node_id]));
  for(const [name,value]of Object.entries(next.files??{})){
   if(externalPath(name)){delete next.files[name];continue;}if(typeof value!=='string')continue;
   const session=await this.ensure(nodes.get(name)??'document:'+name,name,value),record=await this.record(session),disk=await fs.readFile(record.file,'utf8');
   if(disk!==record.base&&value!==record.base&&disk!==value)throw Error('文本在工作台和磁盘均有修改，请打开文本文件处理冲突：'+name);
   const content=disk!==record.base?disk:value;if(content!==disk)await this.project.write(this.project.textRelative(name),content);next.files[name]=content;
   await this.atomic(path.join(record.folder,'record.json'),JSON.stringify({node:record.node,path:name,base:content}));
  }
  return next;
 }
 async request(operation,p={}){const task=this.queue.then(()=>operation==='text.external.open'?this.open(p):operation==='text.external.reveal'?this.open(p,true):operation==='text.external.read'?this.read(p):operation==='text.external.update'?this.update(p):operation==='text.external.choose'?this.choose():operation==='text.external.clear'?this.clear(p):Promise.reject(Error('未知文本操作')));this.queue=task.catch(()=>{});return task;}
}
