import React from 'react';
import {Handle,Position} from '@xyflow/react';
import {Box,Wrench,CircleAlert} from 'lucide-react';
import './node-problems.css';
import './subnodes.css';
import {colors} from './model.js';

export function NetworkNode({data,selected,readonly=false}){
 if(data.host)return <div className="network-node module-view" title={[data.host.name+' · '+data.module_id,...data.channelGroups.map(group=>group.label+'：'+(group.mode==='deny'?'排除 ':'')+(group.channels.join(' / ')||'本节点'))].join('\n')}>
  <span className="node-name">{data.node.name}</span>
  {!readonly&&[Position.Left,Position.Right,Position.Top,Position.Bottom].map(side=><Handle key={side} id={side} type="source" position={side}/>)}
 </div>;
 const problems=Object.entries(data.moduleProblems??{}),problemText=problems.map(([id,reason])=>id+'：'+reason).join('\n');
 const node=data.node,tools=data.toolCount??(node.offered_tools?.length??0),modules=(node.tables?.modules??[]).length;
 return <div onDoubleClick={e=>{e.stopPropagation();if(node.type==='agent')data.openChat?.(node);}} className={'network-node '+(selected?'is-selected':'')} style={{'--node-color':colors[data.kind]}}>
  {!readonly&&[Position.Left,Position.Right,Position.Top,Position.Bottom].map(side=><Handle key={side} id={side} type="source" position={side}/>)}
  {problems.length>0&&<button className="node-problem nodrag nopan" aria-label={node.name+'的模块不可用'} title={problemText} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();data.openNodeTab?.(node,problems.every(([id])=>id.startsWith('skill:'))?'Skills':'模块');}}><CircleAlert size={17}/></button>}
  <div className="node-content"><span className="node-name">{node.name}</span><div className="node-actions">
   {[[Wrench,'工具',tools],[Box,'模块',modules]].map(([Icon,tab,count])=><button key={tab} className="node-badge nodrag nopan" aria-label={node.name+'的'+tab+'，'+count+' 个'} title={tab} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();data.openNodeTab?.(node,tab);}} onDoubleClick={e=>e.stopPropagation()}><Icon size={11}/><span>{count}</span></button>)}
  </div></div>
 </div>;
}
