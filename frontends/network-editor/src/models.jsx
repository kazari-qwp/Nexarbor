import React,{useEffect,useId,useState} from 'react';
import {Plus,RefreshCw,Save,X,KeyRound,ExternalLink} from 'lucide-react';
import './models.css';

function ConnectionDialog({api,initial,onClose,onSave}){
 const [draft,setDraft]=useState(initial?{...initial,api_key:''}:{name:'',provider:'',protocol:'openai-completions',base_url:'',api_key:'',models:[]}),[models,setModels]=useState((initial?.models??[]).join('\n')),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const field=(key,value)=>setDraft(old=>({...old,[key]:value}));
 return <div className="modal-backdrop model-connection-backdrop"><section className="modal model-connection-dialog" role="dialog" aria-modal="true" aria-label={initial?'编辑 API 连接':'添加 API 连接'}><div className="modal-header"><h2>{initial?'编辑 API 连接':'添加独立 API 连接'}</h2><button aria-label="关闭 API 连接" onClick={onClose}><X size={18}/></button></div>
  <p className="muted">每条连接独立保存 key。节点各自选择连接；本机凭据使用 Windows 账户加密，项目只保存连接引用。</p>
  <label>连接名称<input aria-label="连接名称" placeholder="例如：DeepSeek · 账户 A" value={draft.name} onChange={e=>field('name',e.target.value)}/></label>
  <label>服务商<input aria-label="服务商" placeholder="服务商或本地服务名称" value={draft.provider} onChange={e=>field('provider',e.target.value)}/></label>
  <label>接口类型<select aria-label="接口类型" value={draft.protocol} onChange={e=>field('protocol',e.target.value)}><option value="openai-completions">OpenAI Chat Completions 兼容</option><option value="openai-responses">OpenAI Responses 兼容</option><option value="anthropic-messages">Anthropic Messages</option></select></label>
  <label>Base URL<input aria-label="Base URL" placeholder="https://api.example.com/v1" value={draft.base_url} onChange={e=>field('base_url',e.target.value)}/></label>
  <label>API key<input aria-label="API key" type="password" disabled={!!draft.no_key} autoComplete="new-password" placeholder={initial?.hasKey?'留空保留已有 key':'输入此连接的 key'} value={draft.api_key} onChange={e=>field('api_key',e.target.value)}/></label>
  <label className="model-checkbox"><input type="checkbox" checked={!!draft.no_key} onChange={e=>field('no_key',e.target.checked)}/>本地服务无需 key</label>
  <label>可用模型（每行一个，可稍后查询或手动填写）<textarea aria-label="连接的模型列表" rows={3} value={models} onChange={e=>setModels(e.target.value)}/></label>
  {initial&&<p className="notice">修改会影响使用这条连接的 Agent。使用另一份 key 时，请通过加号新建连接。</p>}
  {error&&<p role="alert" className="notice">{error}</p>}<div className="modal-actions"><button onClick={onClose}>取消</button><button className="primary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const {hasKey,kind,...value}=draft;const saved=await api('models.connection.save',{...value,models:models.split(/[\n,]/).map(value=>value.trim()).filter(Boolean)});setDraft(old=>({...old,api_key:''}));await onSave(saved);onClose();}catch(error){setError(error.message);}finally{setBusy(false);}}}><Save size={14}/>{busy?'保存中…':'保存连接'}</button></div>
 </section></div>;
}

export function ModelPanel({api,value,onChange,scope='project',disabled=false}){
 const id=useId(),[data,setData]=useState(null),[local,setLocal]=useState(null),[changed,setChanged]=useState(false),[dialog,setDialog]=useState(null),[error,setError]=useState(''),[discovered,setDiscovered]=useState([]),[busy,setBusy]=useState(false);
 const controlled=!!onChange,chosen=controlled?(value??null):local;
 const load=async()=>{const next=await api('models.list');setData(next);return next;};
 useEffect(()=>{let alive=true;api('models.list').then(next=>{if(alive){setData(next);setLocal(next.scopes[scope]??null);setChanged(false);}}).catch(error=>setError(error.message));return()=>{alive=false;};},[scope]);
 const update=next=>{setError('');setDiscovered([]);if(controlled)onChange(next);else{setLocal(next);setChanged(true);}};
 const connection=data?.connections.find(item=>item.id===chosen?.connection),defaultChoice=data?.scopes.project??{connection:'harness-default',model:'deepseek-flash'};
 return <section className="model-panel" aria-label="模型选择"><p className="muted">{scope==='project'&&!controlled?'设置当前项目的默认模型。':'此 Agent 的模型选择独立保存；使用不同 key 时选择不同连接。'}</p>
  <label className="model-checkbox"><input type="checkbox" aria-label="使用默认模型" checked={!chosen} disabled={disabled} onChange={e=>update(e.target.checked?null:{...defaultChoice})}/>{scope==='project'&&!controlled?'使用 Harness 默认账户':'使用项目默认模型'}</label>
  <label>服务商连接<div className="model-connection-row"><select aria-label="服务商连接" value={chosen?.connection??defaultChoice.connection} disabled={disabled||!chosen} onChange={e=>{const item=data.connections.find(item=>item.id===e.target.value);update({...chosen,connection:item.id,model:item.models[0]??chosen.model});}}>{data?.connections.map(item=><option key={item.id} value={item.id}>{item.name} · {item.provider}</option>)}{chosen&&!connection&&<option value={chosen.connection}>连接不可用 · {chosen.connection}</option>}</select><button aria-label="添加 API 连接" title="添加一条独立服务商连接和 key" disabled={disabled} onClick={()=>setDialog({})}><Plus size={16}/></button>{connection?.kind==='api-key'&&<button title="编辑当前连接" aria-label="编辑 API 连接" disabled={disabled} onClick={()=>setDialog(connection)}><KeyRound size={15}/></button>}</div></label>
  <label>模型<input aria-label="模型名称" list={id} value={chosen?.model??defaultChoice.model} disabled={disabled||!chosen} placeholder="选择或填写模型名称" onChange={e=>update({...chosen,model:e.target.value})}/><datalist id={id}>{[...new Set([...(connection?.models??[]),...discovered])].map(model=><option key={model} value={model}/>)}</datalist></label>
  {connection?.kind==='api-key'&&chosen&&<button className="model-discover" disabled={busy||disabled} onClick={async()=>{setBusy(true);setError('');try{const value=await api('models.discover',{id:connection.id});setDiscovered(value.models);setError('连接成功，可用模型：'+(value.models.join('、')||'服务商未返回列表，可手动填写'));}catch(error){setError(error.message);}finally{setBusy(false);}}}><RefreshCw size={13}/>{busy?'查询中…':'测试连接并查询模型'}</button>}
  {chosen&&<details><summary>生成参数</summary><label>思考强度<select aria-label="模型思考强度" value={chosen.reasoning_effort??''} disabled={disabled} onChange={e=>{const next={...chosen};e.target.value?next.reasoning_effort=e.target.value:delete next.reasoning_effort;update(next);}}>{[['','使用连接默认'],['off','关闭'],['minimal','最低'],['low','低'],['medium','中'],['high','高'],['xhigh','更高'],['max','最高']].map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>{[['max_tokens','最大输出 token'],['context_window','上下文窗口']].map(([key,label])=><label key={key}>{label}<input type="number" min="1" aria-label={label} disabled={disabled} placeholder="使用默认值" value={chosen[key]??''} onChange={e=>{const next={...chosen};e.target.value?next[key]=Number(e.target.value):delete next[key];update(next);}}/></label>)}</details>}
  <p className="muted">切换模型或 key 后会保留原历史，后续运行从当前上下文建立分支。{controlled?'节点设置在校验并更新网络后生效。':''}</p>
  {!controlled&&<button className="primary" disabled={disabled||!changed||busy||!!chosen&&!chosen.model.trim()} onClick={async()=>{setBusy(true);try{await api('models.selection.save',{scope,selection:chosen});setChanged(false);await load();setError('模型选择已保存');}catch(error){setError(error.message);}finally{setBusy(false);}}}><Save size={14}/>保存模型选择</button>}
  {error&&<p role="status" className="notice">{error}</p>}{dialog&&<ConnectionDialog api={api} initial={dialog.id?dialog:undefined} onClose={()=>setDialog(null)} onSave={async saved=>{await load();update({...chosen,connection:saved.id,model:saved.id===chosen?.connection?chosen.model:saved.models[0]??chosen?.model??''});}}/>}
 </section>;
}
export function ModelSettings({api,onClose}){return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="项目模型设置"><div className="modal-header"><h2>项目默认模型与 API</h2><button aria-label="关闭模型设置" onClick={onClose}><X size={18}/></button></div><ModelPanel api={api} scope="project"/></section></div>;}
export function ExternalEditorPreferences({api}){
 const [editor,setEditor]=useState(''),[message,setMessage]=useState('');useEffect(()=>{api('preferences.get').then(value=>setEditor(value.external_editor??'')).catch(error=>setMessage(error.message));},[]);
 return <section className="external-editor-preferences"><h3>外部文本编辑器</h3><label>编辑器 .exe 完整路径<input aria-label="外部文本编辑器路径" placeholder="留空使用系统默认程序" value={editor} onChange={e=>setEditor(e.target.value)}/></label><button onClick={async()=>{try{await api('preferences.save',{external_editor:editor});setMessage('已保存编辑器设置');}catch(error){setMessage(error.message);}}}><ExternalLink size={14}/>保存编辑器设置</button>{message&&<p role="status">{message}</p>}</section>;
}
