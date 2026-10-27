import React,{useState} from 'react';
import Markdown from 'markdown-to-jsx';
import {FileText,ExternalLink} from 'lucide-react';
import './message-content.css';
const local=value=>/^[a-z]:[\\/]/i.test(value)||value.startsWith('/')||value.startsWith('file:');
function safeUrl(value){const url=String(value??'').trim();if(local(url)&&!url.startsWith('//'))return url;if(/^https?:\/\//i.test(url))return url;return null;}
export function RichText({text,api,onError=()=>{}}){
 const Link=({href,children})=>{const url=safeUrl(href);if(!url)return <span>{children}</span>;if(local(url))return <button className="message-file-link" onClick={()=>Promise.resolve().then(()=>api?.('file.reveal',{path:decodeURI(url.replace(/^file:\/\/\//,''))})).catch(e=>onError(e.message))}><FileText size={12}/>{children}</button>;return <a href={url} target="_blank" rel="noreferrer noopener">{children}<ExternalLink size={11}/></a>;};
 // Never evaluate generated HTML/JSX. Native image attachments are rendered separately.
 const Image=({src,alt})=><Link href={src}>{alt||'查看图片'}</Link>;
 return <div className="message-text markdown-body"><Markdown options={{forceBlock:true,disableParsingRawHTML:true,wrapper:'div',sanitizer:safeUrl,overrides:{a:Link,img:Image}}}>{String(text??'')}</Markdown></div>;
}
function resultSummary(text){
 try{const v=JSON.parse(text);if(v.kind==='detail'&&v.region)return v.region+' 局部 · '+((v.nodes?.length??0)+(v.index_omitted??0))+' 个完整节点';if(v.kind==='overview'&&v.counts)return '网络概览 · '+v.counts.shown_nodes+'/'+v.counts.total_nodes+' 节点'+(v.regions?.length?' · '+v.regions.length+' 个可放大区域':'');}catch{}
 try{const v=JSON.parse(text),parts=[];for(const [key,name] of [['nodes','节点'],['edges','连线'],['modules','模块'],['tools','工具']])if(Array.isArray(v[key]))parts.push(v[key].length+' 个'+name);if(v.counts?.shown_nodes!=null)parts.push('显示 '+v.counts.shown_nodes+'/'+v.counts.total_nodes+' 节点');if(v.status)parts.push(String(v.status));return parts.join(' · ')||'结构化结果';}catch{return String(text).replace(/\s+/g,' ').slice(0,70)||'工具结果';}
}
function ToolResult({text,api,onError}){
 const [open,setOpen]=useState(false);let json;try{json=JSON.parse(text);}catch{}
 return <details className="message-tool-result" onToggle={e=>setOpen(e.currentTarget.open)}><summary>{resultSummary(text)}<span>展开结果</span></summary>{open&&(json!==undefined?<pre>{JSON.stringify(json,null,2)}</pre>:<RichText text={text} api={api} onError={onError}/>)}</details>;
}
export function MessageContent({message,previews,api,onError}){
 const preview=id=>Array.isArray(previews)?previews.find(p=>p.id===id)?.preview:previews?.[id];
 const blocks=typeof message.content==='string'?[{type:'text',text:message.content}]:message.content??[];
 return blocks.map((b,j)=>b.type==='text'?(message.role==='tool'?<ToolResult key={j} text={b.text} api={api} onError={onError}/>:<RichText key={j} text={b.text} api={api} onError={onError}/>):b.type==='image'?<figure key={j} className="message-image">{preview(b.attachment?.attachmentId)?<img alt={b.attachment?.name??'图片附件'} src={preview(b.attachment?.attachmentId)}/>:<figcaption>{b.attachment?.name??'图片附件'}</figcaption>}</figure>:<details key={j}><summary>{b.type==='tool-call'?'调用工具':b.type==='reasoning'?'思考':b.type} {b.name??''}</summary><pre>{JSON.stringify(b,null,2)}</pre></details>);
}
