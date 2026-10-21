const path=require('node:path'),fs=require('node:fs');
const {packager}=require('@electron/packager');
const outIndex=process.argv.indexOf('--out');
if(outIndex>=0&&!process.argv[outIndex+1])throw Error('--out requires a directory');
const out=outIndex>=0?path.resolve(process.argv[outIndex+1]):path.resolve(__dirname,'../../build/desktop');
(async()=>{const result=await packager({dir:__dirname,out,name:'Nexarbor Workbench',executableName:'Nexarbor',platform:'win32',arch:'x64',electronVersion:require('./package.json').devDependencies.electron,...(fs.existsSync(path.resolve(__dirname,'../../build/electron-v'+require('./package.json').devDependencies.electron+'-win32-x64.zip'))?{electronZipDir:path.resolve(__dirname,'../../build')}:{}),overwrite:true,asar:false,prune:true,ignore:[/^\/node_modules/,/^\/test/,/^\/package-lock\.json$/, /^\/package\.cjs$/]});for(const target of result)console.log(target);})().catch(error=>{console.error(error);process.exitCode=1;});
