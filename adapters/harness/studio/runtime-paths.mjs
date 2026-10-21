import fs from 'node:fs/promises';
import path from 'node:path';

// 运行包优先使用随包的 Python，源码开发使用 .venv；不依赖打包机器的路径。
export async function pythonExecutable(root){
 if(process.env.DATANET_PYTHON)return path.resolve(process.env.DATANET_PYTHON);
 const candidates=[path.join(root,'runtime/python/python.exe'),path.join(root,'.venv/Scripts/python.exe')];
 for(const candidate of candidates)try{await fs.access(candidate);return candidate;}catch(error){if(error.code!=='ENOENT')throw error;}
 throw Error('找不到 Python 运行时。请完整解压 0.9 运行包；源码开发请创建 .venv，或设置 DATANET_PYTHON。');
}
