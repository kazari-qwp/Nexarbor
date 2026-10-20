import {replaceFile} from './atomic-write.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {spawn} from 'node:child_process';
import {randomUUID,createHash} from 'node:crypto';
import {harnessCredentials} from '../framework/harness-installation.js';

const protocols=['openai-completions','openai-responses','anthropic-messages'];
const text=(value,label,max=300)=>{if(typeof value!=='string'||!value.trim()||value.length>max)throw Error(label+'无效');return value.trim();};
export function selection(value){
 if(value==null)return null;
 if(typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!['connection','model','reasoning_effort','max_tokens','context_window'].includes(k)))throw Error('模型配置无效');
 const result={connection:text(value.connection,'模型连接',100),model:text(value.model,'模型名称')};
 if(value.reasoning_effort!=null){if(!['off','minimal','low','medium','high','xhigh','max'].includes(value.reasoning_effort))throw Error('思考强度无效');result.reasoning_effort=value.reasoning_effort;}
 for(const [key,max]of [['max_tokens',2000000],['context_window',4000000]])if(value[key]!=null){if(!Number.isInteger(value[key])||value[key]<1||value[key]>max)throw Error('模型参数 '+key+' 无效');result[key]=value[key];}
 return result;
}
// DPAPI is bound to the current Windows account. Keys never enter project files.
export async function protectSecret(value,decrypt=false){
 if(process.platform!=='win32')throw Error('当前凭据库需要 Windows DPAPI');
 const script=`$ErrorActionPreference='Stop';Add-Type -AssemblyName System.Security;$bytes=[Convert]::FromBase64String([Console]::In.ReadToEnd());$result=[Security.Cryptography.ProtectedData]::${decrypt?'Unprotect':'Protect'}($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser);[Console]::Out.Write([Convert]::ToBase64String($result))`;
 return new Promise((resolve,reject)=>{
  const child=spawn('powershell.exe',['-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],{windowsHide:true,stdio:['pipe','pipe','pipe']}),output=[];
  child.on('error',()=>reject(Error('无法访问本机凭据保护服务')));child.stdout.on('data',value=>output.push(value));child.stderr.on('data',()=>{});
  child.on('close',code=>code?reject(Error('本机凭据无法解密，请使用保存该连接的 Windows 账户，或重新填写 key')):resolve(decrypt?Buffer.from(Buffer.concat(output).toString().trim(),'base64').toString('utf8'):Buffer.concat(output).toString().trim()));
  child.stdin.on('error',()=>{});child.stdin.end(decrypt?value:Buffer.from(value,'utf8').toString('base64'));
 });
}
export class ModelConnections{
 constructor({project,directory,configDirectory,protect=protectSecret}={}){this.project=project;this.directory=directory;this.root=configDirectory??process.env.NEXARBOR_MODEL_DIRECTORY??path.join(process.env.LOCALAPPDATA??os.homedir(),'Nexarbor','models');this.protect=protect;this.queue=Promise.resolve();}
 file(id){if(!/^[a-f0-9-]{36}$/.test(id))throw Error('模型连接编号无效');return path.join(this.root,id+'.json');}
 async read(id){try{return JSON.parse(await fs.readFile(this.file(id),'utf8'));}catch(error){if(error.code==='ENOENT')throw Error('模型连接不存在，请重新选择连接');throw error;}}
 public(value){const {secret,...safe}=value;return {...safe,hasKey:!!secret};}
 async settings(){return (await this.project.read()).model_settings??{};}
 async index(){await fs.mkdir(this.root,{recursive:true});const connections=[];for(const name of await fs.readdir(this.root))if(/^[a-f0-9-]{36}\.json$/.test(name))connections.push(this.public(JSON.parse(await fs.readFile(path.join(this.root,name),'utf8'))));return {connections:[{id:'harness-default',name:'Harness 已授权账户',provider:'DeepSeek',kind:'harness-account',models:['deepseek-flash','deepseek-v4-pro'],revision:0},...connections.sort((a,b)=>a.name.localeCompare(b.name))],scopes:await this.settings(),protocols};}
 async atomic(file,value){await fs.mkdir(path.dirname(file),{recursive:true});const temporary=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temporary,JSON.stringify(value,null,2)+'\n',{mode:0o600});await replaceFile(temporary,file);}
 async save(p){
  const task=this.queue.then(async()=>{
   const previous=p.id?await this.read(p.id):null;if(previous&&p.revision!==previous.revision)throw Error('连接已被修改，请重新打开配置');
   const name=text(p.name,'连接名称',80),provider=text(p.provider,'服务商',80),protocol=p.protocol??'openai-completions';if(!protocols.includes(protocol))throw Error('不支持的 API 类型');
   const url=new URL(text(p.base_url,'API 地址',2000));if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw Error('API 地址须为不含账户、查询和片段的 HTTP(S) 地址');
   const models=[...new Set((p.models??[]).map(value=>text(value,'模型名称')))];if(models.length>200)throw Error('模型列表过长');
   const apiKey=p.api_key??'';if(typeof apiKey!=='string'||apiKey.length>16000||/[\r\n]/.test(apiKey))throw Error('API key 无效');
   const secret=p.no_key?undefined:apiKey?await this.protect(apiKey):previous?.secret;if(!secret&&!p.no_key)throw Error('请填写 API key，或明确选择无需 key');
   const value={id:previous?.id??randomUUID(),name,provider,kind:'api-key',protocol,base_url:url.href.replace(/\/$/,''),models,no_key:!secret,revision:(previous?.revision??0)+1,...(secret?{secret}:{})};await this.atomic(this.file(value.id),value);return this.public(value);
  });this.queue=task.catch(()=>{});return task;
 }
 async choose(scope,value){if(!['project','component','network'].includes(scope))throw Error('模型配置范围无效');const next=selection(value);return this.project.serial(async()=>{const project=await this.project.read();project.model_settings={...project.model_settings,[scope]:next};await this.project.write('nexarbor.json',JSON.stringify(project,null,2)+'\n');return {selection:next};});}
 async runtime(value,scope='project'){
  const settings=await this.settings(),chosen=selection(value??settings[scope]??settings.project)??{connection:'harness-default',model:'deepseek-flash'};
  const model={provider:'deepseek-account',model:chosen.model,maxTokens:chosen.max_tokens??(scope==='project'?16000:24000),contextWindow:chosen.context_window??128000,...(chosen.reasoning_effort?{reasoningEffort:chosen.reasoning_effort}:{})};
  if(chosen.connection==='harness-default'){
   const credentials=await harnessCredentials({directory:this.directory}),stat=await fs.stat(credentials),signature=createHash('sha256').update(JSON.stringify({chosen,credentials,modified:stat.mtimeMs})).digest('hex');
   return {kind:'harness-account',id:chosen.connection,signature,credentials,model:{...model,contextWindow:chosen.context_window??500000,reasoningEffort:chosen.reasoning_effort??'low'}};
  }
  const connection=await this.read(chosen.connection),api_key=connection.secret?await this.protect(connection.secret,true):undefined;
  const signature=createHash('sha256').update(JSON.stringify({chosen,revision:connection.revision})).digest('hex');
  return {kind:'api-key',id:connection.id,signature,protocol:connection.protocol,base_url:connection.base_url,api_key,model:{...model,provider:'nexarbor-'+connection.id+'-'+signature.slice(0,12)}};
 }
 async discover(p){
  const connection=await this.read(p.id),key=connection.secret?await this.protect(connection.secret,true):undefined;
  const base=connection.base_url.replace(/\/$/,''),url=base+(connection.protocol==='anthropic-messages'&&!base.endsWith('/v1')?'/v1/models':'/models');
  const headers=connection.protocol==='anthropic-messages'?{'anthropic-version':'2023-06-01',...(key?{'x-api-key':key}:{})}:key?{Authorization:'Bearer '+key}:{};
  const response=await fetch(url,{headers,redirect:'error',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('模型列表请求失败（HTTP '+response.status+'）；可以手动填写模型名称');const body=await response.json();return {models:[...new Set((body.data??body.models??[]).map(value=>value.id??value.name).filter(value=>typeof value==='string'&&value.length<300))].slice(0,200)};
 }
 async preferences(p){const file=path.join(this.root,'preferences.json');let value={};try{value=JSON.parse(await fs.readFile(file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
  if(p?.save){if(typeof p.external_editor!=='string'||p.external_editor&&(!path.isAbsolute(p.external_editor)||!p.external_editor.toLowerCase().endsWith('.exe')))throw Error('请输入编辑器的完整 .exe 路径，或留空使用系统默认');value.external_editor=p.external_editor;await this.atomic(file,value);}return value;
 }
 async request(operation,p={}){if(operation==='models.list')return this.index();if(operation==='models.connection.save')return this.save(p);if(operation==='models.discover')return this.discover(p);if(operation==='models.selection.save')return this.choose(p.scope,p.selection);if(operation==='preferences.get')return this.preferences();if(operation==='preferences.save')return this.preferences({...p,save:true});throw Error('未知模型连接操作');}
}
