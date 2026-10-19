import React,{useEffect,useMemo,useRef,useState} from 'react';
import Form from '@rjsf/core';
import {Plus,Trash2,ArrowUp,ArrowDown,Copy,X} from 'lucide-react';
import './schema-buttons.css';
import validator from '@rjsf/validator-ajv8';
import {getDefaultFormState,deepEquals} from '@rjsf/utils';
const protocol='nexarbor-module-frontend/v1';
const copy=value=>JSON.parse(JSON.stringify(value));

export function enrichSchema(schema,nodes=[]){
  const result=copy(schema);
  if(result.format==='node-id'){delete result.format;const nullable=result.type==='null'||Array.isArray(result.type)&&result.type.includes('null');result.enum=[...(nullable?[null]:[]),...nodes.map(n=>n.node_id)];result.enumNames=[...(nullable?['未指定']:[]),...nodes.map(n=>n.name+' · '+n.node_id)];}
  if(result.format==='textarea')delete result.format;
  if(result.properties)for(const key in result.properties)result.properties[key]=enrichSchema(result.properties[key],nodes);
  if(result.items&&typeof result.items==='object')result.items=enrichSchema(result.items,nodes);
  for(const key of ['oneOf','anyOf','allOf'])if(result[key])result[key]=result[key].map(value=>enrichSchema(value,nodes));
  return result;
}
// 使用真正的 SVG 图标，避免默认 Bootstrap 字体未加载时留下空白按钮。
function ActionButton({icon:Icon,label,className='',id,onClick,disabled,style}){
  return <button type="button" id={id} className={'schema-action '+className} title={label} aria-label={label} onClick={onClick} disabled={disabled} style={style}><Icon size={14}/></button>;
}
const buttonTemplates={
  AddButton:props=><ActionButton {...props} className="schema-add" icon={Plus} label="添加"/>,
  RemoveButton:props=><ActionButton {...props} className="schema-remove" icon={Trash2} label="删除此项"/>,
  MoveUpButton:props=><ActionButton {...props} icon={ArrowUp} label="上移"/>,
  MoveDownButton:props=><ActionButton {...props} icon={ArrowDown} label="下移"/>,
  CopyButton:props=><ActionButton {...props} icon={Copy} label="复制此项"/>,
  ClearButton:props=><ActionButton {...props} icon={X} label="清空此项"/>,
};
export function SchemaForm({schema,value,onChange,nodes=[],readOnly=false}){
  const enriched=useMemo(()=>enrichSchema(schema,nodes),[schema,nodes]);
  // 默认值只用于展示；库的初始化回调不能把浏览表单变成网络编辑。
  const displayed=useMemo(()=>getDefaultFormState(validator,enriched,value,enriched),[enriched,value]);
  return <Form templates={{ButtonTemplates:buttonTemplates}} schema={enriched} validator={validator} formData={displayed} disabled={readOnly}
    onChange={event=>{if(!deepEquals(event.formData,displayed))onChange(event.formData);}} liveValidate={false} omitExtraData={false}
    uiSchema={{'ui:submitButtonOptions':{norender:true}}}><span/></Form>;
}

function ModuleFrontend({api,module,source,definition,node,config,state,onChange,nodes,readOnly,revision}){
  const frame=useRef(),latest=useRef(),[page,setPage]=useState(null),[error,setError]=useState(''),[height,setHeight]=useState(definition.frontend.height??320);
  const instance=useMemo(()=>crypto.randomUUID(),[module,node?.node_id]);
  const context={instance,module,node:node?{id:node.node_id,name:node.name,type:node.type}:null,
    config:copy(config),state:copy(state??{}),configSchema:copy(definition.schema),readOnly};
  latest.current={context,onChange,nodes};
  const sendContext=()=>frame.current?.contentWindow?.postMessage({protocol,type:'context',context:latest.current.context},'*');
  const sourceKey=JSON.stringify(source??{module});
  useEffect(()=>{
    let alive=true;setPage(null);setError('');
    api('module.frontend',JSON.parse(sourceKey)).then(value=>{
      if(!alive)return;if(!value)throw Error('模块未声明前端页面');setPage(value);setHeight(value.height);
    }).catch(error=>{if(alive)setError(error.message);});
    return()=>{alive=false;};
  },[api,sourceKey,revision]);
  useEffect(sendContext,[config,state,node?.name,readOnly,page,instance]);
  useEffect(()=>{
    const receive=event=>{
      if(event.source!==frame.current?.contentWindow||event.data?.protocol!==protocol)return;
      const message=event.data,{context,onChange,nodes}=latest.current;
      if(message.type==='ready'){sendContext();return;}
      if(message.instance!==context.instance)return;
      if(message.type==='resize'){
        if(Number.isFinite(message.height))setHeight(Math.max(160,Math.min(900,Math.ceil(message.height))));
        return;
      }
      if(message.type==='preview'&&typeof message.id==='string'){
        const reply=result=>event.source.postMessage({protocol,type:'result',id:message.id,...result},'*');
        if(!definition.frontend.preview_operation||!context.node){reply({error:'请在已装配节点上预览'});return;}
        api('module.preview',{node:context.node.id,module:context.module,config:context.config}).then(value=>reply({value}),error=>reply({error:error.message}));return;
      }
      if(message.type!=='set-config'||typeof message.id!=='string')return;
      const reply=result=>event.source.postMessage({protocol,type:'result',id:message.id,...result},'*');
      try{
        if(context.readOnly)throw Error('当前模块配置只读');
        if(!message.config||typeof message.config!=='object'||Array.isArray(message.config))throw Error('模块配置必须是对象');
        const encoded=JSON.stringify(message.config);if(new TextEncoder().encode(encoded).length>1024*1024)throw Error('模块配置超过 1 MiB');
        const value=JSON.parse(encoded),validation=validator.rawValidation(enrichSchema(context.configSchema,nodes),value);
        if(validation.errors?.length)throw Error('配置不符合模块声明：'+validation.errors.map(e=>`${e.instancePath||'/'} ${e.message}`).join('；'));
        onChange(value);setError('');reply({value});
      }catch(error){setError(error.message);reply({error:error.message});}
    };
    window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
  },[]);
  return <div className="module-frontend">
    {!page&&!error&&<p className="muted">正在加载模块页面…</p>}
    {page&&<iframe ref={frame} className="module-frontend-frame" title={page.title+' · 模块页面'}
      sandbox="allow-scripts" referrerPolicy="no-referrer" src={page.src} style={{height}} onLoad={sendContext}/>}
    {error&&<p className="module-frontend-error" role="alert">{error}</p>}
  </div>;
}

export function ModuleConfig(props){
  const [generic,setGeneric]=useState(false);
  const custom=!!props.definition.frontend&&!generic;
  return <div className="module-config">
    {props.definition.frontend&&<button className="module-page-toggle" onClick={()=>setGeneric(value=>!value)}>{custom?'切换到通用表单':'使用模块页面'}</button>}
    {custom?(props.active===false?null:<ModuleFrontend {...props}/>):
      <SchemaForm schema={props.definition.schema} value={props.config} onChange={props.onChange} nodes={props.nodes} readOnly={props.readOnly}/>}
  </div>;
}
