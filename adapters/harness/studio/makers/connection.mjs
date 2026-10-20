// 只把授权文件路径交给本机 SDK 子进程，不把凭据内容交给模型或页面。
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {NativeRunner} from '../runtime/runner.mjs';
import {harnessCredentials} from '../../framework/harness-installation.js';
export async function nativeMakerFactory(p,callback){
 let credentials;try{credentials=await harnessCredentials({home:p.home,directory:p.directory});await fs.access(credentials);}catch(error){if(!p.modelResolver)throw error;}
 await fs.mkdir(path.join(p.directory,'studio'),{recursive:true});await fs.writeFile(path.join(p.directory,'studio/harness-connection.json'),JSON.stringify({...(credentials?{home:path.dirname(credentials)}:{}),authority:'native-sdk'}));
 return new NativeRunner(p.directory,callback,{credentials,modelResolver:p.modelResolver,script:fileURLToPath(new URL('./worker.cjs',import.meta.url)),runtime:p.runtime??{}});
}
