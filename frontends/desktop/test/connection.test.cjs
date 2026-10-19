const test=require('node:test'),assert=require('node:assert/strict');
const {validateAddress,localNavigation}=require('../connection.cjs');
const token='a'.repeat(64);
test('connection requires a credentialed local root; restored local branches remain navigable',()=>{
 assert.equal(validateAddress('http://127.0.0.1:1234/#token='+token),'http://127.0.0.1:1234/#token='+token);
 for(const url of ['https://example.com/#token='+token,'file:///etc/passwd','http://user@127.0.0.1:1234/#token='+token,'http://127.0.0.1:1234/api#token='+token,'http://127.0.0.1:1234/?token='+token,'http://127.0.0.1:1234/#token=short'])assert.throws(()=>validateAddress(url));
 assert.equal(localNavigation('http://127.0.0.1:5678/'),true);assert.equal(localNavigation('https://example.com/'),false);assert.equal(localNavigation('http://127.0.0.1:1234/api'),false);
});

const http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path');
const {activeConnection}=require('../connection.cjs');
test('reopen only reuses a responsive workbench with the matching credential and rejects stale or foreign servers',async()=>{
 const base=path.resolve(__dirname,'../../../build/desktop-connection-tests');await fs.mkdir(base,{recursive:true});const home=await fs.mkdtemp(path.join(base,'run-')),file=path.join(home,'connection.json');let credential=token,shape=true;
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','application/json');if(req.headers['x-nexarbor-token']!==credential){res.statusCode=401;res.end('{}');return;}res.end(JSON.stringify(shape?{value:{live:{document:{network:{nodes:[]}}}}}:{value:{ok:true}}));});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const url='http://127.0.0.1:'+server.address().port+'/#token='+token;await fs.writeFile(file,JSON.stringify({url}));
 try{assert.equal(await activeConnection(file),url);credential='b'.repeat(64);assert.equal(await activeConnection(file),null);credential=token;shape=false;assert.equal(await activeConnection(file),null);}
 finally{await new Promise(resolve=>server.close(resolve));}
 assert.equal(await activeConnection(file,{timeout:100}),null);assert.equal(await activeConnection(path.join(home,'missing.json')),null);
});
