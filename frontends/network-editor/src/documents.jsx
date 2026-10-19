import React,{useState} from 'react';
import {X,Plus} from 'lucide-react';
import {CodeEditor} from './studio/editor.jsx';

export function Documents({files,onChange,onClose}){
 const [file,setFile]=useState(Object.keys(files)[0]??''),[path,setPath]=useState(''),[error,setError]=useState('');
 const create=()=>{
  const name=path.trim().replaceAll('\\','/');
  if(!name||name.startsWith('/')||name.includes(':')||name.split('/').some(p=>!p||p==='..'||p==='.')){setError('请输入运行目录内的相对文档路径');return;}
  if(Object.hasOwn(files,name)){setFile(name);setError('');return;}
  onChange({...files,[name]:''});setFile(name);setPath('');setError('');
 };
 return <div className="studio-overlay"><section className="studio-dialog" role="dialog" aria-label="网络文档" style={{display:'flex',flexDirection:'column'}}>
  <header className="studio-header"><strong>网络文档</strong><span>人格、常识、地图与其他文本；随草稿应用和存档</span><button aria-label="关闭网络文档" onClick={onClose}><X size={20}/></button></header>
  <div style={{display:'flex',flex:1,minHeight:0}}><aside className="studio-sidebar" style={{width:260,flexShrink:0}}>
   <input aria-label="新文档相对路径" placeholder="例如 personas/new.md" value={path} onChange={e=>setPath(e.target.value)}/><button onClick={create}><Plus size={14}/>添加文档</button>
   {Object.keys(files).sort().map(name=><button key={name} className={name===file?'active':''} onClick={()=>setFile(name)}>{name}</button>)}
  </aside><main style={{flex:1,minWidth:0,display:'flex',flexDirection:'column'}}><p>{file||'先添加文档'} · 修改自动进入网络草稿</p>
   {file&&typeof files[file]==='object'&&files[file]!==null?<p className="notice">二进制数据资源随节点独立复制和存档，请通过对应节点的数据工具读写。</p>:file&&<div style={{flex:1,minHeight:0}}><CodeEditor file={file} value={files[file]??''} onChange={text=>onChange({...files,[file]:text})}/></div>}
   {error&&<p role="status">{error}</p>}
  </main></div>
 </section></div>;
}
