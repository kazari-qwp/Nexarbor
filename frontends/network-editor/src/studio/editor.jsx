import React,{useEffect,useRef} from 'react';
import {EditorView,basicSetup} from 'codemirror';
import {EditorState} from '@codemirror/state';
import {python} from '@codemirror/lang-python';
import {json} from '@codemirror/lang-json';
import {MergeView} from '@codemirror/merge';
const theme=EditorView.theme({'&':{height:'100%',background:'#101923',color:'#d4dde8'},'.cm-scroller':{overflow:'auto',fontFamily:'Consolas, monospace',fontSize:'13px'},'.cm-gutters':{background:'#141e29',color:'#6e8397',border:'none'},'.cm-content':{caretColor:'#8bd9bf'},'&.cm-focused .cm-cursor':{borderLeftColor:'#8bd9bf'}},{dark:true});
export function CodeEditor({file,value,onChange,original,diff=false,readOnly=false}){
 const element=useRef(),editor=useRef(),change=useRef(onChange);change.current=onChange;
 useEffect(()=>{
  const extensions=[basicSetup,theme,file.endsWith('.py')?python():file.endsWith('.json')?json():[],EditorState.readOnly.of(readOnly),EditorView.updateListener.of(update=>{if(update.docChanged)change.current?.(update.state.doc.toString());})];
  if(diff){const view=new MergeView({parent:element.current,a:{doc:original??'',extensions:[basicSetup,theme,EditorState.readOnly.of(true)]},b:{doc:value,extensions},collapseUnchanged:{margin:3,minSize:8}});editor.current=view.b;return()=>{editor.current=null;view.destroy();};}
  const view=new EditorView({parent:element.current,doc:value,extensions});editor.current=view;return()=>{editor.current=null;view.destroy();};
 },[file,diff,readOnly,original]);
 useEffect(()=>{const view=editor.current;if(view&&view.state.doc.toString()!==value)view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value}});},[value]);
 return <div className="studio-code" ref={element} aria-label={diff?'源码变更对比':'模块源码编辑器'}/>;
}
