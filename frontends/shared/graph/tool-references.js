// Stable names use the same UTF-8 SHA-256 convention as the application factories.
const hash=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),byte=>byte.toString(16).padStart(2,'0')).join('');
export async function remapToolReferences(node,oldId,catalog,properties={}){
 const names=new Map();
 for(const module of node.tables?.modules??[]){
  const before=(await hash(oldId+'\0'+module.module_id)).slice(0,24),after=(await hash(node.node_id+'\0'+module.module_id)).slice(0,24);
  for(const tool of catalog[module.module_id]?.agent_tools??[]){
   const oldName='mod_'+(await hash(before+'\0'+tool.id)).slice(0,24),newName='mod_'+(await hash(after+'\0'+tool.id)).slice(0,24);
   names.set(module.module_id+'\0'+oldName,newName);
  }
 }
 for(const offer of properties.offered_ports??[])names.set('\0ext_'+(await hash(oldId+'\0'+offer.ref)).slice(0,24),'ext_'+(await hash(node.node_id+'\0'+offer.ref)).slice(0,24));
 const visit=value=>{
  if(!value||typeof value!=='object')return;
  if(value.tool){const next=names.get((value.factory_module??'')+'\0'+value.tool);if(next){value.tool=next;if(value.description?.startsWith(oldId+' · '))value.description=node.node_id+value.description.slice(oldId.length);}}
  for(const child of value.members??[])visit(child);
 };
 visit(node.tables?.tools);for(const module of node.tables?.modules??[])visit(module.tools);
}
