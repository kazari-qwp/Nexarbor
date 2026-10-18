import React from 'react';
import {Plus,Trash2} from 'lucide-react';
export function NodeConnections({node,nodes,onAdd,onRemove,gesture='右键'}){
 const links=node.connections.interfaces;
 return <section className="node-connections"><button className="wide" onClick={onAdd}><Plus size={14}/>新增连接</button><p className="muted">连接有方向。也可按住节点的 {gesture} 拖到目标，或拖动节点边缘圆点。</p>
 <div className="section-label">从本节点出发 · {links.length}</div>
 {!links.length&&<p className="muted">尚无出边</p>}
 {links.map((link,index)=><div className="node-connection-row" key={index}><div><strong>→ {nodes.find(n=>n.node_id===link.target_node_id)?.name??link.target_node_id}</strong><small>{link.target_node_id}</small><span>{link.metadata.channels.join(' · ')||'无频道'}</span></div><button aria-label={'删除连接 '+node.node_id+' → '+link.target_node_id} onClick={()=>onRemove(index)}><Trash2 size={14}/></button></div>)}
 <div className="section-label">指向本节点</div>{nodes.flatMap(n=>n.connections.interfaces.filter(l=>l.target_node_id===node.node_id).map((_,i)=><div className="node-connection-row" key={n.node_id+'-'+i}><div><strong>← {n.name}</strong><small>{n.node_id}</small></div></div>))}
 </section>;
}
