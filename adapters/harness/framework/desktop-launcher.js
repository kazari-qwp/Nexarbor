// Operator-only desktop launch. No shell commands or model tools are involved.
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';
import {spawn} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
export function desktopCommand(connection,environment=process.env){
 if(typeof connection!=='string'||!existsSync(connection))throw new Error('工作台连接记录不存在');
 const explicit=environment.NEXARBOR_DESKTOP_EXECUTABLE;
 const packaged=path.join(root,'build/desktop/Nexarbor Workbench-win32-x64/Nexarbor Workbench.exe');
 const installed=path.join(environment.LOCALAPPDATA??'','Programs/Nexarbor Workbench/Nexarbor Workbench.exe');
 for(const exe of [explicit,packaged,installed].filter(Boolean))if(existsSync(exe))return {executable:exe,args:['--connection',path.resolve(connection)]};
 const electron=path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),entry=path.join(root,'frontends/desktop/main.cjs');
 if(existsSync(electron)&&existsSync(entry))return {executable:electron,args:[entry,'--connection',path.resolve(connection)]};
 throw new Error('请先安装 Nexarbor Workbench，或设置 NEXARBOR_DESKTOP_EXECUTABLE 指向客户端');
}
export async function launchDesktopEditor(value){
 const command=desktopCommand(value.connection_file);
 const child=spawn(command.executable,command.args,{detached:true,stdio:'ignore',windowsHide:true,env:{...process.env,ELECTRON_RUN_AS_NODE:undefined}});
 await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});child.unref();
 return {opened:true,kind:'desktop'};
}
