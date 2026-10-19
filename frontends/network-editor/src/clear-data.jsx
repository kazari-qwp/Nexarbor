import React,{useState} from 'react';
import {Trash2} from 'lucide-react';
import {isDataNode} from './data-edit.js';

export function ClearDataButton({node,onClear,disabled=false}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 if(!isDataNode(node))return null;
 const clear=async()=>{setBusy(true);setError('');try{await onClear();}catch(e){setError(e.message);}finally{setBusy(false);}};
 return <div className="clear-node-data"><button className="danger" aria-label="清空节点数据" title="清空本节点存储数据，保留名称、链接、模块、工具及配置" disabled={disabled||busy} onClick={clear}><Trash2 size={14}/>{busy?'正在清空…':'清空数据'}</button>{error&&<p className="notice" role="alert">{error}</p>}</div>;
}
