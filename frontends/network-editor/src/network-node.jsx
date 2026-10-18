import React from 'react';
import {Handle,Position} from '@xyflow/react';
import {Box,Wrench} from 'lucide-react';
import {colors} from './model.js';

export function NetworkNode({data,selected}){
 const node=data.node,tools=node.offered_tools?.length??0,modules=Object.keys(node.modules).length;
 return <div onDoubleClick={e=>{e.stopPropagation();if(node.type==='agent')data.openChat?.(node);}} className={'network-node '+(selected?'is-selected':'')} style={{'--node-color':colors[data.kind]}}>
  {[Position.Left,Position.Right,Position.Top,Position.Bottom].map(side=><Handle key={side} id={side} type="source" position={side}/>)}
  <div className="node-content"><span className="node-name">{node.name}</span><div className="node-actions">
   {[[Wrench,'工具',tools],[Box,'模块',modules]].map(([Icon,tab,count])=><button key={tab} className="node-badge nodrag nopan" aria-label={node.name+'的'+tab+'，'+count+' 个'} title={tab} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();data.openNodeTab?.(node,tab);}} onDoubleClick={e=>e.stopPropagation()}><Icon size={11}/><span>{count}</span></button>)}
  </div></div>
 </div>;
}
