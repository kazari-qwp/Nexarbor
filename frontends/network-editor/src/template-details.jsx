import React,{useRef,useState} from 'react';
import {Box,Network,Save,Trash2,FolderOpen} from 'lucide-react';
import {mergeDataEdit,mergeClearedData} from './data-edit.js';
import {ClearDataButton} from './clear-data.jsx';
import {DataPanel} from './data-panel.jsx';
import {ValueEditor} from './fields.jsx';
import {attachResource,nodeTools} from './resources.js';
import {ModuleConfig} from './module-config.jsx';

// 待放置资源只编辑独立快照；保存或查看都不会创建运行节点。
export function TemplateDetails({value,catalog,api,onSave,onOpenNetwork}){
 const [snapshot,setSnapshot]=useState(()=>structuredClone(value.snapshot)),[name,setName]=useState(value.name),[index,setIndex]=useState(0),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const [dataEpoch,setDataEpoch]=useState(0);
 const snapshotRef=useRef(snapshot);snapshotRef.current=snapshot;
 const node=snapshot.nodes[index],network=snapshot.nodes.length>1,Icon=network?Network:Box;
 const change=fn=>setSnapshot(old=>{const next=structuredClone(old);fn(next.nodes[index],next);return next;});
 const attach=asset=>{setError('');try{const doc=attachResource({network:{nodes:snapshot.nodes},files:snapshot.files},node.node_id,asset,catalog);setSnapshot({...snapshot,nodes:doc.network.nodes});}catch(e){setError(e.message);}};
 const unmount=id=>{const dependents=Object.keys(node.modules).filter(name=>catalog.modules[name]?.requires?.includes(id));if(dependents.length){setError('请先卸载依赖此模块的模块：'+dependents.map(name=>catalog.modules[name]?.label??name).join('、'));return;}setError('');change(n=>delete n.modules[id]);};
 const clear=async()=>{const beforeNode=structuredClone(node),response=await api('data.preview',{node:beforeNode,files:snapshotRef.current.files,operation:'clear'});const next=mergeClearedData(snapshotRef.current,{...response,beforeNode});snapshotRef.current=next;setSnapshot(next);setDataEpoch(v=>v+1);};
 const save=async()=>{setError('');setSaving(true);try{if(!name.trim())throw Error('书签名称不能为空');await onSave({...value,name:name.trim(),snapshot});}catch(e){setError(e.message);}finally{setSaving(false);}};
 return <section className="resource-details" aria-label={network?'网络预设详情':'节点模板详情'}><div className="inspector-intro"><Icon size={22}/><strong>{value.name}</strong><small>{snapshot.nodes.length} 个节点 · 待放置配置</small></div><p className="muted">{value.description||'在这里编辑模板，保存后从书签拖入画布。每次放置都会分配新编号。'}</p><label>书签名称<input aria-label="资源书签名称" value={name} onChange={e=>setName(e.target.value)}/></label>
  {value.storageKind==='network'&&snapshot.nodes.some(n=>n.node_id==='root')&&onOpenNetwork&&<button className="primary" aria-label="打开完整网络" onClick={()=>onOpenNetwork(value)}><FolderOpen size={14}/>打开完整网络</button>}
  {value.file&&<label>{value.kind==='node'?'磁盘节点文件':'磁盘网络文件'}<code className="stored-network-path" title={value.file}>{value.file}</code></label>}
  {network&&<label>编辑节点<select aria-label="预设中的节点" value={index} onChange={e=>setIndex(Number(e.target.value))}>{snapshot.nodes.map((n,i)=><option key={n.node_id} value={i}>{n.name}</option>)}</select></label>}
  {node?<><ClearDataButton key={node.node_id} node={node} onClear={clear}/><label>名称<input aria-label="模板节点名称" value={node.name} onChange={e=>change(n=>n.name=e.target.value)}/></label><label>描述<textarea aria-label="模板节点描述" value={node.description??''} onChange={e=>change(n=>n.description=e.target.value)}/></label><label>节点内散度<input aria-label="模板节点散度" type="number" value={node.divergence??-1} onChange={e=>change(n=>n.divergence=Number(e.target.value))}/></label>
   {node.modules?.['data.local']&&<DataPanel key={node.node_id+':'+dataEpoch} node={node} files={snapshot.files} api={api} onChange={value=>{const next=mergeDataEdit(snapshotRef.current,value);snapshotRef.current=next;setSnapshot(next);}}/>}
   <details><summary>节点参数</summary><ValueEditor label="节点参数" value={node.parameters??{}} onChange={v=>change(n=>n.parameters=v)}/></details>
   {node.parameters?.file_path&&<label>关联文档<textarea aria-label="模板节点文档" rows={8} value={snapshot.files[node.parameters.file_path]??''} onChange={e=>change((n,s)=>s.files[n.parameters.file_path]=e.target.value)}/></label>}
   {node.type==='agent'&&<details><summary>Agent 执行配置</summary><ValueEditor label="执行配置" value={node.execution} onChange={v=>change(n=>n.execution=v)}/></details>}
   <details><summary>模块 · {Object.keys(node.modules??{}).length}</summary><select aria-label="模板添加模块" value="" onChange={e=>{const id=e.target.value;if(id)attach({kind:'module',id,...structuredClone(catalog.modules[id].defaults)});}}><option value="">装配模块…</option>{Object.entries(catalog.modules??{}).filter(([id,m])=>!node.modules[id]&&(!m.node_types||m.node_types.includes(node.type))).map(([id,m])=><option key={id} value={id}>{m.label}</option>)}</select>{Object.entries(node.modules??{}).map(([id,spec])=><details className="module-section" key={node.node_id+id}><summary>{catalog.modules[id]?.label??id}</summary>{catalog.modules[id]?<ModuleConfig api={api} module={id} definition={catalog.modules[id]} nodes={snapshot.nodes} node={node} config={spec.config} state={spec.state??{}} onChange={v=>change(n=>n.modules[id].config=v)}/>:<ValueEditor value={spec.config} onChange={v=>change(n=>n.modules[id].config=v)}/>}<ValueEditor label="网络访问授权" value={spec.access} onChange={v=>change(n=>n.modules[id].access=v)}/><button aria-label={'模板卸载模块 '+id} onClick={()=>unmount(id)}><Trash2 size={12}/>卸载</button></details>)}</details>
   <details><summary>工具 · {nodeTools(node,catalog).length}</summary><select aria-label="模板添加工具" value="" onChange={e=>{if(e.target.value){const tool=catalog.tools.find(t=>t.ref===e.target.value);attach({kind:'tool',id:tool.ref,channels:tool.channels??['tools']});}}}><option value="">装配工具…</option>{(catalog.tools??[]).filter(t=>!nodeTools(node,catalog).some(o=>o.ref===t.ref)&&(!t.module||!catalog.modules[t.module]?.node_types||catalog.modules[t.module].node_types.includes(node.type))).map(t=><option key={t.ref} value={t.ref}>{t.name}</option>)}</select>{nodeTools(node,catalog).map(t=><div key={t.ref}><strong>{catalog.tools?.find(s=>s.ref===t.ref)?.name??t.ref}</strong>{t.module?<p className="muted">由 {catalog.modules[t.module]?.label??t.module} 提供，卸载该模块后移除。</p>:<><label>提供频道<input value={t.channels.join(', ')} onChange={e=>change(n=>n.offered_tools.find(o=>o.ref===t.ref).channels=e.target.value.split(',').map(s=>s.trim()).filter(Boolean))}/></label><button onClick={()=>change(n=>n.offered_tools=n.offered_tools.filter(o=>o.ref!==t.ref))}><Trash2 size={12}/>卸载</button></>}</div>)}</details>
   <details><summary>出边 · {node.connections.interfaces.length}</summary><pre>{JSON.stringify(node.connections.interfaces,null,2)}</pre></details>
  </>:<ValueEditor label="连接配置" value={snapshot.edges} onChange={edges=>setSnapshot(s=>({...s,edges}))}/>}
  {error&&<p className="notice" role="alert">{error}</p>}<button className="primary resource-save" disabled={saving} onClick={save}><Save size={14}/>Save · 保存至书签</button>
 </section>;
}
