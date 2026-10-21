import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';

export function harnessSettingsFile(){return process.env.NEXARBOR_HARNESS_CONFIG??path.join(process.env.LOCALAPPDATA??process.env.USERPROFILE,'Nexarbor','harness.json');}
export async function harnessSettings(){try{return JSON.parse(await fs.readFile(harnessSettingsFile(),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;return {};}}
export async function saveHarnessExecutable(executable){
 if(typeof executable!=='string')throw Error('请选择 DeepSeek Harness 的 .exe 文件');
 executable=executable.trim();
 if(executable&&(!path.isAbsolute(executable)||!executable.toLowerCase().endsWith('.exe')))throw Error('Harness 路径须为完整的 .exe 路径');
 if(executable){const stat=await fs.stat(executable);if(!stat.isFile())throw Error('Harness 路径不是文件');}
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
