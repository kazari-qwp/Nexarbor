// Native Windows ACL compatibility only; no DataNet business policy.
import path from 'node:path';
import {fileURLToPath} from 'node:url';
let users=0,previous,installed;
export function installWindowsPythonCompat(ctx){
  if(process.platform!=='win32')return;
  if(users++===0){
    previous=process.env.PYTHONPATH;
    const directory=fileURLToPath(new URL('../compat/windows_python/',import.meta.url));
    installed=[directory,previous].filter(Boolean).join(path.delimiter);
    process.env.PYTHONPATH=installed;
  }
  ctx.effect(()=>()=>{
    if(--users===0&&process.env.PYTHONPATH===installed){
      if(previous===undefined)delete process.env.PYTHONPATH;else process.env.PYTHONPATH=previous;
    }
  },'datanet.windows-python');
}
