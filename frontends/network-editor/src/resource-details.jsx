import React,{useState} from 'react';
import {BookmarkPlus,Box,Wrench,Save,Trash2} from 'lucide-react';
import validator from '@rjsf/validator-ajv8';
import {ModuleConfig,enrichSchema} from './module-config.jsx';
import {ResourceRelations} from './resource-badges.jsx';

export function ResourceDetails({value,catalog,nodes,api,onSave}){
 const [asset,setAsset]=useState(()=>structuredClone(value.asset)),[name,setName]=useState(value.name),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const module=asset.kind==='module',definition=module?catalog.modules[asset.id]:catalog.tools?.find(t=>t.ref===asset.id),Icon=module?Box:Wrench;
 const save=async()=>{setError('');setSaving(true);try{if(!definition)throw Error('该资源已不在当前目录中');if(!name.trim())throw Error('名称不能为空');if(module){const result=validator.rawValidation(enrichSchema(definition.schema,nodes),asset.config);if(result.errors?.length)throw Error('配置不符合模块声明：'+result.errors.map(e=>e.message).join('；'));}await onSave({...value,name:name.trim(),asset});}catch(e){setError(e.message);}finally{setSaving(false);}};
 return <section className="resource-details" aria-label={module?'模块资源详情':'工具资源详情'}><div className="inspector-intro"><Icon size={22}/><strong>{value.name}</strong><small>{asset.id}</small></div><p className="muted">{value.description}</p><label>书签名称<input aria-label="资源书签名称" value={name} onChange={e=>setName(e.target.value)}/></label>
  <ResourceRelations value={value} catalog={catalog}/>{module?<><p className="muted">编辑待装配配置；页面未挂载到节点。保存后可从书签拖到节点上。</p>{definition?<ModuleConfig api={api} module={asset.id} definition={definition} nodes={nodes} config={asset.config} state={asset.state??{}} onChange={config=>setAsset(old=>({...old,config}))}/>:<p className="notice">模块已不在当前组件库，预设仍保存在书签中。</p>}<details><summary>网络访问授权</summary><label>强度<input type="number" min="0" value={asset.access?.strength??0} onChange={e=>setAsset(old=>({...old,access:{...old.access,strength:Number(e.target.value)}}))}/></label><label>频道<input value={(asset.access?.channels??[]).join(', ')} onChange={e=>setAsset(old=>({...old,access:{...old.access,channels:e.target.value.split(',').map(s=>s.trim()).filter(Boolean)}}))}/></label></details></>:<><label>提供频道<input disabled={!!definition?.module} aria-label="资源工具频道" value={asset.channels.join(', ')} onChange={e=>setAsset(old=>({...old,channels:e.target.value.split(',').map(s=>s.trim()).filter(Boolean)}))}/></label><details><summary>工具定义</summary><pre>{JSON.stringify(definition,null,2)}</pre></details></>}
  {error&&<p role="alert" className="notice">{error}</p>}<button className="primary resource-save" disabled={saving} onClick={save}><Save size={14}/>Save · 保存至书签</button>
 </section>;
}
