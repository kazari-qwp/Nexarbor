import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash,randomUUID} from 'node:crypto';
const root=fileURLToPath(new URL('../../../',import.meta.url)),identity=id=>{if(typeof id!=='string'||id.length>64||!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id))throw Error('Skill 名称无效');return id;};
const json=value=>JSON.stringify(value,null,2)+'\n';
export class SkillResources{
 constructor(project,rpc){this.project=project;this.rpc=rpc;this.builtins={ 'nexarbor-basics':path.join(root,'extensions/development/capabilities/component_studio/resources/skills/nexarbor-basics')};}
 async files(directory){
  const base=await fs.realpath(directory),result={};let total=0;
  const walk=async(relative='')=>{for(const entry of await fs.readdir(path.join(base,relative),{withFileTypes:true})){if(entry.name.startsWith('.')||entry.name==='__pycache__')continue;const name=path.posix.join(relative,entry.name),file=path.join(base,name);if(entry.isSymbolicLink())throw Error('Skill 资源不能使用符号链接');if(entry.isDirectory())await walk(name);else if(entry.isFile()){if(Object.keys(result).length>=128)throw Error('Skill 文件过多');const stat=await fs.stat(file);total+=stat.size;if(total>2*1024*1024)throw Error('Skill 文本总量超过2MiB');result[name]=new TextDecoder('utf-8',{fatal:true}).decode(await fs.readFile(file));}}};await walk();return result;
 }
 async source(id,{localOnly=false}={}){identity(id);const local=path.join(this.project.directory,'skills',id);try{const actual=await fs.realpath(local),base=await fs.realpath(this.project.directory);if(!actual.startsWith(base+path.sep))throw Error('Skill 路径越出项目');return {directory:actual,local:true};}catch(e){if(e.code!=='ENOENT')throw e;}if(!localOnly&&this.builtins[id])return {directory:this.builtins[id],local:false};throw Error('项目缺少 Skill：'+id);}
 async read(id,options={}){const source=await this.source(id,options),files=options.metadataOnly?await this.metadata(source.directory):await this.files(source.directory),parsed=await this.rpc('skill_parse',{files}),digest=createHash('sha256').update(JSON.stringify(files)).digest('hex');return {...parsed,name:id,description:parsed.manifest.description,digest,source:source.local?'project':'bundled',directory:source.directory,local:source.local};}
 async metadata(directory){const files={};for(const name of ['SKILL.md','skill.json'])try{const file=path.join(directory,name),stat=await fs.lstat(file);if(stat.isSymbolicLink()||!stat.isFile())throw Error('Skill 元数据必须是普通文件');if(stat.size>2*1024*1024)throw Error('Skill 文件过大');files[name]=await fs.readFile(file,'utf8');}catch(e){if(e.code!=='ENOENT'||name==='SKILL.md')throw e;}return files;}
 async catalog(){
  let local=[];try{local=(await fs.readdir(path.join(this.project.directory,'skills'),{withFileTypes:true})).filter(e=>e.isDirectory()&&/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(e.name)).map(e=>e.name);}catch(e){if(e.code!=='ENOENT')throw e;}
  const result={};for(const id of new Set([...Object.keys(this.builtins),...local]))try{const item=await this.read(id,{metadataOnly:true}),m=item.manifest;result[id]={id,name:m.name,description:m.description,requires:m.requires.modules,tools:m.requires.tools,skills:m.requires.skills,local:item.local,available:true,digest:item.digest};}catch(e){result[id]={id,name:id,description:e.message,requires:[],tools:[],skills:[],available:false,unavailableReason:e.message,local:local.includes(id)};}return result;
 }
 async import(files){
  const parsed=await this.rpc('skill_parse',{files}),id=parsed.manifest.id,target=path.join(this.project.directory,'skills',identity(id)),temporary=path.join(this.project.directory,'skills','.import-'+randomUUID());
  try{await fs.access(target);throw Error('项目已有同名 Skill，请先在项目内保留或修改已有版本');}catch(e){if(e.code!=='ENOENT')throw e;}
  const skillRoot=path.dirname(target);await fs.mkdir(skillRoot,{recursive:true});const realRoot=await fs.realpath(this.project.directory),realSkillRoot=await fs.realpath(skillRoot);if(!realSkillRoot.startsWith(realRoot+path.sep))throw Error('Skill 目录越出项目');if(!path.resolve(temporary).startsWith(path.resolve(skillRoot)+path.sep))throw Error('临时 Skill 路径无效');
  await fs.mkdir(temporary,{recursive:true});try{for(const [name,text]of Object.entries({...files,'skill.json':json(parsed.manifest)})){const file=path.join(temporary,name);await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,text);}await fs.rename(temporary,target);}catch(e){await fs.rm(temporary,{recursive:true,force:true});throw e;}return {id,name:parsed.manifest.name};
 }
 async install(id,visiting=new Set()){
  const key='skill:'+identity(id);if(visiting.has(key))throw Error('Skill 依赖成环：'+id);visiting.add(key);
  try{const item=await this.read(id);for(const dep of item.manifest.requires.skills)await this.install(dep,visiting);for(const dep of item.manifest.requires.modules)await this.project.installNow('module',dep,visiting);for(const dep of item.manifest.requires.tools)await this.project.installNow('tool',dep,visiting);
   if(!item.local){const files=await this.files(item.directory);await this.import(files);}
   const manifest=await this.project.read();manifest.resources.skills??={};manifest.resources.skills[id]={folder:'skills/'+id,digest:item.digest};await this.project.write('nexarbor.json',json(manifest));return manifest.resources.skills[id];
  }finally{visiting.delete(key);}
 }
 async bundles(ids){return Promise.all([...new Set(ids)].map(async id=>{const s=await this.read(id,{localOnly:true});return {name:id,description:s.description,content:s.content,files:s.files,source:'project',digest:s.digest};}));}
}
