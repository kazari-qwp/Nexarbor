// Empty bootstrap placeholders do not constitute a restored project.
export function isProjectBootstrap(document,bootstrap){
 const nodes=document?.network?.nodes,expected=bootstrap?.network?.nodes;
 if(!Array.isArray(nodes)||!expected?.length||nodes.length!==expected.length)return false;
 const byId=new Map(expected.map(n=>[n.node_id,n]));
 const fields=['type','node_id','name','description','divergence','parameters','connections','modules','agent','execution','offered_tools','toolboxes','expose','inputs','context_cursor'];
 return nodes.every(n=>{const seed=byId.get(n.node_id);return seed&&fields.every(k=>JSON.stringify(n[k]??null)===JSON.stringify(seed[k]??null));});
}
