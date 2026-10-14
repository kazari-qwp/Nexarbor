// Real Harness restricted tokens; no model or paid API.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),cp=require('node:child_process');
const {pathToFileURL}=require('node:url');
const sdk=process.env.DATANET_NATIVE_MODULES??'C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules';
const {AclSandbox,workspaceWriteSid,tempWriteSid}=require(path.join(sdk,'@deepseek-ai/dsh-sandbox-windows-acl'));
const root=path.resolve(__dirname,'..'),base=path.join(root,'build/test-data');fs.mkdirSync(base,{recursive:true});
const sid=cp.execFileSync('whoami',['/user','/fo','csv','/nh'],{encoding:'utf8'}).match(/S-1-5-[0-9-]+/)[0];
function directory(prefix){
 const value=fs.mkdtempSync(path.join(base,prefix));
 assert.ok(path.resolve(value).startsWith(path.resolve(base)+path.sep));
 cp.execFileSync('icacls',[value,'/grant',`*${sid}:(OI)(CI)F`,'/Q']);return value;
}
const dir=directory('private-acl-'),temp=directory('private-temp-'),other=directory('private-other-');
const modes=[],effects=[],ctx={effect(fn){effects.push(fn());}},python='E:/miniconda3/envs/ml/python.exe';
async function run(sandbox,code,executable=python){
 const result=await sandbox.spawn({command:executable,args:['-c',code],cwd:dir}).wait();
 return {exitCode:result.exitCode,stdout:result.stdout.toString(),stderr:result.stderr.toString()};
}
const code=`import os,tempfile,shutil\np=tempfile.mkdtemp(dir=os.getcwd())\nos.makedirs(os.path.join(p,'nested'),mode=0o700)\nwith open(os.path.join(p,'nested','data.txt'),'w') as f: f.write('ok')\ntry:\n os.mkdir(p,0o700)\nexcept FileExistsError: pass\nelse: raise AssertionError('mkdir lost FileExistsError')\nshutil.rmtree(p)\nprint('private write and cleanup passed')`;
(async()=>{
 const sandbox=new AclSandbox({mode:'workspace-write',writableDirs:[dir],tempDir:temp,writeSid:workspaceWriteSid(dir),tempWriteSid:tempWriteSid(temp)});modes.push(sandbox);await sandbox.init();
 const ordinary=await run(sandbox,`import os,shutil\np='ordinary'\nos.mkdir(p)\nopen(p+'/x','w').close()\nshutil.rmtree(p)`);assert.equal(ordinary.exitCode,0,JSON.stringify(ordinary));
 const baseline=await run(sandbox,code);assert.notEqual(baseline.exitCode,0);
 const previous=process.env.PYTHONPATH;
 const compat=await import(pathToFileURL(path.join(root,'adapters/harness/framework/windows-python.js')));
 compat.installWindowsPythonCompat(ctx);compat.installWindowsPythonCompat(ctx);
 const fixed=await run(sandbox,code);assert.equal(fixed.exitCode,0,JSON.stringify(fixed));
 const py314=await run(sandbox,code,'E:/miniconda3/python.exe');assert.equal(py314.exitCode,0,JSON.stringify(py314));
 const privateTemp=await run(sandbox,`import tempfile,shutil\np=tempfile.mkdtemp(dir=${JSON.stringify(temp)})\nopen(p+'/x','w').close()\nshutil.rmtree(p)`);assert.equal(privateTemp.exitCode,0,JSON.stringify(privateTemp));
 const outside=await run(sandbox,`open(${JSON.stringify(path.join(other,'denied.txt'))},'w').close()`);assert.notEqual(outside.exitCode,0);
 const create=await run(sandbox,`import os\nos.mkdir('kept',0o700)\nopen('kept/x','w').close()`);assert.equal(create.exitCode,0,JSON.stringify(create));
 const peer=new AclSandbox({mode:'workspace-write',writableDirs:[other],tempDir:null,writeSid:workspaceWriteSid(other)});modes.push(peer);await peer.init();
 const cross=await run(peer,`open('kept/x','w').close()`);assert.notEqual(cross.exitCode,0);
 const readonly=new AclSandbox({mode:'read-only',writableDirs:[],tempDir:null});modes.push(readonly);await readonly.init();
 const denied=await run(readonly,`open('kept/x','w').close()`);assert.notEqual(denied.exitCode,0);
 const acl=cp.execFileSync('icacls',[path.join(dir,'kept')],{encoding:'utf8'});
 assert.ok(acl.includes(workspaceWriteSid(dir)));assert.ok(!acl.includes('S-1-1-0:(F)'));
 const normal=cp.execFileSync(python,['-c',"import os; assert os.mkdir.__module__ == 'nt'; print('unrestricted Python unchanged')"],{encoding:'utf8'});assert.match(normal,/unchanged/);
 effects.pop()();assert.notEqual(process.env.PYTHONPATH,previous);effects.pop()();assert.equal(process.env.PYTHONPATH,previous);
 const result={baseline,fixed,python314:py314,privateTemp,outsideDenied:outside.exitCode,crossWorkspaceDenied:cross.exitCode,readOnlyDenied:denied.exitCode,normalPython:normal,acl};
 fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify(result,null,2));
 console.log('PASS real Harness Windows ACL: 3.11/3.14 private directory write/delete, private temp SID, outside/cross-workspace/read-only denial, ordinary and unrestricted Python, bridge lifecycle');
 console.log('Evidence: '+path.join(dir,'result.json'));
})().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(()=>{while(effects.length)effects.pop()();for(const sandbox of modes.reverse())sandbox.dispose();});
