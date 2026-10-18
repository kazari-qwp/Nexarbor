// Optional loopback host for the separately built network editor.
import http from 'node:http';
import path from 'node:path';
import {readFile,writeFile} from 'node:fs/promises';
import {randomBytes,timingSafeEqual} from 'node:crypto';
import {editorLibrary} from './editor-library.js';

export async function startEditorServer({web,directory,request,chat,recover,port=0}) {
  const token=randomBytes(32).toString('hex');let authority;
  const library=editorLibrary(directory);
  const pages=new Map(),pageKeys=new Map();
  const bridge=await readFile(new URL('./module-frontend-bridge.js',import.meta.url),'utf8');
  const frontend=page=>{
    if(page===null)return null;
    if(typeof page?.html!=='string'||Buffer.byteLength(page.html)>1024*1024)throw Error('模块前端必须是 1 MiB 以内的 HTML');
    const key=page.module+'\0'+page.html;
    let id=pageKeys.get(key);
    if(!id){
      id=randomBytes(24).toString('hex');pageKeys.set(key,id);
      const script='<script>'+bridge+'</script>';
      const html=/<head(?:\s[^>]*)?>/i.test(page.html)?page.html.replace(/<head(?:\s[^>]*)?>/i,match=>match+script):script+page.html;
      pages.set(id,{html,key});
      if(pages.size>128){const oldest=pages.keys().next().value;pageKeys.delete(pages.get(oldest).key);pages.delete(oldest);}
    }
    return {module:page.module,title:page.title,height:page.height??320,src:'/module-frontend/'+id};
  };
  const send=(res,status,value)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  const server=http.createServer(async(req,res)=>{
    res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Referrer-Policy','no-referrer');
    res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'");
    try{
      if(req.headers.host!==authority)return send(res,403,{error:'无效的本地地址'});
      const url=new URL(req.url,'http://'+authority);
      if(url.pathname.startsWith('/module-frontend/')){
        if(req.method!=='GET')return send(res,405,{error:'GET required'});
        const page=pages.get(url.pathname.slice('/module-frontend/'.length));
        if(!page)return send(res,404,{error:'模块页面已失效，请重新打开模块'});
        res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts");
        res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end(page.html);return;
      }
      if(url.pathname==='/api'){
        if(req.method!=='POST')return send(res,405,{error:'POST required'});
        if(req.headers.origin&&req.headers.origin!=='http://'+authority)return send(res,403,{error:'仅允许编辑器同源请求'});
        const supplied=Buffer.from(req.headers['x-nexarbor-token']??'');const expected=Buffer.from(token);
        if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected))return send(res,401,{error:'请从本次启动地址打开编辑器'});
        if(!req.headers['content-type']?.startsWith('application/json'))return send(res,415,{error:'JSON required'});
        const chunks=[];let bytes=0;
        for await(const chunk of req){bytes+=chunk.length;if(bytes>8_000_000)return send(res,413,{error:'请求超过8MB'});chunks.push(chunk);}
        const {operation,params={}}=JSON.parse(Buffer.concat(chunks).toString('utf8'));
        const value=['editor.library','editor.library.update'].includes(operation)?await library(operation,params):operation?.startsWith('chat.')?await chat(operation,params):operation==='recover'?await recover(params):await request(operation,params);
        return send(res,200,{value:operation==='module.frontend'?frontend(value):value});
      }
      if(req.method!=='GET')return send(res,405,{error:'GET required'});
      const relative=decodeURIComponent(url.pathname==='/'?'index.html':url.pathname.slice(1));
      const file=path.resolve(web,relative);
      if(!file.startsWith(path.resolve(web)+path.sep))return send(res,403,{error:'Invalid asset path'});
      const content=await readFile(file);
      const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2','.wasm':'application/wasm'};
      res.writeHead(200,{'Content-Type':types[path.extname(file)]??'application/octet-stream','Cache-Control':'no-cache'});res.end(content);
    }catch(error){send(res,error.code==='ENOENT'?404:400,{error:String(error.message??error)});}
  });
  server.requestTimeout=30000;
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
  authority='127.0.0.1:'+server.address().port;
  const url='http://'+authority+'/#token='+token;
  await writeFile(path.join(directory,'editor-connection.json'),JSON.stringify({url,authority,pid:process.pid},null,2));
  return {url,authority,close:()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);})};
}
