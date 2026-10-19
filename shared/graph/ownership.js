// Pure graph contract shared by disk resources and the editor; no host or UI imports.
export function ownershipRoots(nodes=[]){const ids=new Set(nodes.map(n=>n.node_id));return nodes.filter(n=>n.type!=='subnode'||!ids.has(n.parameters?.parent_id));}
export function singleOwnedNode(nodes=[]){
 const roots=ownershipRoots(nodes);if(roots.length!==1)return false;
 const by=new Map(nodes.map(n=>[n.node_id,n]));if(by.size!==nodes.length)return false;
 for(const node of nodes){let current=node;const seen=new Set();while(current!==roots[0]){if(current.type!=='subnode'||seen.has(current.node_id))return false;seen.add(current.node_id);current=by.get(current.parameters?.parent_id);if(!current)return false;}}
 return true;
}
