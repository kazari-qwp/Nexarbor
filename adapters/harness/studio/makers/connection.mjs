// 只把授权文件路径交给本机 SDK 子进程，不把凭据内容交给模型或页面。
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {NativeRunner} from '../runtime/runner.mjs';
export async function nativeMakerFactory(p,callback){
 const credentials=p.home?path.join(path.resolve(p.home),'.credentials.yaml'):process.env.DATANET_MAKER_CREDENTIALS??'E:/dsh/state/.credentials.yaml';await fs.access(credentials);
 await fs.mkdir(path.join(p.directory,'studio'),{recursive:true});await fs.writeFile(path.join(p.directory,'studio/harness-connection.json'),JSON.stringify({home:path.dirname(credentials),authority:'native-sdk'}));
 return new NativeRunner(p.directory,callback,{credentials,script:fileURLToPath(new URL('./worker.cjs',import.meta.url)),runtime:p.runtime??{}});
}
