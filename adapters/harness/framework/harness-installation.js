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
