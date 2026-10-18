import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// 项目本地记录不随包发布；环境变量始终优先。
export async function harnessExecutable(){
  if(process.env.DATANET_HARNESS_EXE)return process.env.DATANET_HARNESS_EXE;
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
  throw Error('请先在组件工作室启用本机账户，或在项目本地安装记录中配置授权文件位置。');
}
