import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';

const inspectedHarnesses=new Map();
export async function inspectHarnessExecutable(executable){
 const stat=await fs.stat(executable),archive=await fs.stat(path.join(path.dirname(executable),'resources/app.asar')).catch(()=>null),key=executable+'|'+stat.mtimeMs+'|'+archive?.mtimeMs;
 if(inspectedHarnesses.has(key))return inspectedHarnesses.get(key);
 const probe=`const path=require('node:path');const app=path.join(path.dirname(process.execPath),'resources/app.asar');const sdk=path.join(app,'dsh/node_modules/@deepseek-ai');const services=['cordis','dsh-system-prompt','dsh-tools','dsh-agent','dsh-session','dsh-session-projection','dsh-fs-local','dsh-working-directory','dsh-spill-local','dsh-attachment-local','dsh-jobs-local','dsh-shell-env','dsh-subprocess-local','dsh-pwsh-local','dsh-tool-fs','dsh-tool-fs-search','dsh-tool-jobs','dsh-tool-pwsh'];const missing=services.filter(name=>{try{require.resolve(path.join(sdk,name));return false;}catch{return true;}});console.log(JSON.stringify({version:require(path.join(app,'package.json')).version,compatible:missing.length===0,missing}));`;
 const checking=new Promise((resolve,reject)=>{
  const child=spawn(executable,['-e',probe],{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,ELECTRON_RUN_AS_NODE:'1'}});let output='';
  const timer=setTimeout(()=>{child.kill();reject(Error('Harness 检查超时，请选择正确的 DeepSeek Harness.exe'));},10000);
  child.stdout.on('data',value=>output+=value);child.stderr.on('data',()=>{});
  child.on('error',error=>{clearTimeout(timer);reject(Error('无法启动所选 Harness：'+error.message));});
  child.on('close',code=>{clearTimeout(timer);if(code)return reject(Error('所选文件无法作为 Harness 运行，请选择 DeepSeek Harness.exe'));try{resolve({executable,...JSON.parse(output.trim().split(/\r?\n/).at(-1))});}catch{reject(Error('无法读取 Harness 版本，请选择 DeepSeek Harness.exe'));}});
 }).catch(error=>{inspectedHarnesses.delete(key);throw error;});
 inspectedHarnesses.set(key,checking);return checking;
}
export async function requireCompatibleHarness(executable=undefined){
 const status=await inspectHarnessExecutable(executable??await harnessExecutable());
 if(!status.compatible)throw Error('Harness '+status.version+' 缺少原生服务 '+status.missing.join('、')+'；请在“设置 → DeepSeek Harness 路径”选择 0.2.1 或兼容版本。');
 return status;
}

export function harnessSettingsFile(){return process.env.NEXARBOR_HARNESS_CONFIG??path.join(process.env.LOCALAPPDATA??process.env.USERPROFILE,'Nexarbor','harness.json');}
export async function harnessSettings(){try{return JSON.parse(await fs.readFile(harnessSettingsFile(),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;return {};}}
export async function saveHarnessExecutable(executable){
 if(typeof executable!=='string')throw Error('请选择 DeepSeek Harness 的 .exe 文件');
 executable=executable.trim();
 if(executable&&(!path.isAbsolute(executable)||!executable.toLowerCase().endsWith('.exe')))throw Error('Harness 路径须为完整的 .exe 路径');
 if(executable){const stat=await fs.stat(executable);if(!stat.isFile())throw Error('Harness 路径不是文件');await requireCompatibleHarness(executable);}
 const file=harnessSettingsFile(),value=await harnessSettings(),temporary=file+'.'+randomUUID()+'.tmp';
 if(executable)value.executable=executable;else delete value.executable;
 await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(temporary,JSON.stringify(value,null,2)+'\n');await fs.rename(temporary,file);
 return {executable:await harnessExecutable(),saved:executable,source:process.env.DATANET_HARNESS_EXE?'environment':executable?'settings':'automatic'};
}

// 机器配置不进入项目与发布包；环境变量仍可临时覆盖。
export async function harnessExecutable(){
  if(process.env.DATANET_HARNESS_EXE)return process.env.DATANET_HARNESS_EXE;
  const saved=await harnessSettings();if(saved.executable)return saved.executable;
  const root=fileURLToPath(new URL('../../../',import.meta.url));
  try{
    const local=JSON.parse(await fs.readFile(path.join(root,'build/harness-installation.json'),'utf8'));
    if(typeof local.executable!=='string'||!path.isAbsolute(local.executable))throw Error('Harness 安装记录必须提供绝对路径');
    return local.executable;
  }catch(error){if(error.code!=='ENOENT')throw error;}
  return path.join(process.env.LOCALAPPDATA,'Programs/DeepSeek Harness/DeepSeek Harness.exe');
}

// 这里只保存授权文件的位置；文件内容仅由本机模型运行器读取。
export async function harnessCredentials({home,directory}={}){
  if(home)return path.join(path.resolve(home),'.credentials.yaml');
  const environment=process.env.DATANET_HARNESS_CREDENTIALS??process.env.DATANET_MAKER_CREDENTIALS;
  if(environment)return path.resolve(environment);
  if(directory){try{const connection=JSON.parse(await fs.readFile(path.join(directory,'studio/harness-connection.json'),'utf8'));return path.join(path.resolve(connection.home),'.credentials.yaml');}catch(error){if(error.code!=='ENOENT')throw error;}}
  const root=fileURLToPath(new URL('../../../',import.meta.url));
  try{const local=JSON.parse(await fs.readFile(path.join(root,'build/harness-installation.json'),'utf8'));if(local.credentials){if(!path.isAbsolute(local.credentials))throw Error('授权记录须为绝对路径');return local.credentials;}}catch(error){if(error.code!=='ENOENT')throw error;}
  for(const folder of [process.env.DSH_HOME,process.env.USERPROFILE&&path.join(process.env.USERPROFILE,'.dsh')].filter(Boolean)){const candidate=path.join(path.resolve(folder),'.credentials.yaml');try{await fs.access(candidate);return candidate;}catch(error){if(error.code!=='ENOENT')throw error;}}
  throw Error('请先在 DeepSeek Harness 完成账户授权，并在制作 Agent 页面指定 Harness home，或设置 DATANET_HARNESS_CREDENTIALS。');
}
