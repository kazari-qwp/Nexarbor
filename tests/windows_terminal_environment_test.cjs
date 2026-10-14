// Real native confined PowerShell with PYTHONPATH overwritten; no paid model.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),cp=require('node:child_process');
const {pathToFileURL}=require('node:url');
const sdk=process.env.DATANET_NATIVE_MODULES??'C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules';
const {AclSandbox,workspaceWriteSid}=require(path.join(sdk,'@deepseek-ai/dsh-sandbox-windows-acl'));
const root=path.resolve(__dirname,'..'),base=path.join(root,'build/test-data');fs.mkdirSync(base,{recursive:true});
const owned=fs.mkdtempSync(path.join(base,'terminal-env-')),outside=fs.mkdtempSync(path.join(base,'terminal-outside-'));
(async()=>{
 const {prepareWindowsWorkspace}=await import(pathToFileURL(path.join(root,'adapters/harness/framework/windows-workspace.js')));
 const terminal=await import(pathToFileURL(path.join(root,'adapters/harness/framework/windows-terminal.js')));
 await prepareWindowsWorkspace(owned);
 const previousPath=process.env.PATH;
 let noPython;
 try{process.env.PATH='';noPython=await terminal.prepareWindowsPythonTerminal(path.join(owned,'without-python'));}
 finally{if(previousPath===undefined)delete process.env.PATH;else process.env.PATH=previousPath;}
 assert.equal(noPython.python,null);
 assert.ok(!terminal.windowsPythonCommand('Get-Location',noPython).includes('$env:PATH='));
 const environment=await terminal.prepareWindowsPythonTerminal(owned);
 assert.deepEqual(await terminal.prepareWindowsPythonTerminal(owned),environment);
 const custom=path.join(owned,'custom');fs.mkdirSync(custom);fs.writeFileSync(path.join(custom,'model_module.py'),'VALUE = 42');
 const code=`import os,sys,tempfile,shutil,subprocess,model_module
assert model_module.VALUE == 42
assert os.path.normcase(tempfile.gettempdir()) == os.path.normcase(os.environ['TEMP'])
p=tempfile.mkdtemp()
os.mkdir(os.path.join(p,'private'),0o700)
open(os.path.join(p,'private','data.txt'),'w').write('ok')
shutil.rmtree(p)
r=subprocess.run([sys.executable,'-c',"import tempfile,shutil; p=tempfile.mkdtemp(); open(p+'/child.txt','w').close(); shutil.rmtree(p)"],capture_output=True,text=True)
assert r.returncode == 0,r.stderr
print('private temp, model imports and Python subprocess passed')`;
 const file=path.join(owned,'check.py');fs.writeFileSync(file,code);
 const sandbox=new AclSandbox({mode:'workspace-write',writableDirs:[owned],tempDir:null,writeSid:workspaceWriteSid(owned)});await sandbox.init();
 const shell=process.env.DATANET_TEST_PWSH??'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe';
 const literal=s=>"'"+s.replaceAll("'","''")+"'";
 const run=async command=>{const r=await sandbox.spawn({command:shell,args:['-NoProfile','-NonInteractive','-Command',terminal.windowsPythonCommand(command,environment)],cwd:owned}).wait();return {exitCode:r.exitCode,stdout:r.stdout.toString(),stderr:r.stderr.toString()};};
 try{
  const success=await run('$env:PYTHONPATH='+literal(custom)+'; python '+literal(file));assert.equal(success.exitCode,0,JSON.stringify(success));
  const deniedFile=path.join(owned,'denied.py');fs.writeFileSync(deniedFile,'open('+JSON.stringify(path.join(outside,'denied.txt'))+',"w").close()');
  const denied=await run('python '+literal(deniedFile));assert.notEqual(denied.exitCode,0);assert.ok(!fs.existsSync(path.join(outside,'denied.txt')));
  assert.match(terminal.windowsPythonFailureHint({isError:true,content:[{type:'text',text:'ModuleNotFoundError'}]}),/项目根目录/);
  const result={success,outsideDenied:denied.exitCode,python:environment.python,temporary:environment.temporary};fs.writeFileSync(path.join(owned,'result.json'),JSON.stringify(result,null,2));
  console.log('PASS native sandbox: overwritten PYTHONPATH, private temp write/delete, custom imports, nested Python, outside denial');console.log('Evidence: '+path.join(owned,'result.json'));
 }finally{sandbox.dispose();}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
