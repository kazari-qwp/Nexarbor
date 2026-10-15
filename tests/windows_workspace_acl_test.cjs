// Actual native Windows restricted-token setup; no model calls.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
const sdk=process.env.DATANET_NATIVE_MODULES??'C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules';
const {AclSandbox,workspaceWriteSid}=require(path.join(sdk,'@deepseek-ai/dsh-sandbox-windows-acl'));
const root=path.resolve(__dirname,'..'),parent=path.join(root,'build/test-data');fs.mkdirSync(parent,{recursive:true});
const owned=fs.mkdtempSync(path.join(parent,'owner-acl-')),outside=fs.mkdtempSync(path.join(parent,'owner-outside-'));
const make=()=>new AclSandbox({mode:'workspace-write',writableDirs:[owned],tempDir:null,writeSid:workspaceWriteSid(owned)});
(async()=>{
 const before=make();let failure;
 try{await before.init();}catch(error){failure=String(error);}finally{before.dispose();}
 assert.match(failure??'',/SetNamedSecurityInfoW.*Win32 5/);
 const {prepareWindowsWorkspace}=await import(pathToFileURL(path.join(root,'adapters/harness/framework/windows-workspace.js')));
 await prepareWindowsWorkspace(owned);await prepareWindowsWorkspace(owned);
 const sandbox=make();await sandbox.init();
 try{
  const run=async code=>{const result=await sandbox.spawn({command:'E:/miniconda3/envs/ml/python.exe',args:['-c',code],cwd:owned}).wait();return {exitCode:result.exitCode,stdout:result.stdout.toString(),stderr:result.stderr.toString()};};
  const write=await run("from pathlib import Path;Path('allowed.txt').write_text('ok');print('ok')");assert.equal(write.exitCode,0,JSON.stringify(write));
  const denied=await run('from pathlib import Path;Path('+JSON.stringify(path.join(outside,'denied.txt'))+").write_text('must not write')");assert.notEqual(denied.exitCode,0);
  const report={baselineError:failure,write,outsideDenied:denied.exitCode};fs.writeFileSync(path.join(owned,'result.json'),JSON.stringify(report,null,2));
  console.log('PASS workspace owner ACL setup: native sandbox starts, workspace write succeeds, outside write denied');console.log('Evidence: '+path.join(owned,'result.json'));
 }finally{sandbox.dispose();}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
